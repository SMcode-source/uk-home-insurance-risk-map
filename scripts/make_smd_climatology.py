"""The committed input for the Gate 2 SMD-curve experiment.

Reduces the gitignored 66-year 1 km per-district table
(data/haduk_district_annual_1km.csv, built by haduk_1km_stream.py on CI,
run 33319459184) to the one thing the pricing experiment needs: each
district's 1991-2020 drought climatology, on the two candidate indices.

  cwd_yr_clim_mm   mean annual peak of the uncapped within-year deficit
                   max(cumsum(PET - rain), 0), reset each 1 January. The
                   index that recovered 5 of 6 canonical subsidence years
                   nationally and discriminates 1976 from 1975.
  smd_jja_clim_mm  mean June-August soil moisture deficit under a 150 mm
                   capped bucket. Tamer (the cap compresses the top), and
                   the second candidate so the experiment prices the
                   index CHOICE, not just the share.

1991-2020 to match the window of every other climatology the model
carries (frost_days, the Met Office grids). Raw mm, NOT normalised: the
exposure-weighted normalisation happens on the live frame in the model,
like eow_rate's, because a mean baked into a file goes stale the moment
exposure changes.

KNOWN LIMITATION, carried on purpose: the PET inside these integrals is
Hargreaves-Samani, which runs ~a third high in a maritime climate. The
level is therefore not a soil-physics quantity. What the experiment
prices is the RELATIVITY, and whether that survives the PET level is
measured (haduk_district_daily.py --pet-sensitivity) rather than assumed.
The citable fix, if the leg ever ships, is Hydro-PE (Penman-Monteith on
this same HadUK-Grid met, 1 km daily 1969-2021, CC-BY,
doi:10.5285/9275ab7e-6e93-42bc-8e72-59c98d409deb).

Usage:  make_smd_climatology.py [--src <annual csv>] [--out <csv>]

The defaults reduce the district table. The SECTOR grain (the same
construction over data/sectors_risk.geojson, workflow
haduk-1km-sectors.yml) is reduced with:
  make_smd_climatology.py --src data/haduk_sector_annual_1km.csv \
      --out data/smd_climatology.csv
and that output is committed on the sector-model branch under the SAME
filename - scores_real.drought_from_haduk reads one path and the grain
is decided by which branch's file is checked out, exactly like
children.csv and households.csv.
"""

import argparse
import csv
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "data", "haduk_district_annual_1km.csv")
OUT = os.path.join(ROOT, "data", "smd_climatology.csv")
CLIM = (1991, 2020)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    acc = defaultdict(lambda: {"cwd": [], "jja": []})
    with open(args.src, newline="") as fh:
        for r in csv.DictReader(fh):
            if CLIM[0] <= int(r["year"]) <= CLIM[1]:
                acc[r["district"]]["cwd"].append(float(r["cwd_yr_max_mm"]))
                acc[r["district"]]["jja"].append(float(r["smd_jja_mean_mm"]))
    n_y = CLIM[1] - CLIM[0] + 1
    rows = []
    for d in sorted(acc):
        a = acc[d]
        assert len(a["cwd"]) == n_y, f"{d}: {len(a['cwd'])} of {n_y} years"
        rows.append({"district": d,
                     "cwd_yr_clim_mm": round(float(np.mean(a["cwd"])), 2),
                     "smd_jja_clim_mm": round(float(np.mean(a["jja"])), 2)})
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}: {len(rows)} polygons, {CLIM[0]}-{CLIM[1]}")


if __name__ == "__main__":
    main()
