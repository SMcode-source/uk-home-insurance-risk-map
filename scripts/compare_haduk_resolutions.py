"""Does 1 km change the answer, or only sharpen it? 5 km vs 1 km.

Joins data/haduk_district_annual.csv (5 km, area-weighted overlap) with
data/haduk_district_annual_1km.csv (1 km, point-in-polygon, fetched on
CI) on district x year and reports, per column:

  - agreement over all district-years (Pearson on values, Spearman on
    each year's cross-district ranking, averaged), which is the "same
    instrument?" question, and
  - agreement restricted to the districts 5 km CANNOT resolve (the ones
    sharing their every cell with a neighbour), which is the "what did
    the extra 166 GB actually buy?" question. If 1 km only reproduces
    the shared-cell value there, it bought separation on paper and
    nothing real - HadUK is interpolated, so grid spacing is not
    information density.

cwd_run_max_mm is compared but flagged: the CI run is sliced with one
spin-up year per slice, so its multi-year memory restarts at 1977, 1993
and 2010, and disagreement THERE is the slicing, not the resolution.

This script MEASURES. Nothing is wired into build_model.
"""

import csv
import os
from collections import defaultdict

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
P5 = os.path.join(ROOT, "data", "haduk_district_annual.csv")
P1 = os.path.join(ROOT, "data", "haduk_district_annual_1km.csv")

KEYS = ["rain_mm", "tmax_mean_c", "tmin_mean_c", "pet_mm", "smd_max_mm",
        "cwd_yr_max_mm", "cwd_run_max_mm", "smd_jja_mean_mm",
        "frost_days", "freeze_spells", "freeze_spell_days",
        "worst_spell_degc_days"]
SLICE_RESTARTS = {1977, 1993, 2010}     # cwd_run memory resets here on CI


def load(path):
    out = defaultdict(dict)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out[(r["district"], int(r["year"]))] = r
    return out


def main():
    a5, a1 = load(P5), load(P1)
    both = sorted(set(a5) & set(a1))
    dists = sorted({d for d, _ in both})
    years = sorted({y for _, y in both})
    print(f"{len(both)} shared district-years "
          f"({len(dists)} districts, {years[0]}-{years[-1]})")

    for k in KEYS:
        pairs = [(float(a5[b][k]), float(a1[b][k])) for b in both
                 if a5[b].get(k, "") != "" and a1[b].get(k, "") != ""]
        if not pairs:
            print(f"  {k:22s} absent from one table")
            continue
        v5, v1 = map(np.array, zip(*pairs))
        r = stats.pearsonr(v5, v1).statistic
        # cross-district rank agreement, per year, averaged - the shape
        # question Gate 2 actually asks of these tables
        rhos = []
        for y in years:
            if k == "cwd_run_max_mm" and y in SLICE_RESTARTS:
                continue
            p = [(float(a5[(d, y)][k]), float(a1[(d, y)][k]))
                 for d in dists if a5[(d, y)].get(k, "") != ""
                 and a1[(d, y)].get(k, "") != ""]
            if len(p) > 100:
                x, z = map(np.array, zip(*p))
                rhos.append(stats.spearmanr(x, z).statistic)
        flag = "  (slice-restart years excluded)" \
            if k == "cwd_run_max_mm" else ""
        print(f"  {k:22s} pearson {r:+.4f}   per-year spearman "
              f"{np.mean(rhos):+.4f} (min {np.min(rhos):+.4f}){flag}")

    # the separation question: how far apart are 1 km values inside
    # districts that are IDENTICAL at 5 km? Group districts by their
    # 5 km value vector for a sample year; identical vectors = shared
    # cells all the way down.
    probe = years[len(years) // 2]
    sig = defaultdict(list)
    for d in dists:
        sig[tuple(a5[(d, probe)][k] for k in KEYS)].append(d)
    shared = [g for g in sig.values() if len(g) > 1]
    n_shared = sum(len(g) for g in shared)
    print(f"\n{n_shared} of {len(dists)} districts are 5km-identical to a "
          f"neighbour in {probe} ({len(shared)} groups). Inside those "
          f"groups, the 1 km spread that 5 km cannot see:")
    for k in ("smd_jja_mean_mm", "cwd_yr_max_mm", "frost_days"):
        spreads = []
        for g in shared:
            v = [float(a1[(d, probe)][k]) for d in g
                 if a1[(d, probe)].get(k, "") != ""]
            if len(v) > 1 and max(v) > 0:
                spreads.append((max(v) - min(v)) / max(v))
        print(f"  {k:22s} median within-group spread "
              f"{np.median(spreads):.1%}, p90 {np.percentile(spreads, 90):.1%}")


if __name__ == "__main__":
    main()
