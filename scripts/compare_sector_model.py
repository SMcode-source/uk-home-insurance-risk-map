"""The sector-model decision evidence: sectors vs the published districts.

Sectors nest exactly inside districts (derive_sectors.py), so the
sector model can be aggregated back and compared like-for-like:

  python scripts/compare_sector_model.py [sectors.geojson] [districts.geojson]

Defaults to the two published outputs on main - data/sectors_risk.geojson
and data/districts_risk.geojson. (On the sector-model branch the sector
build is itself data/districts_risk.geojson, so pass it explicitly there.)
Three questions, in order of importance:

1. CONSISTENCY - do household-weighted sector premiums aggregate back
   to roughly the district premium? Large systematic drift would mean
   the geography change moved the model, not just refined it.
2. RESOLUTION - how much within-district spread do sectors reveal?
   That spread is the entire argument for sector-level pricing: if
   sectors within a district all price alike, districts were enough.
3. WHERE - which districts hide the widest sector ranges, and which
   peril drives each? Those are the districts a district-level price
   was genuinely mis-rating.
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load(path):
    with open(path, encoding="utf-8") as fh:
        gj = json.load(fh)
    return [f["properties"] for f in gj["features"]]


def main(sector_path, district_path):
    sectors = load(sector_path)
    districts = {d["name"]: d for d in load(district_path)}
    if " " not in sectors[0]["name"]:
        raise SystemExit("names carry no sector digit - is this branch's "
                         "data/districts_risk.geojson really the sector "
                         "build?")

    # OUTPUT_COLUMNS does not carry `district`; the sector name encodes
    # it ("AB10 1" -> AB10) by construction of the derivation
    by_dist = defaultdict(list)
    for s in sectors:
        by_dist[s["name"].rsplit(" ", 1)[0]].append(s)
    print(f"{len(sectors):,} sectors over {len(by_dist):,} districts "
          f"({len(districts):,} in the published model)")

    # 1. consistency: household-weighted aggregation back to districts
    agg, pub, weights = [], [], []
    for name, group in by_dist.items():
        if name not in districts:
            continue
        hh = np.array([s.get("households", 1) for s in group], float)
        agg.append(np.average([s["premium"] for s in group], weights=hh))
        pub.append(districts[name]["premium"])
        weights.append(hh.sum())
    agg, pub, weights = map(np.array, (agg, pub, weights))
    lvl_s = np.average(agg, weights=weights)
    lvl_d = np.average(pub, weights=weights)
    print(f"\n1. CONSISTENCY")
    print(f"   exposure-weighted premium: districts £{lvl_d:.2f}, "
          f"sector-aggregated £{lvl_s:.2f} ({100 * (lvl_s / lvl_d - 1):+.1f}%)")
    print(f"   correlation of district premium vs aggregated sectors: "
          f"{np.corrcoef(pub, agg)[0, 1]:.3f}")
    resid = agg / pub - 1
    print(f"   aggregation residual: median |r| {np.median(np.abs(resid)):.1%}, "
          f"p95 |r| {np.percentile(np.abs(resid), 95):.1%}")

    # 2. resolution: the spread sectors reveal inside a district
    spreads = []
    for name, group in by_dist.items():
        if len(group) < 2 or name not in districts:
            continue
        prem = np.array([s["premium"] for s in group])
        hh = np.array([s.get("households", 1) for s in group], float)
        spreads.append((name, prem.min(), prem.max(),
                        prem.max() / max(prem.min(), 1e-9),
                        np.average(np.abs(prem - np.average(prem, weights=hh)),
                                   weights=hh) / np.average(prem, weights=hh),
                        len(group)))
    ratio = np.array([s[3] for s in spreads])
    mad = np.array([s[4] for s in spreads])
    print(f"\n2. RESOLUTION ({len(spreads):,} multi-sector districts)")
    print(f"   max/min premium ratio within a district: "
          f"median {np.median(ratio):.2f}x, p90 {np.percentile(ratio, 90):.2f}x, "
          f"max {ratio.max():.1f}x")
    print(f"   mean |deviation| from the district mean price: median "
          f"{np.median(mad):.1%}, p90 {np.percentile(mad, 90):.1%} "
          f"(exposure-weighted within each district)")
    print(f"   districts where sectors differ >2x: {(ratio > 2).sum()} "
          f"({100 * (ratio > 2).mean():.0f}%)")

    # 3. where the district price was hiding the most
    spreads.sort(key=lambda s: -s[3])
    print(f"\n3. WIDEST WITHIN-DISTRICT RANGES")
    for name, lo, hi, r, _m, n in spreads[:12]:
        d = districts.get(name, {})
        drivers = max(
            (("flood", d.get("el_fl", 0)), ("subsidence", d.get("el_sub", 0)),
             ("weather", d.get("el_wx", 0)), ("groundwater", d.get("el_gw", 0))),
            key=lambda kv: kv[1])[0]
        print(f"   {name:6s} £{lo:5.0f}-£{hi:5.0f} ({r:4.1f}x over {n} sectors)"
              f"  district price £{d.get('premium', float('nan')):5.0f}, "
              f"lead peril {drivers}")


if __name__ == "__main__":
    args = sys.argv[1:]
    sec = args[0] if args else os.path.join(ROOT, "data", "sectors_risk.geojson")
    dis = args[1] if len(args) > 1 else os.path.join(
        ROOT, "data", "districts_risk.geojson")
    main(sec, dis)
