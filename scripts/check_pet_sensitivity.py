"""Does the Hargreaves PET bias move the MAP, or only the level?

The one caveat the Gate 2 SMD finding carries is that Hargreaves-Samani
PET runs ~a third high in a maritime climate, and a uniform bias does
NOT cancel out of max(PET - rain, 0) - the integral is nonlinear in the
level. Before pricing a relativity built on that integral, this checks
the only thing the relativity actually uses: the RANKING and the SPREAD
of the per-district climatology, at PET x 1.00 vs x 0.85 vs x 0.70
(bracketing the plausible over-estimate; Hydro-PE's PM values sit in
that range of Hargreaves in the UK).

Reads any per-district annual table carrying the sensitivity columns
(cwd_yr_max_mm{,_k85,_k70} and smd_jja_mean_mm{,_k85,_k70}) - the 5 km
one from `haduk_district_daily.py --pet-sensitivity` (the default
path), or the 1 km one from the haduk-1km-pet.yml CI run (pass its
merged CSV as the argument; that workflow runs this check itself as
its last step). Reduces each column to the 1991-2020 per-district
mean and reports, per index and per scale:

  spearman   rank correlation with the k=1.00 climatology - if this is
             ~1 the map survives the PET level and the caveat is about
             the LEVEL only (which calibration re-pins anyway)
  rel p5/p95 of the normalised relativity clim/mean(clim) - how much
             the curve flattens as PET drops (unweighted mean here;
             the priced run normalises with exposure weights, but the
             flattening question doesn't need them)

It runs at BOTH resolutions on purpose: the 1 km run answers it on the
very table the pricing climatology came from, and the 5 km run is the
independent cross-check (the resolution comparison already put the two
climatologies at rho ~0.997+, so the verdicts should agree).

Usage:  check_pet_sensitivity.py [path-to-annual-csv]
"""

import csv
import os
import sys
from collections import defaultdict

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "data", "haduk_district_annual.csv")
CLIM = (1991, 2020)
INDICES = ("cwd_yr_max_mm", "smd_jja_mean_mm")
SCALES = ("", "_k85", "_k70")


def main():
    cols = [i + s for i in INDICES for s in SCALES]
    acc = defaultdict(lambda: defaultdict(list))
    with open(SRC, newline="") as fh:
        rdr = csv.DictReader(fh)
        missing = [c for c in cols if c not in rdr.fieldnames]
        if missing:
            raise SystemExit(
                f"{SRC} lacks {missing} - run haduk_district_daily.py "
                "--pet-sensitivity first")
        for r in rdr:
            if CLIM[0] <= int(r["year"]) <= CLIM[1]:
                a = acc[r["district"]]
                for c in cols:
                    a[c].append(float(r[c]))
    dists = sorted(acc)
    n_y = CLIM[1] - CLIM[0] + 1
    for d in dists:
        assert len(acc[d][cols[0]]) == n_y, \
            f"{d}: {len(acc[d][cols[0]])} of {n_y} years"
    print(f"{len(dists)} districts, climatology {CLIM[0]}-{CLIM[1]}\n")

    for idx in INDICES:
        base = np.array([np.mean(acc[d][idx]) for d in dists])
        print(f"== {idx} ==")
        for s, k in zip(SCALES, (1.00, 0.85, 0.70)):
            v = np.array([np.mean(acc[d][idx + s]) for d in dists])
            rel = v / v.mean()
            rho = spearmanr(base, v).statistic if s else 1.0
            print(f"  k={k:.2f}  spearman vs k=1 {rho:+.4f}   "
                  f"clim mean {v.mean():7.1f} mm   "
                  f"rel p5/p50/p95 {np.percentile(rel, 5):.3f}/"
                  f"{np.percentile(rel, 50):.3f}/"
                  f"{np.percentile(rel, 95):.3f}")
        print()


if __name__ == "__main__":
    main()
