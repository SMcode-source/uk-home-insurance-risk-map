"""Gate 4: the year view as a claim COUNT and a claim VALUE.

The published year view answers "what does a bad year cost?" It does not
answer the question behind it: **is a bad year expensive because more
homes claim, or because each claim costs more?** Those have different
consequences - the first is an exposure story, the second a severity
story - and the model already contains the answer.

WHY THE PUBLISHED FILE CANNOT BE USED TO DERIVE IT. `year_analysis`
emits `inc_<peril>_pct` rounded to 2 dp of a PERCENT. The smallest step
is 0.01%, about 1,550 claims across a 15.5m book, so dividing `mean_*`
by it to recover a cost per claim inherits (measured 2026-08-29):

    weather        0.6 - 0.9%   usable
    flood          2.6 - 12.5%  marginal to unusable
    subsidence     2.1 -  7.1%  marginal to unusable
    groundwater     25 -  50%   unusable; incidence rounds to
                                0.00 / 0.01 / 0.01 / 0.02 across buckets

That is a resolution floor, not sampling noise: more simulated years
would not move it. So `year_analysis` now emits both quantities from the
UNROUNDED arrays - `claims_<peril>_per_100k` and
`cost_<peril>_per_claim` - and this script is what reads them back.

It runs ONE simulation off one scored frame, which is the cheapest thing
that can produce a year view at all: a full rebuild regenerates the
district file and the site as well, and none of that is needed to answer
this. Nothing here is written back to the repo.

Usage:
  year_claim_view.py                 # full N_SIM
  year_claim_view.py --nsim 4000     # quick shape check, NOT for quoting
"""

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "data", "year_claim_view.json")

# The ABI's published average claim, for the perils that have one. These
# are the model's own anchors (build_model.ABI), repeated here only so the
# table can show what the simulated cost per claim is being read against.
ABI_AVG = {"wx": ("storm", 2_450), "fl": ("flood", 30_000),
           "sub": ("subsidence", 17_264), "gw": ("groundwater", 20_000)}


class _Scored(Exception):
    """Sentinel: abort build_model.main() once the scored frame exists."""


