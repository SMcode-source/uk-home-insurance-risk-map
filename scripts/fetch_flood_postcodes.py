"""River/sea flood fractions as the share of unit POSTCODES in the extent.

fetch_flood.py measures the share of a district's AREA inside the
national flood extents. The model's first external validation
(2026-09-05, HANDOFF) held that ordering against NRW's people at risk
per household in Wales and found sea at Spearman +0.70, surface water
+0.57 and rivers at -0.13: in valley geography the floodplain is a
sliver of the district and carries most of the housing, so area share
is a poor proxy for the share of homes. Sampling the SAME extents at
every Code-Point Open / ONSPD unit-postcode centroid instead (each
unit postcode is ~15 addresses) took rivers to +0.42 (high band) and
+0.58 (envelope), and river+sea to +0.75.

This script does that for all of Great Britain in one pass:

  England  : EA NaFRA2 defended extents, the WMS masks fetch_flood.py
             rasterises at 100 m, sampled at the postcode's pixel.
  Wales    : NRW FRAW rivers + sea, same masks.
  Scotland : SEPA river + coastal likelihood polygons, point-in-polygon.

Every postcode row carries its district and sector, so one fetch
serves both grains; the grain written is the one whose names
load_districts() returns on this checkout (sector names contain a
space). Thin units are shrunk toward their parent (sector -> district,
district -> postcode area) with a prior worth K_PRIOR postcodes, so a
sector with two postcodes cannot land on 0 or 1; the 816 sectors with
no live postcode at all in this ONSPD vintage (0.46% of households)
take their district's share outright. Anything still missing falls to
the national median inside scores_real._load_fraction_csv, as before.

Needs data/postcode_centroids.csv (fetch_onspd.py). Same output file
and columns as fetch_flood.py, same meaning of high/low, different
denominator:

    data/flood_fractions.csv   name, f_high, f_low
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_flood as ff                          # noqa: E402
from build_model import load_districts           # noqa: E402

PX, TILE = ff.PX, ff.TILE
DATA = "data"
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
OUT = os.path.join(DATA, "flood_fractions.csv")
K_PRIOR = 20        # postcodes of prior weight; see main()


def raster_region(name, pc, x, y, in_high, in_low):
    region = ff.REGIONS[name]
    minx, miny, maxx, maxy = region["bbox"]
    nx = int(np.ceil((maxx - minx) / (TILE * PX)))
    ny = int(np.ceil((maxy - miny) / (TILE * PX)))
    ctry = (pc["country"] == name.capitalize()).values
    for ix in range(nx):
        for iy in range(ny):
            x0, y0 = minx + ix * TILE * PX, miny + iy * TILE * PX
            bbox = (x0, y0, x0 + TILE * PX, y0 + TILE * PX)
            sel = ctry & (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
            if not sel.any():
                continue
            idx = np.nonzero(sel)[0]
            cols = np.clip(((x[idx] - bbox[0]) / PX).astype(int), 0, TILE - 1)
            rows = np.clip(((bbox[3] - y[idx]) / PX).astype(int), 0, TILE - 1)
            for band, layers in region["bands"].items():
                mask = None
                for kind, base, layer, cql in layers:
                    m = ff.fetch_mask(kind, base, layer, cql, bbox)
                    if m is not None:
                        mask = m if mask is None else (mask | m)
                if mask is None:
                    continue
                (in_high if band == "high" else in_low)[idx] |= mask[rows, cols]
            print(f"  {name} tile {ix},{iy}: {len(idx):,} postcodes", flush=True)
            time.sleep(0.15)


def vector_scotland(pc, x, y, in_high, in_low):
    from pyproj import Transformer
    region = ff.REGIONS["scotland"]
    idx_all = np.nonzero((pc["country"] == "Scotland").values)[0]
    tree = shapely.STRtree(shapely.points(x[idx_all], y[idx_all]))
    t4326 = Transformer.from_crs(4326, 27700, always_xy=True)
    for band, layers in region["bands"].items():
        target = in_high if band == "high" else in_low
        for svc, lid in layers:
            offset, total = 0, 0
            while True:
                q = dict(where="1=1", outFields="", returnGeometry="true",
                         outSR=27700, maxAllowableOffset=100, f="geojson",
                         resultOffset=offset, resultRecordCount=1000)
                url = (f"{ff.SEPA}/{svc}/FeatureServer/{lid}/query?"
                       + urllib.parse.urlencode(q))
                data = None
                for attempt in range(4):
                    try:
                        with urllib.request.urlopen(url, timeout=300) as r:
                            data = json.load(r)
                        break
                    except Exception as e:                # noqa: BLE001
                        print(f"    retry {attempt + 1} {svc}: {e}", flush=True)
                        time.sleep(10)
                if data is None or "features" not in data:
                    raise SystemExit(f"{svc}: no answer at offset {offset} - "
                                     "refusing to write a partial Scotland")
                feats = data["features"]
                if not feats:
                    break
                geoms = shapely.from_geojson(json.dumps(
                    {"type": "GeometryCollection",
                     "geometries": [f["geometry"] for f in feats if f.get("geometry")]}))
                geoms = np.array(shapely.get_parts(geoms))
                if len(geoms):
                    # f=geojson may come back lon/lat regardless of outSR
                    if abs(shapely.get_x(shapely.centroid(geoms[0]))) <= 180:
                        geoms = shapely.transform(
                            geoms, lambda xy: np.column_stack(
                                t4326.transform(xy[:, 0], xy[:, 1])))
                    geoms = shapely.make_valid(geoms)
                    pairs = tree.query(geoms, predicate="intersects")
                    if pairs.shape[1]:
                        target[idx_all[np.unique(pairs[1])]] = True
                total += len(feats)
                offset += len(feats)
                if len(feats) < 1000:
                    break
            print(f"  scotland {svc}: {total} features", flush=True)


def main():
    if not os.path.exists(CENTROIDS):
        raise SystemExit(f"{CENTROIDS} missing - run scripts/fetch_onspd.py first")
    pc = pd.read_csv(CENTROIDS)
    pc = pc[pc["country"].isin(["England", "Wales", "Scotland"])].reset_index(drop=True)
    print(f"GB unit postcodes: {len(pc):,}", flush=True)
    x = pc["easting"].values.astype(float)
    y = pc["northing"].values.astype(float)
    in_high = np.zeros(len(pc), dtype=bool)
    in_low = np.zeros(len(pc), dtype=bool)

    raster_region("wales", pc, x, y, in_high, in_low)
    vector_scotland(pc, x, y, in_high, in_low)
    raster_region("england", pc, x, y, in_high, in_low)
    if ff.FAILED:
        raise SystemExit(f"{len(ff.FAILED)} tiles failed - refusing to write "
                         "a partial file")
    pc["in_high"] = in_high
    pc["in_low"] = in_low | in_high

    names = load_districts()["name"].tolist()
    grain = "sector" if any(" " in n for n in names) else "district"
    # A unit with two live postcodes can only be 0, 1/2 or 1. 412 sectors
    # have fewer than 20 postcodes (0.27% of households) and 76 districts
    # do (0.04%); unshrunk, 359 of those sectors landed on exactly 0 or 1
    # and PH44 (one postcode) went from f_high 0.20 to 1.00 and +143 on
    # its premium. So each unit's share is the beta-binomial posterior
    # mean with its PARENT's share as the prior and a prior weight of
    # K_PRIOR postcodes (~300 addresses): a sector shrinks toward its
    # district, a district toward its postcode area. With hundreds of
    # postcodes the prior is a rounding error; with two, the unit takes
    # its parent's value. A parent with no postcodes falls through to
    # the national median inside scores_real._load_fraction_csv.
    # The prior is itself shrunk one level up: a sector in a district
    # with one postcode (PH44 4 in PH44) otherwise inherits a prior that
    # is as thin as it is, and 0/1 comes back through the back door.
    parent_of = {"sector": "district", "district": "area"}[grain]
    own = pc.groupby(grain).agg(n=("in_high", "size"), h=("in_high", "sum"),
                                l=("in_low", "sum"))
    area = pc.groupby("area").agg(f_high=("in_high", "mean"),
                                  f_low=("in_low", "mean"))
    if grain == "district":
        prior = area
    else:
        dist = pc.groupby("district").agg(n=("in_high", "size"),
                                          h=("in_high", "sum"),
                                          l=("in_low", "sum"))
        pa = area.reindex(dist.index.str.rstrip("0123456789")).set_index(dist.index)
        prior = pd.DataFrame({
            "f_high": (dist["h"] + K_PRIOR * pa["f_high"]) / (dist["n"] + K_PRIOR),
            "f_low": (dist["l"] + K_PRIOR * pa["f_low"]) / (dist["n"] + K_PRIOR)})
    rows, thin, missing = [], 0, 0
    for n in names:
        p = n.split(" ")[0] if grain == "sector" else n.rstrip("0123456789")
        if p not in prior.index:
            missing += 1
            continue
        ph, pl = prior.loc[p, "f_high"], prior.loc[p, "f_low"]
        if n in own.index:
            cnt, h, l = own.loc[n, ["n", "h", "l"]]
            if cnt < K_PRIOR:
                thin += 1
            fh = (h + K_PRIOR * ph) / (cnt + K_PRIOR)
            fl = (l + K_PRIOR * pl) / (cnt + K_PRIOR)
        else:
            thin += 1
            fh, fl = ph, pl
        rows.append((n, fh, fl))
    pd.DataFrame(rows, columns=["name", "f_high", "f_low"]).to_csv(
        OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT}: {len(rows)} {grain}s ({thin} with fewer than "
          f"{K_PRIOR} postcodes, shrunk toward their {parent_of}; {missing} "
          f"left to the median fallback); postcodes in high "
          f"{pc['in_high'].mean():.3%}, low {pc['in_low'].mean():.3%}")


if __name__ == "__main__":
    main()
