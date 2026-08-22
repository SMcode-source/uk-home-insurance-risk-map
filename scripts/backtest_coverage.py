"""Does the model's distribution of simulated years contain the real ones?

Every number this model publishes is a statement about a distribution of
years, and until now nothing has ever checked that distribution against a
year that actually happened. This does, for the one part of the book
where the ABI publishes an annual series: weather.

The test is coverage, not point accuracy. The model is not trying to
reproduce 2025 - it is trying to describe the distribution 2025 was drawn
from. So the question is where each observed year falls in the simulated
distribution. If the observed years cluster in one tail, the level is
wrong. If they are spread across the middle, the model is doing its job
even where it misses a year badly.

What makes this worth running: the level anchors are a SINGLE year
(2025), while the systemic loadings W_* come from multi-decade series.
The mean is fitted to n=1 and the spread to n=45. If 2025 was an unusual
year, the model has enshrined an unusual year as its expectation - and
this script is what detects that.

Scope. The comparison is storm + flood only. The ABI's headline
"weather-related damage to homes" line also contains burst and frozen
pipes (2025 release, footnote 3), which sits in this model's escape-of-
water leg behind EOW_FREEZE_SHARE and cannot be split back out of the
year view. Storm and flood are published separately per year and map
one-to-one onto the model's `w_v` and `f_v`, so that is the comparison
that needs no assumption.

Observed years come from data/abi_annual.csv, which carries a source URL
and a published/derived flag per figure. Read HANDOFF before trusting the
2023 row: the ABI restates this series between releases and its own
publications disagree about which year held the record.

    .venv/Scripts/python.exe scripts/backtest_coverage.py

Output: data/backtest_coverage.json
"""

import csv
import json
import os
import sys

