"""Fetch NCERM coastal-erosion zones per postcode district (England).

Source: Environment Agency, National Coastal Erosion Risk Mapping (NCERM)
National 2024, Open Government Licence. Served from

    https://environment.data.gov.uk/spatialdata/ncern-national-2024/wfs

Note the slug is "ncern", not "ncerm" - the EA misspelled its own dataset,
and the correctly-spelled URL 404s.

NCERM splits the English coast into ~7,500 "frontages" and projects, for
each, the strip of land expected to be lost to erosion by a given epoch,
under two policy scenarios:

    SMP  - the adopted Shoreline Management Plan (defences maintained as
           currently planned).  This is the realistic case.
    NFI  - No Further Intervention (defences allowed to lapse).  This is
           the worst case, and is what the land would do unmanaged.

each at epochs 2055 and 2105, under a 70th-percentile climate-change
allowance. Feature attributes carry the SMP policy per frontage
(`mt_smp`/`lt_smp`, e.g. "No Active Intervention", "Hold the Line").

Separately, `NCERM_Ground_Instability_Zone` (80 features) marks cliffs
with landslip/ground-instability behaviour.

Output: data/erosion.csv, one row per district:
    er_smp55, er_smp105, er_nfi55, er_nfi105  erosion-zone area as a
                                              fraction of district area
    er_smp105_m2                              absolute area lost (m^2)
    er_gi                                     ground-instability zone
                                              fraction
    er_coastal                                1 if any zone touches it

IMPORTANT - what this is NOT: gradual coastal erosion is excluded from
standard UK household insurance policies. These columns are a blight /
valuation exposure measure, not an insured loss. See README.

Usage:
    python -u scripts/fetch_erosion.py
"""

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import geopandas as gpd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import load_districts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
OUT = os.path.join(DATA, "erosion.csv")

BASE = "https://environment.data.gov.uk/spatialdata/ncern-national-2024/wfs"
PAGE = 1000

# (WFS typeName, csv column, recession attribute)
# The recession attribute is the projected retreat in metres for that
# scenario and epoch. Ground instability has no recession figure - its
# polygons are genuine zones, so its area is used directly.
#
# NCERM publishes each epoch under three climate-change allowances: the
# 0th, 70th and 95th percentiles. The 70th is the central case the model
# prices from; the other two bound it, so the erosion layer can answer
# "how much of this is the climate assumption?". On a sample Northumberland
# frontage the 2105 recession runs 8 m / 18 m / 20 m across the three.
LAYERS = [
    ("NCERM_SMP_2055_70CC", "er_smp55", "smp2055_70"),
    ("NCERM_SMP_2105_70CC", "er_smp105", "smp2105_70"),
    ("NCERM_NFI_2055_70CC", "er_nfi55", "nfi2055_70"),
    ("NCERM_NFI_2105_70CC", "er_nfi105", "nfi2105_70"),
    # climate-allowance bounds on the 2105 epoch
    ("NCERM_SMP_2105_0CC", "er_smp105_lo", "smp2105_0"),
    ("NCERM_SMP_2105_95CC", "er_smp105_hi", "smp2105_95"),
    ("NCERM_NFI_2105_0CC", "er_nfi105_lo", "nfi2105_0"),
    ("NCERM_NFI_2105_95CC", "er_nfi105_hi", "nfi2105_95"),
    ("NCERM_Ground_Instability_Zone", "er_gi", None),
]


