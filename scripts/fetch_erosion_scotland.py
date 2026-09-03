"""Fetch Dynamic Coast projected coastal erosion per postcode district (Scotland).

Source: NatureScot / Dynamic Coast phase 2 ("FutureCoast"), Open Government
Licence, served as ArcGIS feature services from

    https://services1.arcgis.com/LM9GyVFsughzHdbO/arcgis/rest/services/

This is the Scottish counterpart to fetch_erosion.py (EA NCERM, England).
The two are NOT the same measurement and the differences are the whole
reason this file exists separately - see DATA_SOURCES.md #38(d).

WHAT DYNAMIC COAST PUBLISHES

Erosion polygons between the 2020 Mean High Water Springs line and the
projected MHWS line for a horizon, under two emissions pathways:

    RCP8.5 (95th percentile)  high  2050, 2100   the 11 open services
    RCP2.6                    low   2050, 2100   DC2_LES_results

Each dataset is tiered by ERODETYPE:

    ErodedArea   land seaward of the projected MHWS - land that goes
    Influence    a 10 m landward buffer on it
    Vicinity     a further 50 m landward buffer on Influence

ONLY ErodedArea is land projected to be lost. Influence and Vicinity are
nested buffers, so summing the three triple-counts.

TWO WAYS THIS DIFFERS FROM NCERM, BOTH DISCLOSED RATHER THAN PAPERED OVER

1. MANAGEMENT. NCERM publishes a pair - SMP (defences maintained as
   planned) and NFI (no further intervention) - and the model's headline
   score uses SMP. Dynamic Coast publishes ONE management case: its layer
   description calls it a "'do nothing' coastal management approach" in
   which "up to 25m of erosion is permitted at known artificial coastal
   defences". That is no NEW intervention with existing defences standing,
   which is nearer NCERM's SMP than its NFI but is not either of them.
   There is no Scottish NFI, so er_nfi* stays zero in Scotland and the
   er_basis column says why.

2. CLIMATE. NCERM publishes the 0th, 70th and 95th percentile allowances
   and the model prices the 70th. Dynamic Coast's ladder is RCP2.6 and
   RCP8.5-95th, which line up with the 0th/95th ends. There is no Scottish
   central case, so the headline takes RCP8.5-95th - the nearer of the two
   to England's 70th, by a measured margin: on England's own 2105 NFI
   columns the 95th is 1.162x the 70th while the 0th is 0.534x of it.

AREA COMES FROM THE POLYGON, WHICH REVERSES NCERM (#21)

fetch_erosion.py deliberately ignores NCERM's polygon areas and rebuilds
land lost as length x recession, because ~2-10% of NCERM "frontages" are
broad estuary zones. Do not copy that here. Dynamic Coast's polygon IS the
modelled outcome - the strip between two MHWS lines, already limited by
the UPSM susceptibility model and by the 25 m defence cap - while its
transect Dist_* attributes are the unconstrained projection upstream of
those limits. The two disagree by construction: 164,371 erosional
transects sum to 1,467,665 m of 2100 recession, which against 79.748 km2
of ErodedArea implies a 54 m mean transect spacing, while the same
arithmetic at 2050 implies 20 m. One coast cannot have two spacings.

Output: data/erosion_scotland.csv, one row per district that Dynamic Coast
reaches (Scottish districts only; everything else is absent, not zero):

    er_dc50_hi, er_dc100_hi   RCP8.5-95th eroded area / district area
    er_dc50_lo, er_dc100_lo   RCP2.6            same
    *_m2                      the same four as absolute areas

The absolute columns are there because the site needs them and cannot
recover them: `area` in the published GeoJSON is a region LABEL, not a
number, so a km2 figure cannot be rebuilt from the fractions downstream.
This file is the side channel, read the way build_site already reads
burglary.csv.

IMPORTANT - what this is NOT: gradual coastal erosion is excluded from
standard UK household insurance. These columns are a blight / valuation
exposure measure, not an insured loss, exactly as the English ones are.

Usage:
    .venv/Scripts/python.exe -u scripts/fetch_erosion_scotland.py
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
from scores_real import load_country    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
OUT = os.path.join(DATA, "erosion_scotland.csv")

ORG = "https://services1.arcgis.com/LM9GyVFsughzHdbO/arcgis/rest/services"
PAGE = 2000                      # the services' own maxRecordCount

# (cache key, service path, csv column)
# Two services carry the RCP8.5 branch one horizon each; the RCP2.6 branch
# lives as two layers inside one bundled service.
LAYERS = [
    ("dc_2050_hi", "DynamicCoast_Future_Erosion_2050_High_Emissions_Scenario"
                   "/FeatureServer/0", "er_dc50_hi"),
    ("dc_2100_hi", "DynamicCoast_Future_Erosion_2100_High_Emissions_Scenario"
                   "/FeatureServer/0", "er_dc100_hi"),
    ("dc_2050_lo", "DC2_LES_results/FeatureServer/1", "er_dc50_lo"),
    ("dc_2100_lo", "DC2_LES_results/FeatureServer/2", "er_dc100_lo"),
]

# Published ErodedArea totals, km2, read off the services' own
# groupBy-ERODETYPE statistics on 2026-09-03. The fetch asserts against
# these: a silently truncated page or a changed edition should fail loudly
# rather than quietly halve Scotland's erosion.
PUBLISHED_KM2 = {
    "er_dc50_hi": 17.914,
    "er_dc100_hi": 79.748,
    "er_dc50_lo": 12.871,
    "er_dc100_lo": 32.520,
}
TOTAL_TOL = 0.02                 # 2% - allows for float/reprojection drift


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


def drop_null_geometry(gdf, key):
    """Rows with geometry: null - real, and poisonous if left in.

    Some ArcGIS rows come back attributes-only: 3,937 of the 59,972 in the
    RCP2.6 2050 layer on 2026-09-03. They are not a paging failure -
    dropping them leaves the area total matching the service's own
    groupBy statistic to five figures - but shapely.area gives them NaN,
    which then silently poisons every sum downstream. Applied on the
    cached path too, because the cache is written before this ran the
    first time and a stale cache must not smuggle them back in.
    """
    bad = gdf.geometry.isna() | gdf.geometry.is_empty
    n = int(bad.sum())
    if n:
        print(f"    {key}: {n} features with no geometry -> dropped",
              flush=True)
        gdf = gdf[~bad].copy()
    return gdf


def fetch_layer(key, path):
    """Page an ArcGIS layer's ErodedArea features into EPSG:27700."""
    cache = os.path.join(CACHE, f"dynamiccoast_{key}.geojson")
    if os.path.exists(cache):
        print(f"  {key}: cached", flush=True)
        return drop_null_geometry(gpd.read_file(cache), key)

    feats, offset = [], 0
    while True:
        q = dict(where="ERODETYPE='ErodedArea'", outFields="ERODETYPE",
                 returnGeometry="true", outSR=27700, f="geojson",
                 resultOffset=offset, resultRecordCount=PAGE)
        d = http_json(f"{ORG}/{path}/query?" + urllib.parse.urlencode(q))
        if d is None:
            raise RuntimeError(f"failed to fetch {key} at offset {offset}")
        if "error" in d:
            raise RuntimeError(f"{key}: {d['error']}")
        got = d.get("features", [])
        feats.extend(got)
        print(f"    {key}: {len(feats)} features", flush=True)
        # exceededTransferLimit is the authoritative "there is more"; the
        # page-size heuristic alone is wrong when the last page is exactly
        # PAGE long.
        if not d.get("properties", {}).get("exceededTransferLimit") \
                and len(got) < PAGE:
            break
        if not got:
            break
        offset += len(got)

    gdf = gpd.GeoDataFrame.from_features(feats)
    if gdf.empty:
        raise RuntimeError(f"{key} returned nothing")

    gdf = drop_null_geometry(gdf, key)

    # CRS check by coordinate magnitude, not by header - the same trap
    # fetch_erosion.py guards. Asking for outSR=27700 is not getting it.
    xs = shapely.get_coordinates(gdf.geometry.values)[:, 0]
    lo, hi = float(np.nanmin(xs)), float(np.nanmax(xs))
    if -12.0 <= lo and hi <= 3.0:
        print(f"    {key}: coords look like lon/lat "
              f"(x in [{lo:.2f}, {hi:.2f}]) -> tagging 4326", flush=True)
        gdf = gdf.set_crs(4326).to_crs(27700)
    else:
        print(f"    {key}: coords look like BNG "
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

    country = load_country(names)
    scot = np.array([c == "Scotland" for c in country])
    if not scot.any():
        raise SystemExit("no Scottish districts in the frame - "
                         "run scripts/fetch_countries.py first")
    print(f"  {int(scot.sum())} Scottish districts of {n}", flush=True)

    cols = {c: np.zeros(n) for _, _, c in LAYERS}

    for key, path, col in LAYERS:
        print(f"fetching {key}...", flush=True)
        zones = fetch_layer(key, path)
        geoms = zones.geometry.values
        poly_area = shapely.area(geoms)

        got_km2 = poly_area.sum() / 1e6
        want_km2 = PUBLISHED_KM2[col]
        # NaN first, and on its own line. Every comparison against NaN is
        # False, so folding this into the tolerance test below lets a
        # single null geometry walk straight through the guard - which is
        # exactly what happened on the first run of this script.
        if not np.isfinite(got_km2):
            raise SystemExit(
                f"{key}: ErodedArea total came out {got_km2} - a null or "
                "invalid geometry survived drop_null_geometry(). Fix the "
                "clean, do not sum around it.")
        if abs(got_km2 - want_km2) / want_km2 > TOTAL_TOL:
            raise SystemExit(
                f"{key}: fetched {got_km2:,.3f} km2 of ErodedArea against "
                f"{want_km2:,.3f} published on 2026-09-03 "
                f"({100 * (got_km2 / want_km2 - 1):+.1f}%). Either a page "
                "was dropped or NatureScot republished - check before "
                "trusting this, do not widen TOTAL_TOL to make it pass.")
        print(f"  {len(geoms)} ErodedArea polygons, {got_km2:,.3f} km2 "
              f"(published {want_km2:,.3f})", flush=True)

        # Allocate each polygon's area to the districts it lies in. Unlike
        # NCERM there is no separate "land lost" attribute to distribute -
        # the polygon area IS the land lost - so this is a straight
        # geometric intersection, and it needs no share arithmetic.
        pairs = tree.query(geoms, predicate="intersects")
        zi, di = pairs[0], pairs[1]
        for k in range(len(zi)):
            z, dd = zi[k], di[k]
            inter = shapely.intersection(geoms[z],
                                         districts.geometry.values[dd])
            a = shapely.area(inter)
            if a > 0:
                cols[col][dd] += a

        alloc = cols[col].sum() / 1e6
        outside = 1.0 - alloc / got_km2
        touched = int((cols[col] > 0).sum())
        print(f"  {col}: {touched} districts touched, {alloc:,.3f} km2 "
              f"allocated ({100 * outside:.1f}% fell outside the district "
              "polygons - intertidal slivers seaward of the coastline)",
              flush=True)

        # Erosion is a Scottish-coast product; anything it lands on outside
        # Scotland is a district-boundary artefact, not data.
        stray = cols[col][~scot]
        if stray.sum() > 0:
            worst = names[~scot][np.argsort(-stray)[:5]]
            print(f"    {int((stray > 0).sum())} non-Scottish districts "
                  f"picked up {stray.sum() / 1e6:.4f} km2 "
                  f"({', '.join(worst[:5])}) -> dropped", flush=True)
            cols[col][~scot] = 0.0

    frac = {c: np.clip(v / area, 0, 1) for c, v in cols.items()}
    keep = scot & (cols["er_dc100_hi"] > 0)

    order_cols = [c for _, _, c in LAYERS]
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name"] + order_cols + [f"{c}_m2" for c in order_cols])
        for i in np.flatnonzero(keep):
            w.writerow([names[i]]
                       + [round(float(frac[c][i]), 8) for c in order_cols]
                       + [round(float(cols[c][i]), 1) for c in order_cols])
    print(f"wrote {OUT}: {int(keep.sum())} Scottish coastal districts "
          f"of {int(scot.sum())}", flush=True)

    for _, _, c in LAYERS:
        v = frac[c][keep]
        print(f"  {c}: mean {v.mean():.6f}  max {v.max():.5f}")
    hi, lo = cols["er_dc100_hi"].sum(), cols["er_dc100_lo"].sum()
    print(f"  climate ladder at 2100: RCP8.5-95th / RCP2.6 = {hi / lo:.2f}x")

    order = np.argsort(-frac["er_dc100_hi"])[:12]
    print("\n  most erosion-exposed Scottish districts (RCP8.5 2100):")
    for i in order:
        print(f"    {names[i]:6s} 2100hi={frac['er_dc100_hi'][i]:.5f}  "
              f"2100lo={frac['er_dc100_lo'][i]:.5f}  "
              f"2050hi={frac['er_dc50_hi'][i]:.5f}")


if __name__ == "__main__":
    main()
