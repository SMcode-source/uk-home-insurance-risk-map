"""Measure TAIL_FREQ_RATIO instead of asserting it.

`TAIL_FREQ_RATIO = 2.0` in build_model.py is the sole target
`calibrate_spatial` solves against. That solve fixes SPATIAL_SCALE, which
drives the year view, `tvar99_euler`, capital and the published premium.
It is the single number that sets how wide the tail is - and as of
2026-08-23 it appears in build_model.py and nowhere else in the repo: no
DATA_SOURCES entry, no README, no methodology page. The house rule is
that a parameter without a published anchor does not ship.

`data/history.csv` has been sitting in the repo with 35 years of per-year
national hazard drivers (ERA5 via Open-Meteo, 1990-2024) and has never
been used for anything but a chart. It is exactly the evidence this knob
needs.

What the target means. calibrate_spatial reports it as "1-in-100 year
claims Nx the mean year", so it is a ratio of CLAIM COUNTS, not of claim
cost. The proxy therefore has to be a driver of how MANY homes claim, not
how hard each is hit - which is why `storm_days` (days with gust >= 70
km/h, averaged over the 12 points) is the primary series here and
`max_gust` is not. A single violent gust hurts a few homes badly; a year
with many storm days puts many homes into claim.

The honest caveat, stated once. Claims are not linear in any of these.
The transforms below bracket the assumption rather than resolve it, and
35 years cannot observe a 1-in-100 directly - every figure past the
observed maximum is a fitted extrapolation. Read this as evidence about
whether 2.0 is the right ORDER, not as a replacement value to paste in.

    .venv/Scripts/python.exe scripts/tail_ratio_from_history.py

Output: data/tail_ratio.json
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy import stats
import build_model as bm

Q = 0.99            # the 1-in-100 the target names


def load():
    path = os.path.join(bm.DATA, "history.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows


def ratios(v):
    """1-in-100 / mean for one series, three ways."""
    v = np.asarray(v, dtype=float)
    m = v.mean()
    out = {"mean": float(m), "sd": float(v.std(ddof=1)),
           "cv": float(v.std(ddof=1) / m), "n": int(len(v)),
           "observed_max_over_mean": float(v.max() / m)}
    # lognormal, method of moments on the CV
    s2 = np.log(1.0 + out["cv"] ** 2)
    mu = np.log(m) - 0.5 * s2
    out["lognormal"] = float(
        np.exp(mu + stats.norm.ppf(Q) * np.sqrt(s2)) / m)
    # gamma, method of moments - a lighter tail than lognormal
    k = 1.0 / out["cv"] ** 2
    out["gamma"] = float(stats.gamma.ppf(Q, k, scale=m / k) / m)
    # GEV fitted to the series itself (not to block maxima - this IS an
    # annual series, so each point is already a year)
    # A GEV fitted to 35 points can land on an unbounded shape (c < 0),
    # which sends the 99th percentile to absurdity. Reject rather than
    # print it: a ratio in the millions is a failed fit, not a wide tail.
    try:
        c, loc, sc = stats.genextreme.fit(v)
        g = float(stats.genextreme.ppf(Q, c, loc=loc, scale=sc) / m)
        out["gev"] = g if 0.0 < g < 10.0 else None
        out["gev_shape"] = float(c)
    except Exception:
        out["gev"], out["gev_shape"] = None, None
    return out


def main():
    rows = load()
    yrs = np.array([int(r["year"]) for r in rows])
    sd = np.array([float(r["storm_days"]) for r in rows])
    gust = np.array([float(r["max_gust"]) for r in rows])
    rain = np.array([float(r["rain5d"]) for r in rows])

    print("=" * 80)
    print("MEASURING THE TAIL-WIDTH TARGET FROM 35 YEARS OF DRIVERS".center(80))
    print("=" * 80)
    print(f"  data/history.csv, {yrs.min()}-{yrs.max()}, {len(yrs)} years")
    print(f"  build_model.TAIL_FREQ_RATIO = {bm.TAIL_FREQ_RATIO}"
          f"   (asserted, no source in the repo)")
    print()

    # Is the primary series even stationary? A trend would make the
    # spread of the raw series the wrong thing to fit.
    sl, ic, r, p, se = stats.linregress(yrs, sd)
    print(f"  storm_days trend {sl:+.3f} days/yr, p = {p:.3f} -> "
          f"{'NOT stationary' if p < 0.05 else 'no significant trend'}")
    print()

    PROXIES = [
        ("storm_days", sd,
         "days with gust >= 70 km/h - the count driver, PRIMARY"),
        ("storm_days^1.5", sd ** 1.5,
         "mildly convex: worse days also bring more claims each"),
        ("storm_days^2", sd ** 2,
         "strongly convex - an upper bracket, not a belief"),
        ("rain5d", rain,
         "wettest 5-day total - the flood count driver"),
        ("max_gust", gust,
         "annual peak gust - severity driver, WRONG shape for a count "
         "target, shown to make that visible"),
    ]

    print(f"{'proxy':16}{'cv':>7}{'obs max':>9}{'lognorm':>9}"
          f"{'gamma':>8}{'gev':>8}   what it assumes")
    res = {}
    for name, v, why in PROXIES:
        r = ratios(v)
        res[name] = r
        gev = f"{r['gev']:.2f}" if r["gev"] is not None else "unbdd"
        print(f"{name:16}{r['cv']:7.3f}{r['observed_max_over_mean']:9.2f}"
              f"{r['lognormal']:9.2f}{r['gamma']:8.2f}{gev:>8}   {why}")
    print()
    print(f"  Columns are the 1-in-{1 / (1 - Q):.0f} value as a multiple of "
          f"the mean year.")
    print()

    prim = res["storm_days"]
    lo = min(prim["lognormal"], prim["gamma"])
    hi = max(prim["lognormal"], prim["gamma"],
             res["storm_days^1.5"]["lognormal"])
    print("=" * 80)
    print("READING IT".center(80))
    print("=" * 80)
    print(f"  On the primary count proxy the 1-in-100 year lands at "
          f"{lo:.2f}-{prim['lognormal']:.2f}x")
    print(f"  the mean year. Allowing mild convexity takes the top of the")
    print(f"  range to {hi:.2f}x. The shipped target is "
          f"{bm.TAIL_FREQ_RATIO:.2f}.")
    print()
    if lo <= bm.TAIL_FREQ_RATIO <= hi:
        print(f"  So {bm.TAIL_FREQ_RATIO:.2f} is INSIDE the measured range. The knob is")
        print("  undocumented, not wrong. It needs a DATA_SOURCES entry")
        print("  citing this measurement - not a different value.")
    else:
        print(f"  So {bm.TAIL_FREQ_RATIO:.2f} is OUTSIDE the measured range "
              f"({lo:.2f}-{hi:.2f}).")
        print("  That is a model change and needs an experiment branch.")
    print()
    print("  What this does NOT establish: that storm days translate into")
    print("  claim counts one-for-one. A claims triangle would settle it;")
    print("  HANDOFF already names that as the highest-value missing")
    print("  dataset, and this is another thing it would buy.")
    print()
    print("  Note the last row. max_gust has a CV of "
          f"{res['max_gust']['cv']:.3f} and would")
    print(f"  imply a 1-in-100 at only {res['max_gust']['lognormal']:.2f}x. "
          f"Picking it would halve the")
    print("  tail. The proxy choice matters more than the fitted")
    print("  distribution, which is why it is argued for above and not")
    print("  just chosen.")

    out = {
        "generated_by": "scripts/tail_ratio_from_history.py",
        "source": "data/history.csv (ERA5 via Open-Meteo, 1990-2024)",
        "quantile": Q,
        "shipped_tail_freq_ratio": float(bm.TAIL_FREQ_RATIO),
        "primary_proxy": "storm_days",
        "storm_days_trend_per_yr": round(float(sl), 4),
        "storm_days_trend_p": round(float(p), 4),
        "proxies": res,
        "measured_range_primary": [round(lo, 3), round(hi, 3)],
        "shipped_inside_range": bool(lo <= bm.TAIL_FREQ_RATIO <= hi),
    }
    path = os.path.join(bm.DATA, "tail_ratio.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