def http_json(url, timeout=300):
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (uk-risk-map)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            print(f"    retry {attempt + 1}: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None


def fetch_layer(type_name):
    """Page through a WFS layer, returning a GeoDataFrame in EPSG:27700."""
    cache = os.path.join(CACHE, f"ncerm_{type_name}.geojson")
    if os.path.exists(cache):
        print(f"  {type_name}: cached", flush=True)
        return gpd.read_file(cache)

    feats, start = [], 0
    while True:
        q = dict(service="WFS", version="2.0.0", request="GetFeature",
                 typeNames=type_name, count=PAGE, startIndex=start,
                 outputFormat="application/json",
                 srsName="urn:ogc:def:crs:EPSG::27700")
        d = http_json(BASE + "?" + urllib.parse.urlencode(q))
        if d is None:
            raise RuntimeError(f"failed to fetch {type_name} at {start}")
        got = d.get("features", [])
        feats.extend(got)
        print(f"    {type_name}: {len(feats)} features", flush=True)
        if len(got) < PAGE:
            break
        start += PAGE

    gdf = gpd.GeoDataFrame.from_features(feats)
    if gdf.empty:
        raise RuntimeError(f"{type_name} returned nothing")

    # CRS check. Asking for 27700 does not guarantee getting it, and this
    # project has been bitten by a silent lon/lat vs BNG mix before, so
    # decide from the actual coordinate magnitudes rather than the header.
    xs = shapely.get_coordinates(gdf.geometry.values)[:, 0]
    lo, hi = float(np.nanmin(xs)), float(np.nanmax(xs))
    if -12.0 <= lo and hi <= 3.0:
        print(f"    {type_name}: coords look like lon/lat "
              f"(x in [{lo:.2f}, {hi:.2f}]) -> tagging 4326", flush=True)
        gdf = gdf.set_crs(4326).to_crs(27700)
    else:
        print(f"    {type_name}: coords look like BNG "
              f"(x in [{lo:.0f}, {hi:.0f}])", flush=True)
        gdf = gdf.set_crs(27700, allow_override=True)

    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    os.makedirs(CACHE, exist_ok=True)
    gdf.to_file(cache, driver="GeoJSON")
    return gdf


def main():
    print("loading districts...", flush=True)
    districts = load_districts().to_crs(27700)
    names = districts["name"].values
    n = len(districts)
    area = shapely.area(districts.geometry.values)
    tree = shapely.STRtree(districts.geometry.values)

    cols = {c: np.zeros(n) for _, c, _ in LAYERS}
    abs_m2 = np.zeros(n)

    for type_name, col, rec_attr in LAYERS:
        print(f"fetching {type_name}...", flush=True)
        zones = fetch_layer(type_name)
        geoms = zones.geometry.values
        poly_area = shapely.area(geoms)

        # How much land is actually lost, per frontage.
        #
        # The polygon is NOT a reliable measure of that. For most frontages
        # it is the recession strip and its area is close to
        # length x recession, but ~2-10% of records - concentrated in
        # estuaries - are broad zones instead. Frontage 101342 covers 10 km2
        # of the Dee while declaring a 3 m recession over a 110 km
        # "frontage"; taken at face value it made two Wirral districts
        # (CH60, CH64) the most erosion-exposed in England, ahead of the
        # Holderness coast, and barely moved between 2055 and 2105 - the
        # tell that it is not erosion at all.
        #
        # So: take the LAND LOST from the authoritative recession attribute
        # (length x recession) and use the polygon only to decide WHERE it
        # falls. This also stops the broad zones from flattening the
        # scenario contrast, which is the point of the layer: on raw
        # polygon area SMP-2055 to NFI-2105 spans only 1.6x, on
        # length x recession it spans 6.4x.
        if rec_attr is not None:
            rec = zones[rec_attr].astype(float).values
            length = zones["shape_leng"].astype(float).values
            lost = np.where(np.isfinite(rec) & np.isfinite(length),
                            np.maximum(rec, 0.0) * np.maximum(length, 0.0),
                            0.0)
        else:
            lost = poly_area          # ground instability: a genuine zone

        print(f"  {len(geoms)} polygons, {lost.sum() / 1e6:,.1f} km2 of land "
              f"lost (polygon area would say {poly_area.sum() / 1e6:,.1f})",
              flush=True)

        # allocate each frontage's land loss to districts in proportion to
        # where its polygon actually lies
        pairs = tree.query(geoms, predicate="intersects")
        zi, di = pairs[0], pairs[1]
        for k in range(len(zi)):
            z, dd = zi[k], di[k]
            if lost[z] <= 0 or poly_area[z] <= 0:
                continue
            inter = shapely.intersection(geoms[z],
                                         districts.geometry.values[dd])
            share = shapely.area(inter) / poly_area[z]
            if share <= 0:
                continue
            a = lost[z] * share
            cols[col][dd] += a
            if col == "er_smp105":
                abs_m2[dd] += a
        touched = int((cols[col] > 0).sum())
        print(f"  {col}: {touched} districts touched, "
              f"{cols[col].sum() / 1e6:,.1f} km2 allocated", flush=True)

    # areas -> fractions of district area
    frac = {c: np.clip(v / area, 0, 1) for c, v in cols.items()}

    # A district is 'coastal' for our purposes if the no-intervention
    # long-horizon zone reaches it at all.
    coastal = (cols["er_nfi105"] > 0) | (cols["er_smp105"] > 0)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        header = ["name"] + [c for _, c, _ in LAYERS] + ["er_smp105_m2",
                                                         "er_coastal"]
        w.writerow(header)
        for i in range(n):
            w.writerow([names[i]]
                       + [round(float(frac[c][i]), 8) for _, c, _ in LAYERS]
                       + [round(float(abs_m2[i]), 1), int(coastal[i])])
    print(f"wrote {OUT}", flush=True)

    print(f"  coastal districts: {int(coastal.sum())} of {n}")
    for _, c, _ in LAYERS:
        v = frac[c]
        print(f"  {c}: mean {v.mean():.6f}  max {v.max():.4f}  "
              f"nonzero {int((v > 0).sum())}")
    order = np.argsort(-frac["er_nfi105"])[:12]
    print("\n  most erosion-exposed districts (NFI 2105):")
    for i in order:
        print(f"    {names[i]:6s} nfi105={frac['er_nfi105'][i]:.5f}  "
              f"smp105={frac['er_smp105'][i]:.5f}  "
              f"nfi55={frac['er_nfi55'][i]:.5f}")


if __name__ == "__main__":
    main()