# seed_sweep parses sys.argv at import time; keep our own args away from it
_argv, sys.argv = sys.argv, sys.argv[:1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import build_model as bm
from seed_sweep import scored_frame
sys.argv = _argv


def observed():
    """Published storm and flood totals per year, GBP m."""
    path = os.path.join(bm.DATA, "abi_annual.csv")
    rows = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["metric"] in ("storm_homes", "flood_homes"):
                rows.setdefault(int(r["year"]), {})[r["metric"]] = (
                    float(r["value_gbp_m"]), r["basis"])
    out = []
    for y in sorted(rows):
        if len(rows[y]) == 2:
            s, sb = rows[y]["storm_homes"]
            f, fb = rows[y]["flood_homes"]
            basis = "published" if sb == fb == "published" else "part derived"
            out.append({"year": y, "storm": s, "flood": f,
                        "total": s + f, "basis": basis})
    return out


def place(sample, value):
    """Where does `value` sit in `sample`? Percentile and return period."""
    pct = 100.0 * float((sample < value).mean())
    n = len(sample)
    n_above = int((sample >= value).sum())
    n_below = int((sample <= value).sum())
    # return period of a year at least this extreme, in whichever
    # direction it is extreme
    if pct >= 50:
        rp = n / max(n_above, 1)
        side = "high"
    else:
        rp = n / max(n_below, 1)
        side = "low"
    return {"pct": round(pct, 2), "return_period": round(rp, 1),
            "side": side}


def main():
    g = scored_frame()
    bm.check_scored_columns(g)
    bm.calibrate_frequency(g)
    bm.calibrate_spatial(g)          # REQUIRED - see seed_sweep's docstring

    print(f"simulating {bm.N_SIM:,} years, seed {bm.RNG_SEED}...", flush=True)
    _, year = bm.simulate(g)

    # year["*_v"] are exposure-weighted national sums; dividing by
    # expo_total gives GBP per policy, and the calibration is per policy
    # over POLICIES - so this is the national annual bill in GBP m.
    n = float(year["expo_total"])
    scale = bm.POLICIES / n / 1e6
    storm = np.asarray(year["w_v"], dtype=float) * scale
    flood = np.asarray(year["f_v"], dtype=float) * scale
    sub = np.asarray(year["s_v"], dtype=float) * scale
    wxfl = storm + flood

    obs = observed()
    print()
    print("=" * 78)
    print("MODEL vs THE YEARS THAT ACTUALLY HAPPENED".center(78))
    print("=" * 78)
    print(f"model storm + flood, {bm.N_SIM:,} simulated years, GBP m")
    qs = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print("  " + "  ".join(f"p{q}={np.percentile(wxfl, q):,.0f}" for q in qs))
    print(f"  mean {wxfl.mean():,.0f}    sd {wxfl.std(ddof=1):,.0f}"
          f"    cv {wxfl.std(ddof=1) / wxfl.mean():.3f}")
    print()
    print(f"{'year':6}{'storm':>8}{'flood':>8}{'total':>8}"
          f"{'model pct':>11}{'return pd':>11}  basis")
    rows = []
    for o in obs:
        p = place(wxfl, o["total"])
        rows.append({**o, **p})
        rp = (f"1 in {p['return_period']:,.0f} {p['side']}"
              if p["return_period"] >= 2 else "typical")
        print(f"{o['year']:<6}{o['storm']:8,.0f}{o['flood']:8,.0f}"
              f"{o['total']:8,.0f}{p['pct']:10.1f}%{rp:>11}  {o['basis']}")

    ob = np.array([o["total"] for o in obs], dtype=float)
    print()
    print(f"  observed mean over {len(ob)} years   GBP {ob.mean():,.0f}m")
    print(f"  model mean                  GBP {wxfl.mean():,.0f}m")
    print(f"  model is {100 * (wxfl.mean() / ob.mean() - 1):+.0f}% "
          f"against the observed average")
    print()

    # The coverage statement. With this few years it is a direction, not
    # a test with power - say so rather than dressing it up.
    mid = sum(1 for r in rows if 25 <= r["pct"] <= 75)
    print("=" * 78)
    print("READING IT".center(78))
    print("=" * 78)
    print(f"  {mid} of {len(rows)} observed years land in the model's middle "
          f"half (p25-p75).")
    print("  With this few years that is a direction, not a test with")
    print("  power. What it can already show is systematic bias: if every")
    print("  observed year sits low in the distribution, the level is")
    print("  high, and no amount of extra years will change that sign.")
    print()
    below = sum(1 for r in rows if r["pct"] < 50)
    print(f"  {below} of {len(rows)} sit below the model's median.")
    if below == len(rows) and len(rows) >= 3:
        print("  ALL of them. The model's central year is more expensive")
        print("  than every year on record, which is what calibrating the")
        print("  level to a single record year would produce.")
    print()
    print("  Subsidence and the attritional legs are NOT tested here: the")
    print("  ABI publishes no annual series for theft, escape of water,")
    print("  fire or accidental damage, and subsidence has only two years")
    print("  in abi_annual.csv. This tests weather, and only weather.")

    out = {
        "generated_by": "scripts/backtest_coverage.py",
        "n_sim": int(bm.N_SIM),
        "seed": int(bm.RNG_SEED),
        "comparison": "storm + flood, national annual, GBP m",
        "model": {
            "mean": round(float(wxfl.mean()), 1),
            "sd": round(float(wxfl.std(ddof=1)), 1),
            "percentiles": {f"p{q}": round(float(np.percentile(wxfl, q)), 1)
                            for q in qs},
            "storm_mean": round(float(storm.mean()), 1),
            "flood_mean": round(float(flood.mean()), 1),
            "subsidence_mean": round(float(sub.mean()), 1),
        },
        "observed": rows,
        "observed_mean": round(float(ob.mean()), 1),
        "model_vs_observed_pct": round(
            100 * (float(wxfl.mean()) / float(ob.mean()) - 1), 1),
        "years_below_model_median": below,
        "years_in_middle_half": mid,
    }
    path = os.path.join(bm.DATA, "backtest_coverage.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
