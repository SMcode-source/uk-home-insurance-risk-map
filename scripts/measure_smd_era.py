"""The DROUGHT re-aim question, measured: does the SMD map need re-aiming?

`measure_frost_era.py` asked this of the freeze leg on 2026-08-31 and
answered no: frost days fell about 20% between climate eras, but the
model divides frost by its own exposure-weighted mean, so the level
cancels exactly, and every re-aimed window moved the SHAPE of the map by
less than a same-climate control does. The identical question was never
put to the other temperature-driven leg.

It should have been. Subsidence frequency is priced through

    sub_rel = (1 - SUB_DROUGHT_SHARE)
              + SUB_DROUGHT_SHARE * cwd_yr / wmean(cwd_yr)

which is the same construction as `eow_rate`, on a climatology built
from the same window (`make_smd_climatology.py`: 1991-2020, "to match
the window of every other climatology the model carries"). And the
drought integral is not merely trending, it is trending UPWARD and
significantly: +0.93 mm/yr, p = 0.036, on the household-weighted
national series - the opposite sign to frost and, unlike frost, a
direction that raises the peril it drives.

So: the level cancels here too, exactly as it does for freeze. The only
thing that can price is whether the SHAPE of the drought map has moved
by more than the noise of estimating it from a shorter window. This
script measures that, against the same within-era controls the frost
answer was held to, so the two legs are judged by one standard.

Reads the gitignored 66-year per-district table (1960-2025) that
`make_smd_climatology.py` reduces; nothing here is a model input.

Usage:
  measure_smd_era.py [--src data/haduk_district_annual_1km.csv]
                     [--geojson data/districts_risk.geojson]
                     [--column cwd_yr_max_mm]
"""

import argparse
import csv
import json
import os
from collections import defaultdict

import numpy as np
from scipy.stats import linregress, spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "data", "haduk_district_annual_1km.csv")
GEOJSON = os.path.join(ROOT, "data", "districts_risk.geojson")

BASE_ERA = (1991, 2020)
CANDIDATES = [("1961-1990 (the previous normal)", (1961, 1990)),
              ("1996-2025 (normal, slid 5 years)", (1996, 2025)),
              ("2006-2025 (recent 20 years)", (2006, 2025)),
              ("2016-2025 (recent decade)", (2016, 2025))]
CONTROLS = [("odd vs even years of 1991-2020",
             [y for y in range(1991, 2021) if y % 2],
             [y for y in range(1991, 2021) if not y % 2]),
            ("1991-2005 vs 2006-2020 (15y halves)",
             list(range(1991, 2006)), list(range(2006, 2021))),
            ("1991-2000 vs 2001-2010 (10y windows)",
             list(range(1991, 2001)), list(range(2001, 2011)))]

# build_model.SUB_DROUGHT_SHARE, mirrored so the report can show what
# each relativity does to the number the model actually multiplies.
SUB_DROUGHT_SHARE = 0.565


def load(src, geojson, column):
    with open(geojson) as fh:
        hh = {f["properties"]["name"]: f["properties"]["households"]
              for f in json.load(fh)["features"]}
    vals = defaultdict(dict)
    with open(src, newline="") as fh:
        rdr = csv.DictReader(fh)
        if column not in (rdr.fieldnames or []):
            raise SystemExit(f"{src} has no column {column!r}; it has "
                             f"{rdr.fieldnames}")
        for r in rdr:
            v = r[column]
            if v not in ("", "nan"):
                vals[r["district"]][int(r["year"])] = float(v)
    names = sorted(set(vals) & set(hh))
    if not names:
        raise SystemExit(f"{src} and {geojson} share no district names "
                         "- wrong grain?")
    return names, np.array([hh[n] for n in names], float), vals


def clim(vals, names, years):
    years = list(years)
    return np.array([np.mean([vals[n][y] for y in years if y in vals[n]])
                     for n in names])


