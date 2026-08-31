"""Per-era frost climatologies, for the freeze re-aim experiment only.

Reduces the gitignored 66-year per-district daily extraction to the two
windows the experiment prices, so CI can run the harness without the
12 MB annual table (the make_smd_climatology.py pattern: commit the
small reduction, gitignore the big input).

  frost_1991_2020   the published model's window. NOT the published
                    model's INSTRUMENT: the live model reads a gridded
                    HadUK climatology through frost_from_metoffice and
                    IDWs it to district centroids, while this column is
                    the daily extraction integrated over each polygon.
                    They agree at +0.98 (means 40.5 vs 40.0 days), and
                    that difference is exactly why the harness prices
                    this column as its own variant - otherwise an era
                    comparison would confound the instrument with the
                    era, the mistake the climate scenario avoids by
                    using matched product pairs.
  frost_2006_2025   the recent-20-year window, the only re-aim
                    candidate that is both current and not
                    sample-starved (measure_frost_era.py).

Usage:  make_frost_climatology.py [--src <annual csv>] [--out <csv>]
"""

import argparse
import csv
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "data", "haduk_district_annual_1km.csv")
OUT = os.path.join(ROOT, "data", "frost_climatology.csv")
ERAS = {"frost_1991_2020": (1991, 2020), "frost_2006_2025": (2006, 2025)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    acc = defaultdict(lambda: defaultdict(list))
    with open(args.src, newline="") as fh:
        for r in csv.DictReader(fh):
            y = int(r["year"])
            for col, (a, b) in ERAS.items():
                if a <= y <= b:
                    acc[r["district"]][col].append(float(r["frost_days"]))

    rows = []
    for d in sorted(acc):
        row = {"district": d}
        for col, (a, b) in ERAS.items():
            got = acc[d][col]
            assert len(got) == b - a + 1, \
                f"{d}/{col}: {len(got)} of {b - a + 1} years"
            row[col] = round(float(np.mean(got)), 3)
        rows.append(row)
    if not rows:
        raise SystemExit(f"{args.src}: no rows in any era window")
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}: {len(rows)} polygons, {len(ERAS)} eras")


if __name__ == "__main__":
    main()
