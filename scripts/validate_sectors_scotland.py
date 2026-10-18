"""Measure the Voronoi sector method against Scotland's official sectors.

Scotland is the one place postcode-sector polygons are actually
published (NRS Scottish Postcode Directory, layer 4 of the SPD
MapServer on maps.gov.scot, OGL) — so it is the one place the derived
partition (derive_sectors.py) can be scored against ground truth.

Two IoU distributions, and the GAP between them is the answer:

  * district-level IoU — my district polygon (union of my sectors) vs
    NRS's (union of theirs). This is boundary-SET disagreement:
    uk-postcode-polygons vs NRS, nothing to do with the method.
  * sector-level IoU — my derived sector vs the official one.

`district IoU − sector IoU` reads as what the Voronoi approximation
itself costs. It is a heuristic, not a bound: a sector can align BETTER
than its parent district (both sides can agree about the half of a
district the sector sits in while disagreeing about the other half), and
the two medians are taken over different populations (959 sectors vs
~100 districts). The measured gap is in fact slightly negative — sector
median 0.706 vs district median 0.689 — which supports the published
claim ("the derivation adds no measurable error beyond the district
outlines") without proving a theorem. Writes
data/sector_validation_scotland.csv and prints the summary.
"""

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

import shapely
import shapely.geometry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAYER = ("https://maps.gov.scot/server/rest/services/NRS/SPD/MapServer/4"
         "/query")
OUT = os.path.join(ROOT, "data", "sector_validation_scotland.csv")
SUMMARY = os.path.join(ROOT, "data", "sector_validation.json")


def fetch_official():
    """sector name -> shapely geometry (EPSG:27700), from the NRS layer."""
    geoms = {}
    offset = 0
    while True:
        # 1000-feature pages come back as an HTML error page (payload cap
        # on this MapServer - a single feature works fine); 50 detailed
        # coastline polygons per page at 1 m precision stays under it.
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": "sector", "f": "geojson",
            "outSR": 27700, "geometryPrecision": 0,
            "resultOffset": offset,
            "resultRecordCount": 50,
        })
        for attempt in range(6):
            try:
                with urllib.request.urlopen(f"{LAYER}?{q}", timeout=300) as r:
                    data = json.load(r)
                break
            except Exception as e:      # noqa: BLE001 - retried
                print(f"  retry {attempt + 1}: {e}", flush=True)
                time.sleep(10 * (attempt + 1))
        else:
            raise SystemExit("NRS layer unreachable")
        feats = data.get("features", [])
        if not feats:
            break
        for f in feats:
            name = " ".join(f["properties"]["sector"].split()).upper()
            # make_valid BEFORE any set op: 1 m-rounded coastline rings
            # self-touch, and GEOS throws "side location conflict" on
            # the first intersection with them (it did)
            g = shapely.make_valid(shapely.geometry.shape(f["geometry"]))
            geoms[name] = (shapely.union_all([geoms[name], g])
                           if name in geoms else g)
        offset += len(feats)
        print(f"  {offset} official sector features", flush=True)
    return geoms


def main():
    import geopandas as gpd
    print("official NRS sectors...", flush=True)
    official = fetch_official()
    print(f"{len(official):,} official sectors", flush=True)

    mine = gpd.read_file(os.path.join(ROOT, "data", "sectors_gb.gpkg"))
    mine = mine[mine["sector"].str.match(r"^(AB|DD|DG|EH|FK|G|HS|IV|KA|KW|"
                                         r"KY|ML|PA|PH|TD|ZE)\d")]
    mine = mine.assign(geometry=shapely.make_valid(mine.geometry.values))
    print(f"{len(mine):,} derived Scottish sectors", flush=True)

    # sector-level IoU over the shared names
    rows = []
    mine_by_name = dict(zip(mine["sector"], mine["geometry"]))
    shared = sorted(set(official) & set(mine_by_name))
    print(f"{len(shared):,} sector names in both", flush=True)
    for name in shared:
        a, b = mine_by_name[name], official[name]
        inter = shapely.intersection(a, b).area
        union = shapely.union(a, b).area
        rows.append((name, inter / union if union else 0.0))

    # district-level IoU: unions of each side's sectors
    def by_district(pairs):
        acc = defaultdict(list)
        for name, geom in pairs:
            acc[name.split()[0]].append(geom)
        return {d: shapely.union_all(gs) for d, gs in acc.items()}

    mine_d = by_district(mine_by_name.items())
    off_d = by_district(official.items())
    drows = []
    for d in sorted(set(mine_d) & set(off_d)):
        inter = shapely.intersection(mine_d[d], off_d[d]).area
        union = shapely.union(mine_d[d], off_d[d]).area
        drows.append((d, inter / union if union else 0.0))

    import numpy as np
    s_iou = np.array([r[1] for r in rows])
    d_iou = np.array([r[1] for r in drows])
    print(f"\ndistrict-level IoU (boundary-set disagreement only): "
          f"median {np.median(d_iou):.3f}, p10 {np.percentile(d_iou, 10):.3f}")
    print(f"sector-level IoU (boundary sets + Voronoi method): "
          f"median {np.median(s_iou):.3f}, p10 {np.percentile(s_iou, 10):.3f}")
    print(f"the method's own cost (median district - median sector IoU): "
          f"{np.median(d_iou) - np.median(s_iou):.3f}")
    print(f"sectors with IoU > 0.5: {100 * (s_iou > 0.5).mean():.0f}%  "
          f"> 0.7: {100 * (s_iou > 0.7).mean():.0f}%")

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sector", "iou"])
        w.writerows(rows)
    print(f"wrote {OUT}")

    # Summary the website injects, so the published claim about how good
    # the derived boundaries are cannot drift from the measurement.
    summary = {
        "n_official": len(official),
        "n_compared": len(rows),
        "sector_iou_median": round(float(np.median(s_iou)), 3),
        "district_iou_median": round(float(np.median(d_iou)), 3),
        "pct_above_50": round(100 * float((s_iou > 0.5).mean())),
        "pct_above_70": round(100 * float((s_iou > 0.7).mean())),
    }
    with open(SUMMARY, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"wrote {SUMMARY}: {summary}")


if __name__ == "__main__":
    main()
