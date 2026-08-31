"""Gate 3: price the escape-of-water severity SPREAD, four ways.

Gate 3 set out to break burst pipes out of the escape-of-water leg. The
desk research (HANDOFF, "Gate 3 prep 2026-08-28") says that leg has no
shippable anchor: the ABI's two burst-pipe series disagree by a third,
the 2025 figure is not burst pipes at all, and there is no public
geography for them whatsoever. What the research DID produce is the
first anchor `SEV_SIGMA["eow"]` has ever had, so this prices that
instead.

WHAT THE ANCHOR IS. The ABI's winter-advice releases report burst-pipe
claims as a count and an average:

  2023   12,000 claims, average "exceeding GBP17,000"
  2024   ~8,000 claims, average ~GBP33,000     (primary not retrievable)

Against the model's EoW leg (GBP657m / GBP4,000 = 164,250 claims) those
are 7.3% of claims carrying 31.1% of paid, and 4.9% carrying 40.2%.
Asking what lognormal sigma puts that much value in that few claims
gives **0.96** and **1.41**. The 2023 figure is a floor ("exceeding"),
so its sigma is a floor too. The model ships **1.00**.

WHY THIS IS A PURE CAPITAL QUESTION, provable rather than empirical.
`marginal_params` builds the EoW severity as

    mu = log(_median_for_mean(M, s)) = log(M) - s^2 / 2

and `simulate` takes the leg's expected loss ANALYTICALLY:

    el_eow = p_eow * exp(mu + s^2 / 2) = p_eow * M

`s` cancels. Exactly, per district, for the same reason `sev` cancelled
out of the subsidence leg in Gate 1. So sigma cannot move `el_total` at
all: it moves the SHAPE of the severity distribution at a fixed mean,
which changes the simulated tail and therefore capital, and nothing
else. The table checks that rather than assuming it.

Do NOT restore a bit-equality test on el_total. The code divides M by
exp(s^2/2) and then multiplies by exp(s^2/2), and that round trip is
not bit-exact - Gate 1's harness tripped on 2.8e-14 and the finding was
a test bug, not a model bug. The tolerance below is 1e-9 on a mean of
~164, which is six orders of magnitude tighter than anything that could
matter and four looser than the rounding.

WHAT A RESULT HERE DOES NOT SETTLE. Raising sigma spreads cost
concentration UNIFORMLY across districts. In the model frost enters EoW
through frequency only (`eow_rate`), while severity is
`ABI["sev_eow"] * ct_eow` with one sigma everywhere - so a cold district
gets more EoW claims at the same average cost. A real burst-pipe leg
would tie the high-severity component to frost geography instead. These
are different models and this harness prices only the first. The second
stays unanchored until someone publishes burst-pipe geography.

Usage:
  price_eow_sigma.py                 # all four, full N_SIM
  price_eow_sigma.py --nsim 4000     # quick shape check, NOT for quoting
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "data", "eow_sigma_pricing.json")

# (key, label, sigma)
VARIANTS = [
    ("baseline", "as published", 1.00),
    ("abi2023", "2023 winter release, a FLOOR (12k x >GBP17,000)", 0.96),
    ("midpoint", "midway between the two ABI readings", 1.20),
    ("abi2024", "2024 winter release (8k x ~GBP33,000)", 1.41),
]


class _Scored(Exception):
    """Sentinel: raised from the simulate() stub to abort build_model.main()
    once the scored frame exists, so scoring is reused rather than copied."""


def scored_frame():
    """Run build_model.main() only as far as the scored, calibrated frame."""
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


def price(gdf, sigma):
    """Re-calibrate and re-simulate the frame under one EoW sigma."""
    bm.SEV_SIGMA["eow"] = sigma
    # calibrate_frequency does not read SEV_SIGMA for EoW - the leg's
    # target frequency is paid/sev/POLICIES and its `raw` comes from
    # p_eow, neither of which sigma touches. Re-run anyway: it is cheap,
    # it keeps this identical to the real pipeline, and the flood blend
    # it DOES re-derive must not silently differ between variants.
    g = gdf.copy()
    bm.calibrate_frequency(g)
    bm.calibrate_spatial(g)
    sim, _year = bm.simulate(g)
    for k, v in sim.items():
        g[k] = v
    g["capital"] = 0.06 * np.maximum(g["tvar99_euler"] - g["el_total"], 0.0)
    g["premium"] = g["el_total"] + g["capital"]
    bm.apply_cover_split(g)
    g["group"] = pd.qcut(g["premium"].rank(method="first"),
                         10, labels=False) + 1
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nsim", type=int, default=None,
                    help="override N_SIM (a quick shape check only)")
    ap.add_argument("--batch", type=int, default=None,
                    help="districts per simulation batch; lower it when the "
                         "machine is short of COMMIT, not just RAM")
    args = ap.parse_args()
    if args.nsim:
        bm.N_SIM = args.nsim
        print(f"*** N_SIM overridden to {args.nsim:,} - NOT quotable ***",
              flush=True)
    if args.batch:
        bm.BATCH = args.batch
        print(f"*** BATCH {args.batch}, {bm.N_THREADS} threads ***",
              flush=True)

    t0 = time.time()
    print("scoring once (this is the expensive half)...", flush=True)
    gdf = scored_frame()
    print(f"  scored {len(gdf)} districts in "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)

    w = gdf["households"].values
    rows, base = [], None
    for key, label, sigma in VARIANTS:
        t1 = time.time()
        print(f"\n=== {key}: SEV_SIGMA['eow'] = {sigma:.2f} ===", flush=True)
        g = price(gdf, sigma)
        avg = lambda c: float(np.average(g[c].values, weights=w))  # noqa: E731
        row = dict(
            key=key, label=label, sigma=sigma,
            el_total=avg("el_total"), el_eow=avg("el_eow"),
            tvar99_euler=avg("tvar99_euler"), capital=avg("capital"),
            premium=avg("premium"),
            premium_buildings=avg("premium_buildings"),
            premium_contents=avg("premium_contents"),
        )
        if base is None:
            base = g
            row["churn"] = 0
            row["churn2"] = 0
            row["el_err"] = 0.0
            row["el_invariant"] = True
        else:
            row["churn"] = int((g["group"].values
                                != base["group"].values).sum())
            row["churn2"] = int((np.abs(g["group"].values
                                        - base["group"].values) >= 2).sum())
            # The identity: sigma cancels out of el_eow analytically, so
            # el_total must not move at all. NOT a bit test - see the
            # docstring, and do not restore one.
            row["el_err"] = row["el_total"] - rows[0]["el_total"]
            row["el_invariant"] = abs(row["el_err"]) < 1e-9
        rows.append(row)
        print(f"  premium GBP{row['premium']:.4f}  "
              f"el GBP{row['el_total']:.6f}  "
              f"capital GBP{row['capital']:.4f}  "
              f"({(time.time() - t1) / 60:.1f} min)", flush=True)

    b = rows[0]
    print("\n" + "=" * 92, flush=True)
    print(f"{'variant':<12}{'sigma':>7}{'EL':>12}{'tvar99_eu':>12}"
          f"{'capital':>10}{'premium':>11}{'vs base':>10}{'churn':>7}"
          f"{'churn2':>8}", flush=True)
    print("-" * 92, flush=True)
    for r in rows:
        d = (r["premium"] - b["premium"]) / b["premium"] * 100
        print(f"{r['key']:<12}{r['sigma']:>7.2f}{r['el_total']:>12.6f}"
              f"{r['tvar99_euler']:>12.4f}{r['capital']:>10.4f}"
              f"{r['premium']:>11.4f}{d:>9.3f}%{r['churn']:>7}"
              f"{r['churn2']:>8}", flush=True)
    print("=" * 92, flush=True)
    for r in rows[1:]:
        if not r["el_invariant"]:
            print(f"WARNING: {r['key']} moved el_total by {r['el_err']:+.3e} "
                  "- sigma is NOT cancelling and the derivation is WRONG",
                  flush=True)
    with open(OUT, "w") as fh:
        json.dump(rows, fh, indent=1)
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
