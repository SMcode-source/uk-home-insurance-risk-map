"""The freeze LEVEL question, measured: does the frost map need re-aiming?

Gate 2 closed the freeze GEOGRAPHY half - no cold-spell or thaw index
reorders the map against plain air-frost days (Spearman +0.97..+0.99 at
both resolutions). What it left open was the LEVEL: frost days fell
about 20% between climate eras while the map stayed rank-stable, so
should the model's frost climatology - and with it EOW_FREEZE_SHARE -
be aimed at a more recent window than 1991-2020?

This script answers it from the 66-year per-district daily extraction
(1960-2025, gitignored, built by haduk_district_daily.py at 5 km and
haduk_1km_stream.py at 1 km).

WHY THE LEVEL CANNOT MATTER, and the one thing that can. The model
uses frost through

    eow_rate = ABI_TARGET_FREQ["eow"] * ((1 - share) + share * frost/wmean(frost))

and that division by the exposure-weighted mean removes the level
EXACTLY. A frost decline that is uniform in proportion is invisible to
the premium no matter how large it is. Only two things can move it:
the RELATIVITY map (frost/wmean per district), and the SHARE. So the
re-aim question is not "has frost fallen" - it has, and this script
measures by how much - but "has the SHAPE of the frost map changed by
more than the noise of estimating it".

THE CONTROL IS THE POINT. A shorter, more recent window is a noisier
estimate of a climatology as well as a more current one, and the two
are easy to confuse: any re-aimed window will show SOME relativity
movement, and it will look like signal. So every era comparison here is
run beside within-era controls that hold the climate fixed and vary
only the sample - odd vs even years of one era, and two disjoint
windows inside the stable era. A candidate window earns the word
"signal" only by moving the map MORE than those controls do.

Usage:
  measure_frost_era.py [--src data/haduk_district_annual_1km.csv]
                       [--geojson data/districts_risk.geojson]
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

# The published model's window, and the candidates for re-aiming it.
BASE_ERA = (1991, 2020)
CANDIDATES = [("1961-1990 (the previous normal)", (1961, 1990)),
              ("1996-2025 (normal, slid 5 years)", (1996, 2025)),
              ("2006-2025 (recent 20 years)", (2006, 2025)),
              ("2016-2025 (recent decade)", (2016, 2025))]
# Same climate, different sample: whatever these move is not a re-aim.
CONTROLS = [("odd vs even years of 1991-2020",
             [y for y in range(1991, 2021) if y % 2],
             [y for y in range(1991, 2021) if not y % 2]),
            ("1991-2005 vs 2006-2020 (15y halves)",
             list(range(1991, 2006)), list(range(2006, 2021))),
            ("1991-2000 vs 2001-2010 (10y windows)",
             list(range(1991, 2001)), list(range(2001, 2011)))]

# build_model.EOW_FREEZE_SHARE, mirrored so the report can show what each
# relativity does to the number the model actually multiplies.
EOW_FREEZE_SHARE = 0.31


def load(src, geojson):
    with open(geojson) as fh:
        hh = {f["properties"]["name"]: f["properties"]["households"]
              for f in json.load(fh)["features"]}
    frost = defaultdict(dict)
    with open(src, newline="") as fh:
        for r in csv.DictReader(fh):
            frost[r["district"]][int(r["year"])] = float(r["frost_days"])
    names = sorted(set(frost) & set(hh))
    if not names:
        raise SystemExit(f"{src} and {geojson} share no district names "
                         "- wrong grain?")
    return names, np.array([hh[n] for n in names], float), frost


def clim(frost, names, years):
    """Per-district mean frost days over `years`, and its relativity."""
    return np.array([np.mean([frost[n][y] for y in years]) for n in names])


def compare(tag, va, vb, w):
    """One relativity comparison, reported the way the model would feel it."""
    ra, rb = va / np.average(va, weights=w), vb / np.average(vb, weights=w)
    d = ra / rb - 1.0
    # what the frame's eow_rate multiplier actually does under each map
    ea = (1 - EOW_FREEZE_SHARE) + EOW_FREEZE_SHARE * ra
    eb = (1 - EOW_FREEZE_SHARE) + EOW_FREEZE_SHARE * rb
    de = np.abs(ea / eb - 1.0)
    print(f"  {tag:38s} rho {spearmanr(ra, rb).statistic:+.4f}  "
          f"|drel| p95 {np.percentile(np.abs(d), 95):.3f}  "
          f">10%: {int((np.abs(d) > 0.10).sum()):4d}  "
          f"|d eow_rate| max {de.max():.4f}")
    return float(np.percentile(np.abs(d), 95)), int((np.abs(d) > 0.10).sum())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--geojson", default=GEOJSON)
    args = ap.parse_args()

    names, w, frost = load(args.src, args.geojson)
    years = sorted({y for d in frost.values() for y in d})
    print(f"{len(names)} polygons, {years[0]}-{years[-1]} "
          f"({len(years)} years), from {os.path.basename(args.src)}\n")

    # 1. THE LEVEL: is the decline real, and how fast?
    nat = np.array([np.average([frost[n][y] for n in names], weights=w)
                    for y in years])
    lr = linregress(years, nat)
    print("LEVEL - the national household-weighted frost series")
    print(f"  trend {lr.slope:+.3f} days/yr (p={lr.pvalue:.2g}), "
          f"{lr.slope * 10:+.2f} days/decade = "
          f"{lr.slope * 10 / nat.mean():+.1%} of the mean per decade")
    base = clim(frost, names, range(BASE_ERA[0], BASE_ERA[1] + 1))
    bl = np.average(base, weights=w)
    for tag, (a, b) in CANDIDATES:
        v = clim(frost, names, range(a, b + 1))
        print(f"  {tag:34s} {np.average(v, weights=w):6.2f} days "
              f"({np.average(v, weights=w) / bl - 1:+6.1%} vs "
              f"{BASE_ERA[0]}-{BASE_ERA[1]}'s {bl:.2f})")
    print("  ...and ALL of it cancels: eow_rate divides frost by its own\n"
          "     exposure-weighted mean, so only the shape below can price.\n")

    # 2. THE CONTROLS, first - so the candidates are read against them.
    #
    # Sample size matters and is easy to cheat on: a 10-year window is a
    # noisier estimate of the SAME climatology than a 30-year one, so a
    # short re-aimed window will always look like it moved the map.
    # Each control is therefore labelled with its per-side sample count
    # and each candidate is judged against the control with the nearest
    # count at or below its own - which is conservative for the long
    # candidates, because fewer samples means MORE noise in the control.
    print("SHAPE - controls (same climate, different sample)")
    floors = []
    for tag, ya, yb in CONTROLS:
        n = min(len(ya), len(yb))
        p95, _cnt = compare(f"{tag} [n={n}]", clim(frost, names, ya),
                            clim(frost, names, yb), w)
        floors.append((n, p95))
    floors.sort()
    print()

    print(f"SHAPE - candidate windows vs the published {BASE_ERA[0]}-"
          f"{BASE_ERA[1]}")
    for tag, (a, b) in CANDIDATES:
        n = b - a + 1
        p95, _cnt = compare(f"{tag} [n={n}]",
                            clim(frost, names, range(a, b + 1)), base, w)
        # nearest control at or below this candidate's sample count; if the
        # candidate is longer than every control, the noisiest control is
        # still an over-estimate of its noise, which only helps the verdict.
        usable = [f for f in floors if f[0] <= n] or floors
        cn, cf = usable[-1]
        if p95 > cf:
            verdict = (f"ABOVE the n={cn} control ({cf:.3f}) - "
                       "the only candidate that could be signal")
        else:
            verdict = (f"inside the n={cn} control ({cf:.3f}) - "
                       "re-aiming here buys noise, not currency")
        print(f"  {'':38s} -> {verdict}")


if __name__ == "__main__":
    main()