def scored_frame():
    grab = {}
    real = bm.simulate

    def stub(df):
        grab["gdf"] = df
        raise _Scored

    bm.simulate = stub
    try:
        bm.main()
    except _Scored:
        pass
    finally:
        bm.simulate = real
    if "gdf" not in grab:
        raise SystemExit("build_model.main() never reached simulate()")
    return grab["gdf"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nsim", type=int, default=None)
    ap.add_argument("--batch", type=int, default=None)
    args = ap.parse_args()
    if args.nsim:
        bm.N_SIM = args.nsim
        print(f"*** N_SIM overridden to {args.nsim:,} - NOT quotable ***",
              flush=True)
    if args.batch:
        bm.BATCH = args.batch

    t0 = time.time()
    print("scoring once...", flush=True)
    gdf = scored_frame()
    bm.calibrate_frequency(gdf)
    bm.calibrate_spatial(gdf)
    print(f"  scored {len(gdf)} districts in "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)

    print("simulating...", flush=True)
    _sim, year = bm.simulate(gdf)
    ya = bm.year_analysis(year, len(gdf))
    print(f"  simulated in {(time.time() - t0) / 60:.1f} min", flush=True)

    pol = bm.POLICIES
    buckets = {b["label"]: b for b in ya["buckets"]}
    typ = buckets["typical"]

    print("\n" + "=" * 88, flush=True)
    print("Is a bad year MORE CLAIMS or DEARER CLAIMS?  "
          f"(x vs the typical year, {pol / 1e6:.1f}m policies)", flush=True)
    print("=" * 88, flush=True)
    for key, (name, abi) in ABI_AVG.items():
        print(f"\n{name}  (ABI average claim GBP{abi:,})", flush=True)
        print(f"  {'bucket':<14}{'claims/yr':>12}{'count x':>10}"
              f"{'GBP/claim':>12}{'value x':>10}{'cost/policy':>13}",
              flush=True)
        tn = typ[f"claims_{key}_per_100k"]
        tv = typ[f"cost_{key}_per_claim"]
        for b in ya["buckets"]:
            n100k = b[f"claims_{key}_per_100k"]
            cost = b[f"cost_{key}_per_claim"]
            claims = n100k / 1e5 * pol
            cx = (n100k / tn) if tn else float("nan")
            vx = (cost / tv) if (tv and cost) else float("nan")
            print(f"  {b['label']:<14}{claims:>12,.0f}{cx:>9.2f}x"
                  f"{(cost if cost is not None else 0):>12,.0f}"
                  f"{vx:>9.2f}x{b[f'mean_{key}']:>13.2f}", flush=True)

    print("\nAll four vine perils together:", flush=True)
    print(f"  {'bucket':<14}{'claims/yr':>12}{'count x':>10}"
          f"{'GBP/claim':>12}{'value x':>10}{'cost/policy':>13}", flush=True)
    tn, tv = typ["claims_total_per_100k"], typ["cost_total_per_claim"]
    for b in ya["buckets"]:
        claims = b["claims_total_per_100k"] / 1e5 * pol
        print(f"  {b['label']:<14}{claims:>12,.0f}"
              f"{b['claims_total_per_100k'] / tn:>9.2f}x"
              f"{b['cost_total_per_claim']:>12,.0f}"
              f"{b['cost_total_per_claim'] / tv:>9.2f}x"
              f"{b['mean_total']:>13.2f}", flush=True)

    # The decomposition, stated as the ratio it is. A bad year's cost is
    # count x value, so the two multipliers must multiply to the cost one.
    print("\nDecomposition check (count x  *  value x  ==  cost x):",
          flush=True)
    for b in ya["buckets"]:
        cx = b["claims_total_per_100k"] / tn
        vx = b["cost_total_per_claim"] / tv
        kx = b["mean_total"] / typ["mean_total"]
        print(f"  {b['label']:<14}{cx:>7.3f} x {vx:>6.3f} = {cx * vx:>6.3f}"
              f"   vs cost ratio {kx:>6.3f}"
              f"   ({100 * (cx * vx / kx - 1):+.2f}%)", flush=True)

    # The value multiplier is two effects, and they answer different
    # questions. MIX: cheap storm claims give way to dear flood and
    # subsidence ones, which raises the average claim without any single
    # peril getting worse. SEVERITY: what is left, the perils themselves
    # getting dearer. Holding every peril at its typical-year cost per
    # claim and moving only the mix separates them.
    print(flush=True)
    print("Value x split into mix and severity:", flush=True)
    print(f"  {'bucket':<14}{'value x':>10}{'mix-only':>11}"
          f"{'mix x':>9}{'severity x':>13}", flush=True)
    tvc = typ["cost_total_per_claim"]
    for b in ya["buckets"]:
        n = {k: b[f"claims_{k}_per_100k"] for k in ABI_AVG}
        tot = sum(n.values())
        if not (tot and tvc):
            continue
        mix = sum(n[k] * typ[f"cost_{k}_per_claim"] for k in ABI_AVG) / tot
        vx, mx = b["cost_total_per_claim"] / tvc, mix / tvc
        print(f"  {b['label']:<14}{vx:>9.2f}x{mix:>11,.0f}"
              f"{mx:>8.2f}x{vx / mx:>12.2f}x", flush=True)

    print(flush=True)
    print("Share of all claims, by peril:", flush=True)
    print(f"  {'bucket':<14}" + "".join(f"{k:>9}" for k in ABI_AVG),
          flush=True)
    for b in ya["buckets"]:
        tot = b["claims_total_per_100k"]
        print(f"  {b['label']:<14}" + "".join(
            f"{100 * b[f'claims_{k}_per_100k'] / tot:>8.1f}%"
            for k in ABI_AVG), flush=True)

    print(f"\nFor scale, the ABI's 2025 actual: 560,000 home claims across "
          f"ALL perils at GBP6,000 average.\nThe four vine perils are a "
          f"SUBSET of that, so the total above must come in under it.",
          flush=True)

    with open(OUT, "w") as fh:
        json.dump(ya, fh, indent=1)
    print(f"\nwrote {OUT} ({(time.time() - t0) / 60:.1f} min total)",
          flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    try:
        main()
    except BaseException as e:               # noqa: BLE001 - re-raised
        import traceback
        print("", flush=True)
        print(f"DIED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise
