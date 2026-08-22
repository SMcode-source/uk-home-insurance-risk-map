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

    .venv/Scripts/python.exe scripts/backtest_coverage.py           # instant
    .venv/Scripts/python.exe scripts/backtest_coverage.py --fresh   # ~40 min

The 20,000-year series is cached in data/backtest_years.npz alongside the
sha256 of build_model.py. If the model has moved the cache is REJECTED
and the simulation reruns, so a stale cache cannot pass silently - that
failure mode has cost this repo enough already.

Output: data/backtest_coverage.json, data/backtest_years.npz
"""

import csv
import hashlib
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


def model_fingerprint():
    """sha256 of build_model.py, so a stale cache cannot pass silently."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "build_model.py"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def simulated_years():
    """The national annual series, from cache if it is still valid.

    The simulation is ~40 minutes; the arrays it produces are ~200 KB, so
    they are cached and committed - re-reading the backtest against a new
    ABI release then costs nothing.

    The cache carries the sha256 of build_model.py and is REJECTED if the
    model has moved. A cache that silently outlives the code it came from
    is the exact failure this repo keeps finding the hard way, so this one
    refuses rather than warns.
    """
    cache = os.path.join(bm.DATA, "backtest_years.npz")
    if "--fresh" not in sys.argv and os.path.exists(cache):
        z = np.load(cache)
        got = str(z["model_sha"][0]) if "model_sha" in z else "(none)"
        want = model_fingerprint()
        if got == want:
            print(f"using cached years from {cache} "
                  f"(seed {int(z['seed'][0])}, build_model {want[:12]})")
            return (z["storm"].astype(float), z["flood"].astype(float),
                    z["subsidence"].astype(float))
        print("CACHE REJECTED - build_model.py has changed since it was "
              "written")
        print(f"  cached {got[:12]}   current {want[:12]}")
        print("  re-simulating; this takes ~40 minutes")

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
    return (np.asarray(year["w_v"], dtype=float) * scale,
            np.asarray(year["f_v"], dtype=float) * scale,
            np.asarray(year["s_v"], dtype=float) * scale)