def compare(tag, va, vb, w, share):
    """One relativity comparison, reported the way the model would feel it."""
    ra, rb = va / np.average(va, weights=w), vb / np.average(vb, weights=w)
    d = ra / rb - 1.0
    ea = (1 - share) + share * ra
    eb = (1 - share) + share * rb
    de = np.abs(ea / eb - 1.0)
    print(f"  {tag:38s} rho {spearmanr(ra, rb).statistic:+.4f}  "
          f"|drel| p95 {np.percentile(np.abs(d), 95):.3f}  "
          f">10%: {int((np.abs(d) > 0.10).sum()):4d}  "
          f"|d sub_rel| max {de.max():.4f}")
    return float(np.percentile(np.abs(d), 95)), int((np.abs(d) > 0.10).sum())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--geojson", default=GEOJSON)
    ap.add_argument("--column", default="cwd_yr_max_mm",
                    help="cwd_yr_max_mm (the shipped index) or "
                         "smd_jja_mean_mm (the Gate 2 alternative)")
    ap.add_argument("--share", type=float, default=SUB_DROUGHT_SHARE)
    args = ap.parse_args(argv)

    names, w, vals = load(args.src, args.geojson, args.column)
    years = sorted({y for d in vals.values() for y in d})
    print(f"{len(names)} polygons, {years[0]}-{years[-1]} ({len(years)} years), "
          f"column {args.column}, share {args.share}\n")

    nat = np.array([np.average([vals[n][y] for n in names], weights=w)
                    for y in years])
    lr = linregress(years, nat)
    print("LEVEL - the national household-weighted series")
    print(f"  trend {lr.slope:+.3f} mm/yr (p={lr.pvalue:.2g}), "
          f"{lr.slope * 10:+.1f} mm/decade = "
          f"{lr.slope * 10 / nat.mean():+.1%} of the mean per decade")
    base = clim(vals, names, range(BASE_ERA[0], BASE_ERA[1] + 1))
    bl = np.average(base, weights=w)
    for tag, (a, b) in CANDIDATES:
        v = clim(vals, names, range(a, b + 1))
        print(f"  {tag:34s} {np.average(v, weights=w):7.2f} mm "
              f"({np.average(v, weights=w) / bl - 1:+6.1%} vs "
              f"{BASE_ERA[0]}-{BASE_ERA[1]}'s {bl:.2f})")
    print("  ...and ALL of it cancels: sub_rel divides the index by its own\n"
          "     exposure-weighted mean, so only the shape below can price.\n")

    print("SHAPE - controls (same climate, different sample)")
    floors = []
    for tag, ya, yb in CONTROLS:
        n = min(len(ya), len(yb))
        p95, _ = compare(f"{tag} [n={n}]", clim(vals, names, ya),
                         clim(vals, names, yb), w, args.share)
        floors.append((n, p95))
    floors.sort()
    print()

    print(f"SHAPE - candidate windows vs the published {BASE_ERA[0]}-"
          f"{BASE_ERA[1]}")
    verdicts = []
    for tag, (a, b) in CANDIDATES:
        n = b - a + 1
        p95, _ = compare(f"{tag} [n={n}]", clim(vals, names, range(a, b + 1)),
                         base, w, args.share)
        usable = [f for f in floors if f[0] <= n] or floors
        cn, cf = usable[-1]
        if p95 > cf:
            verdict = (f"ABOVE the n={cn} control ({cf:.3f}) - "
                       "the only candidate that could be signal")
        else:
            verdict = (f"inside the n={cn} control ({cf:.3f}) - "
                       "re-aiming here buys noise, not currency")
        verdicts.append((tag, p95, cf, p95 > cf))
        print(f"  {'':38s} -> {verdict}")

    print()
    signal = [t for t, _, _, s in verdicts if s]
    if signal:
        print(f"VERDICT: {len(signal)} candidate window(s) move the map more "
              f"than a same-climate control does:")
        for t in signal:
            print(f"  - {t}")
        print("  A re-aim is arguable for those, and is the user's call.")
    else:
        print("VERDICT: no candidate window moves the drought map more than "
              "a same-climate\n  control does. The level has moved and the "
              "level cannot price; the shape has\n  not moved beyond the "
              "noise of measuring it. Do not re-aim - the same answer\n"
              "  the freeze leg got on 2026-08-31, now on the same standard.")


if __name__ == "__main__":
    main()
