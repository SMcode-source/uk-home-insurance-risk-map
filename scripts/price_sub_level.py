"""Gate 1: price every defensible subsidence LEVEL, and the severity fix.

Five full-fidelity runs off ONE scored frame. Scoring the 2,736 districts
(BGS geology, Met Office grids, EA/NRW/SEPA flood, NCERM, police, MHCLG,
census, council tax) is the expensive half of a build and is identical
across these variants, so it runs once and every variant re-calibrates and
re-simulates on the same frame with the same seed. That makes the
differences PAIRED - no scoring noise, no seed lottery between variants.

WHAT IS BEING TESTED, and why it is two questions and not one.

`build_model.ABI` carries the subsidence leg as a paid total and an
average claim:

    subsidence_paid=307e6, sev_subsidence=17_820.0

Those two numbers are from different periods and different releases.
GBP307m is FY2025 (ABI 2026-02). GBP17,820 is **Q1 2026** (ABI 2026-05).
DATA_SOURCES #33 records the mismatch; this script prices it.

But the severity cannot move the premium, and that is provable rather
than empirical. calibrate_frequency sets

    FREQ_SCALE["sub"] = ABI_TARGET_FREQ["sub"] / raw
                      = (paid / sev / POLICIES) / raw

and the leg's expected loss is p_sub(i) * FREQ_SCALE["sub"] * E[sev]:

    EL_sub(i) = p_sub(i) * paid / (POLICIES * raw)

`sev` cancels. Per district, exactly. So the severity choice moves the
FREQUENCY/SEVERITY SPLIT at a fixed expected loss - which changes the
simulated tail (more, cheaper claims are thinner-tailed at the same mean)
and changes the implied claim count, and nothing else.

MEASURED, first run: the severity fix moved the exposure-weighted EL by
-2.8e-14 on 164.12 - one unit in the last place of a float64 - and the
premium by -0.7 pence, all of it capital. The identity holds.

So the table checks the STRONGER form of the same claim, at every level
rather than only at an unchanged one: national EL must equal
`paid / POLICIES`, so a level change of D must move it by exactly
D / POLICIES. It does, to under 6e-14 across a 30% range of the level.
Do NOT restore a bit-equality test here - it fails on rounding, because
the code divides by `sev` and then multiplies by exp(mu + sigma^2/2)
with mu = log(sev / exp(sigma^2/2)), which is not a bit-exact round trip.

The only lever on the LEVEL is `subsidence_paid`, and the series in
data/abi_subsidence.csv offers four candidates, all on the paid basis so
they are comparable to each other:

  307   FY2025, published (ABI 2026-02)              - what ships today
  280   FY2024, DERIVED as 307-27 from a comparative - its own quarters
        sum to 178, implying a Q4 of 102, which is 1.55x the largest
        quarter ever published. Recorded as unreconciled, not smoothed.
  237   FY2024 annualised from its three published quarters (4/3 x 178)
  288   2026 annualised from Q2 (4 x 72); paid has no seasonality -
        2025 ran 49.8% H1 / 50.2% H2 - so x4 is legitimate here in a way
        it would NOT be on the notified series, which is 78% H2.

None of these is obviously right, which is the point of pricing all four.
Note the model anchors E[loss] on ONE year for every peril, and
anchor_budget.py already calls that a methodology defect; subsidence is
the most volatile peril in the book, and paid LAGS - the 2022 surge
(23,000 claims notified, GBP219m incurred) was settled across 2023-25, so
FY2025 paid contains run-off from it and is not a steady-state year.

LIMITATION, stated rather than hidden: the corrected severity (GBP17,264,
2025 H1 avg_paid) is held fixed across all four level candidates because
no 2024 or 2026 average on the paid basis has been published. Pairing a
2025 average with a 2024 total is the same class of mismatch this script
is correcting - it is accepted here only because the alternative is no
comparison at all, and because the algebra above says the severity cannot
move the level anyway.

WHAT THIS HARNESS'S NUMBERS ARE, to the digit. Every figure here is an
exposure-weighted mean of UNROUNDED per-district values. The published
`districts_risk.geojson` is not: `build_model.main()` rounds `el*` and
`premium` to 1 dp per district and `capital` to 4 dp before writing.

So comparing a row here against a published figure compares two
different quantisations. Measured on the Gate 1 rebuild: capital agreed
to six decimals (5.533736), `el_total` differed by +0.0011. That is not
an error in either - 1-dp rounding across 2,736 districts puts SD 0.00067
on the weighted mean, so +0.0011 is 1.65 SD, while 4-dp rounding puts
SD 6.7e-7 on capital's. The gap scales with each column's granularity,
which is the signature of rounding and of nothing else.

Practical rule: quote THIS for differences, at full precision. Quote it
for absolute levels too, but only to about +-0.0013 on EL and premium -
and note that reading those back out of the GeoJSON carries the same
+-0.0013, so a rebuild is not the more precise source, merely the
published one.

Usage:
  price_sub_level.py                 # all five, full N_SIM
  price_sub_level.py --nsim 4000     # quick shape check, NOT for quoting
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
OUT = os.path.join(ROOT, "data", "sub_level_pricing.json")

# (key, label, subsidence_paid, sev_subsidence)
VARIANTS = [
    ("baseline", "as published: FY2025 paid, Q1-2026 average",
     307e6, 17_820.0),
    ("sevfix", "severity fix only: FY2025 paid, 2025-H1 average",
     307e6, 17_264.0),
    ("fy2024_derived", "level FY2024 derived (307-27)",
     280e6, 17_264.0),
    ("fy2024_quarters", "level FY2024 from its 3 published quarters",
     4.0 / 3.0 * 178e6, 17_264.0),
    ("y2026_annualised", "level 2026 annualised from Q2 (4 x 72)",
     288e6, 17_264.0),
]


class _Scored(Exception):
    """Sentinel: raised from the simulate() stub to abort build_model.main()
    once the scored frame exists, so scoring is reused rather than copied."""


def scored_frame():
    """Run build_model.main() only as far as the scored, calibrated frame.

    Reusing main() rather than duplicating its hundred lines of scoring is
    deliberate: a copy would drift the moment anyone touches the real
    pipeline, and an experiment that silently scores differently from the
    model it is pricing is worse than no experiment.
    """
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


def price(gdf, paid, sev):
    """Re-calibrate and re-simulate the frame under one ABI pair."""
    bm.ABI["subsidence_paid"] = paid
    bm.ABI["sev_subsidence"] = sev
    # ABI_TARGET_FREQ is built at import from ABI, and calibrate_frequency
    # only re-derives the FLOOD entry (its severity is a blend). The
    # subsidence entry has to be re-derived here or the run silently
    # prices the old level.
    bm.ABI_TARGET_FREQ["sub"] = paid / sev / bm.POLICIES

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
        # The first attempt at this died in geopandas' to_crs failing to
        # allocate EIGHT megabytes, because the machine was at 66.9 GB of
        # a 68.4 GB commit limit with a single unrelated process holding
        # 25 GB. Peak here is ~25 transient (BATCH x N_SIM) float64
        # arrays per thread, so BATCH and UKRISK_THREADS are the two
        # dials that matter when commit is the binding constraint.
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
    for key, label, paid, sev in VARIANTS:
        t1 = time.time()
        print(f"\n=== {key}: paid GBP{paid / 1e6:,.1f}m, "
              f"sev GBP{sev:,.0f} ===", flush=True)
        g = price(gdf, paid, sev)
        avg = lambda c: float(np.average(g[c].values, weights=w))  # noqa: E731
        row = dict(
            key=key, label=label, paid=paid, sev=sev,
            implied_claims=paid / sev,
            el_total=avg("el_total"), el_sub=avg("el_sub"),
            tvar99_euler=avg("tvar99_euler"), capital=avg("capital"),
            premium=avg("premium"),
            premium_buildings=avg("premium_buildings"),
            premium_contents=avg("premium_contents"),
        )
        if base is None:
            base = g
            row["churn"] = 0
            row["churn2"] = 0
            row["el_pred_err"] = 0.0
            row["el_identical"] = True
        else:
            row["churn"] = int((g["group"].values
                                != base["group"].values).sum())
            row["churn2"] = int((np.abs(g["group"].values
                                        - base["group"].values) >= 2).sum())
            # NOT array_equal. The first run tripped this check on a
            # difference of 2.8e-14 on a mean of 164.12 - ONE unit in the
            # last place of a float64. `sev` cancels in exact arithmetic,
            # but the code divides by it and then multiplies by
            # exp(mu + sigma^2/2) with mu = log(sev / exp(sigma^2/2)), and
            # that round trip is not bit-exact. Demanding bit-equality of
            # an algebraic identity computed in floating point is a test
            # bug, not a finding.
            #
            # The stronger claim is checked instead, and it is the one
            # actually worth checking: EL must equal the BASE EL less the
            # change in paid per policy, for every level, not just for an
            # unchanged one.
            pred = (float(np.average(base["el_total"].values, weights=w))
                    - (VARIANTS[0][2] - paid) / bm.POLICIES)
            row["el_pred_err"] = row["el_total"] - pred
            row["el_identical"] = abs(row["el_pred_err"]) < 1e-9
        rows.append(row)
        print(f"  premium GBP{row['premium']:.2f}  "
              f"el GBP{row['el_total']:.2f}  "
              f"capital GBP{row['capital']:.4f}  "
              f"claims {row['implied_claims']:,.0f}  "
              f"({(time.time() - t1) / 60:.1f} min)", flush=True)

    b = rows[0]
    print("\n" + "=" * 96, flush=True)
    print(f"{'variant':<18}{'paid':>8}{'sev':>8}{'claims':>9}"
          f"{'EL':>9}{'capital':>9}{'premium':>10}{'vs base':>9}"
          f"{'churn':>7}", flush=True)
    print("-" * 96, flush=True)
    for r in rows:
        d = (r["premium"] - b["premium"]) / b["premium"] * 100
        print(f"{r['key']:<18}{r['paid'] / 1e6:>8.0f}{r['sev']:>8.0f}"
              f"{r['implied_claims']:>9,.0f}{r['el_total']:>9.2f}"
              f"{r['capital']:>9.4f}{r['premium']:>10.2f}{d:>8.2f}%"
              f"{r['churn']:>7}", flush=True)
    print("=" * 96, flush=True)
    for r in rows[1:]:
        if not r["el_identical"]:
            print(f"WARNING: {r['key']} EL is {r['el_pred_err']:+.3e} off "
                  "paid/POLICIES - the severity-cancels derivation is WRONG",
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