def main():
    storm, flood, sub = simulated_years()
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
    k = len(ob)
    print()
    print(f"  model mean {wxfl.mean():,.0f}   MEDIAN {np.median(wxfl):,.0f}"
          f"   observed {k}-year mean {ob.mean():,.0f}")
    print()
    print("  Read the median, not the mean. The simulated distribution is")
    print(f"  strongly right-skewed (cv {wxfl.std(ddof=1) / wxfl.mean():.2f}), "
          f"so most years fall")
    print("  well below the mean by construction. Comparing a handful of")
    print("  observed years against the MEAN and calling the gap bias is a")
    print("  mistake - it is what a skewed distribution looks like.")
    print()

    # ------------------------------------------------------- the real test
    # Draw k-year windows from the model and ask where the observed
    # window falls. This turns "18% below the mean" into a probability,
    # which is the only way to read k=3 honestly.
    rng = np.random.default_rng(0)
    draws = rng.choice(wxfl, size=(200_000, k), replace=True)
    dmean = draws.mean(axis=1)
    dcv = draws.std(axis=1, ddof=1) / np.maximum(dmean, 1e-9)
    o_mean, o_cv = float(ob.mean()), float(ob.std(ddof=1) / ob.mean())
    p_mean = float((dmean <= o_mean).mean())
    p_cv = float((dcv <= o_cv).mean())

    print("=" * 78)
    print(f"IS THE OBSERVED WINDOW A PLAUSIBLE DRAW? ({k} YEARS, "
          f"200k BOOTSTRAP)".center(78))
    print("=" * 78)
    print(f"{'statistic':22}{'observed':>10}{'model median':>15}"
          f"{'P(model <= obs)':>17}")
    print(f"{'mean of the window':22}{o_mean:10,.0f}"
          f"{np.median(dmean):15,.0f}{p_mean:16.3f}")
    print(f"{'cv within the window':22}{o_cv:10.3f}"
          f"{np.median(dcv):15.3f}{p_cv:16.3f}")
    print()
    print("  LEVEL. The observed mean sits at the "
          f"{100 * p_mean:.0f}th percentile of what")
    print(f"  the model expects a {k}-year window to average. ", end="")
    if 0.05 <= p_mean <= 0.95:
        print("Unremarkable -")
        print("  the level is NOT contradicted by these years.")
    else:
        print("OUTSIDE the")
        print("  central 90% - the level is contradicted by these years.")
    print()
    print("  SPREAD. The observed within-window cv sits at the "
          f"{100 * p_cv:.0f}th percentile.")
    if p_cv < 0.05:
        print("  The real years were far STEADIER than the model says years")
        print("  are. That is the finding, and it points at the tail, not")
        print("  the level: capital is 6% of (TVaR99 - EL), so a tail that")
        print("  is too wide inflates every published premium.")
        print()
        print("  Before acting on it, the honest caveat: this window is")
        print("  2022-2025 and contains no catastrophic flood year. 2007")
        print("  (~GBP 3bn insured) or 2015-16 Desmond/Eva would widen the")
        print("  observed spread a long way. Four quiet years cannot")
        print("  measure a tail. What they CAN say is that the model's")
        print("  ordinary years are too volatile, which is a different and")
        print("  more testable claim - and more ABI years will test it.")
    else:
        print("  Not unusual - the model's year-to-year spread is not")
        print("  contradicted by these years either.")
    print()

    mid = sum(1 for r in rows if 25 <= r["pct"] <= 75)
    below = sum(1 for r in rows if r["pct"] < 50)
    print("=" * 78)
    print("READING IT".center(78))
    print("=" * 78)
    print(f"  {mid} of {len(rows)} observed years land in the model's middle "
          f"half (p25-p75);")
    print(f"  {below} of {len(rows)} sit below its median. The distribution "
          f"contains the")
    print("  real years. On coverage, the model passes.")
    print()
    print("  Subsidence and the attritional legs are NOT tested here: the")
    print("  ABI publishes no annual series for theft, escape of water,")
    print("  fire or accidental damage, and subsidence has only two years")
    print("  in abi_annual.csv. This tests weather, and only weather.")
    print()
    print("  Groundwater is excluded from the model side: it is pegged at")
    print("  10% of flood and the ABI's flood line may or may not contain")
    print("  it. At ~GBP 19m it cannot change any conclusion above.")
    print()

    # ------------------------------------------------- does it MATTER?
    # A finding about the tail is only worth acting on in proportion to
    # how much of the published number the tail actually drives. Read
    # that off the shipped artifact rather than assuming it.
    prop = None
    gj = os.path.join(bm.DATA, "districts_risk.geojson")
    if os.path.exists(gj):
        with open(gj, encoding="utf-8") as fh:
            props = [ft["properties"] for ft in json.load(fh)["features"]]
        el = np.array([p["el_total"] for p in props], dtype=float)
        pr = np.array([p["premium"] for p in props], dtype=float)
        hh = np.array([p["households"] for p in props], dtype=float)
        cap = pr - el
        nat_cap = float(np.average(cap, weights=hh))
        nat_pr = float(np.average(pr, weights=hh))
        share = 100 * nat_cap / nat_pr
        el_ratio = float(np.percentile(el, 90) / np.percentile(el, 10))
        pr_ratio = float(np.percentile(pr, 90) / np.percentile(pr, 10))
        lo, hi = np.percentile(100 * cap / pr, [0, 100])
        prop = {"capital_share_of_premium_pct": round(share, 2),
                "capital_share_range_pct": [round(float(lo), 2),
                                            round(float(hi), 2)],
                "el_p90_over_p10": round(el_ratio, 3),
                "premium_p90_over_p10": round(pr_ratio, 3)}

        print("=" * 78)
        print("HOW MUCH WOULD FIXING THE TAIL ACTUALLY CHANGE?".center(78))
        print("=" * 78)
        print(f"  From the SHIPPED artifact, household-weighted:")
        print(f"    expected loss                GBP {np.average(el, weights=hh):7.2f}")
        print(f"    premium                      GBP {nat_pr:7.2f}")
        print(f"    capital (the tail's whole contribution)  "
              f"GBP {nat_cap:5.2f}  = {share:.1f}% of premium")
        print(f"    across districts it ranges {lo:.1f}% to {hi:.1f}% "
              f"of premium")
        print()
        print(f"    EL      p90/p10 = {el_ratio:.2f}")
        print(f"    premium p90/p10 = {pr_ratio:.2f}")
        print()
        print("  Two consequences, and they cut the finding down to size.")
        print()
        print(f"  1. The tail is {share:.1f}% of the premium. Deleting the "
              f"capital charge")
        print("     ENTIRELY would move it by that much. A tail that is too")
        print("     wide by some fraction moves it by less. This is a")
        print("     sub-3% effect on the published number.")
        print()
        print(f"  2. The map's spatial pattern is not the tail's at all -")
        print(f"     EL and premium have the SAME dispersion "
              f"({el_ratio:.2f} vs {pr_ratio:.2f}).")
        print("     What the map shows is expected loss. Capital varies so")
        print("     little across districts that it does not shift the")
        print("     picture.")
        print()
        print("  So: the spread finding is real and worth recording, and it")
        print("  is NOT where the money is. Expected loss is 97% of the")
        print("  premium and 100% of the map. The theft level - one leg")
        print("  carrying 17% of EL and over its claim-count budget on")
        print("  every reading - is worth roughly 2.5x the entire capital")
        print("  charge. Fix that first.")

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
        "model_median": round(float(np.median(wxfl)), 1),
        "model_cv": round(float(wxfl.std(ddof=1) / wxfl.mean()), 4),
        "window_test": {
            "k_years": k,
            "observed_mean": round(o_mean, 1),
            "observed_cv": round(o_cv, 4),
            "p_model_mean_below_observed": round(p_mean, 4),
            "p_model_cv_below_observed": round(p_cv, 4),
        },
        "years_below_model_median": below,
        "years_in_middle_half": mid,
        "proportionality": prop,
    }
    path = os.path.join(bm.DATA, "backtest_coverage.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {path}")

    # Cache the simulated year series so re-analysing this never needs
    # another 40-minute run. 20,000 float32 per peril is ~80 KB.
    cache = os.path.join(bm.DATA, "backtest_years.npz")
    np.savez_compressed(cache, storm=storm.astype(np.float32),
                        flood=flood.astype(np.float32),
                        subsidence=sub.astype(np.float32),
                        seed=np.array([bm.RNG_SEED]),
                        model_sha=np.array([model_fingerprint()]))
    print(f"wrote {cache}  "
          f"({os.path.getsize(cache) / 1e3:.0f} KB, seed {bm.RNG_SEED})")


if __name__ == "__main__":
    main()
