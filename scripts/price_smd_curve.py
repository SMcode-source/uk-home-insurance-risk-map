"""Gate 2, the decision half: price the SMD curve on subsidence geography.

Seven full-fidelity runs off ONE scored frame, the price_sub_level.py
pattern: scoring is the expensive half and is identical across variants,
so every variant re-calibrates and re-simulates the same frame with the
same seed, and differences are PAIRED.

WHAT IS BEING PRICED. The model's subsidence surface is geology alone -
p_sub = 0.002 + 0.028*sub_score^1.5 - with no weather in it. The Gate 2
measurement (HANDOFF 2026-08-30) showed a drought climatology is a
genuinely different map (rho ~0.69 against the geology) whose national
aggregate recovers 5 of 6 canonical subsidence years. This harness asks
what an eow_rate-style blend

    sub_rel = (1 - share) + share * clim / weighted_mean(clim)

does to the premium, the capital, and the rating map, per index and per
share. The relativity multiplies FREQUENCY only; calibrate_frequency
re-pins the ABI level, so the national loss cost cannot move - only who
carries it. Dependence is untouched: theta_ws still reads sub_score.

THE SHARE MENU, and where each number comes from:

  0.40   below every published reading - the low bracket
  0.565  the ABI's own arithmetic, two releases agreeing: the 2018-12
         release frames 2,500 claims/quarter as the pre-surge baseline
         (=> 10,000/yr), and 2022's 23,000 total then attributes 13,000
         to the drought => 13/23 = 0.565. Internally consistent with
         2022's own H2 split (5,000 H1 = base/2 => the same 10,000
         base). Same derivation style as EOW_FREEZE_SHARE's 0.31.
  0.70   the industry attribution reading - root-induced clay shrinkage
         is ~60% of upheld claims in an average year and ~85% in a
         surge year (Zurich, "An in-depth look at subsidence"), and
         "~70% of claims" circulates as the round industry figure. The
         high bracket, NOT an anchor - recorded as corroboration.

Both candidate indices are priced at all three shares because the index
choice IS part of the decision:

  cwd_yr   annual peak of the uncapped within-year deficit. Recovers
           5/6 canonical years; wider spread (rel p5/p95 0.33/1.41).
  smd_jja  JJA mean of the 150 mm capped bucket. 4/6; tamer
           (0.31/1.22).

THE PET CAVEAT, MEASURED (check_pet_sensitivity.py, 2026-08-31, at
both resolutions): the PET inside both indices is Hargreaves-Samani,
~a third high in a maritime climate, and re-running the integrals at
PET x 0.85 and x 0.70 shows the bias moves the LEVEL (cwd_yr clim mean
240 -> 121 mm at x 0.70) and not the MAP - Spearman vs k=1.00 stays
+0.9983 or better for cwd_yr and +0.9940 or better for smd_jja, at
1 km (CI run 33404395072, the very table the climatology came from)
and 5 km alike. The level is exactly what calibration re-pins, so the
relativity this harness prices survives the PET formula. A shipped leg
would still cite Hydro-PE for the level's physics.

MEASUREMENT ONLY. Nothing here touches the published model; there is no
commit step. The result is a table the user decides on.

Usage:
  price_smd_curve.py                 # all seven, full N_SIM
  price_smd_curve.py --nsim 4000     # quick shape check, NOT for quoting
"""

import argparse
import csv
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
CLIM = os.path.join(ROOT, "data", "smd_climatology.csv")
OUT = os.path.join(ROOT, "data", "smd_curve_pricing.json")

SHARES = (0.40, 0.565, 0.70)
INDICES = (("cwd_yr", "cwd_yr_clim_mm"), ("smd_jja", "smd_jja_clim_mm"))


class _Scored(Exception):
    """Sentinel: aborts build_model.main() once the scored frame exists."""


def scored_frame():
    """price_sub_level.scored_frame, same reasoning: reuse main()'s
    scoring rather than copying it, so the experiment cannot silently
    score a different model from the one it prices."""
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


def climatology(gdf):
    """The committed per-district indices, aligned to the frame's rows."""
    idx = {}
    with open(CLIM, newline="") as fh:
        for r in csv.DictReader(fh):
            idx[r["district"]] = r
    missing = [n for n in gdf["name"] if n not in idx]
    if missing:
        raise SystemExit(f"{len(missing)} districts missing from "
                         f"smd_climatology.csv, e.g. {missing[:5]}")
    out = {}
    for key, col in INDICES:
        out[key] = np.array([float(idx[n][col]) for n in gdf["name"]])
    return out


def price(gdf, rel):
    """Re-calibrate and re-simulate the frame under one sub_rel curve.

    The normalisation happens HERE on the full frame, never per chunk -
    the eow_rate rule. calibrate_frequency then re-pins the ABI level,
    so FREQ_SCALE['sub'] absorbs any residual and the national EL is
    pinned by construction.
    """
    g = gdf.copy()
    g["sub_rel"] = rel
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
    clim = climatology(gdf)

    variants = [("baseline", None, 0.0)]
    for key, _col in INDICES:
        for s in SHARES:
            variants.append((f"{key}_s{int(round(s * 1000)):03d}", key, s))

    rows, base = [], None
    for name, key, share in variants:
        t1 = time.time()
        if key is None:
            rel = np.ones(len(gdf))
        else:
            v = clim[key]
            rel = (1.0 - share) + share * v / np.average(v, weights=w)
        print(f"\n=== {name}: rel p5/p50/p95 "
              f"{np.percentile(rel, 5):.3f}/{np.percentile(rel, 50):.3f}/"
              f"{np.percentile(rel, 95):.3f} ===", flush=True)
        g = price(gdf, rel)
        avg = lambda c: float(np.average(g[c].values, weights=w))  # noqa: E731
        row = dict(
            key=name, index=key, share=share,
            el_total=avg("el_total"), el_sub=avg("el_sub"),
            tvar99_euler=avg("tvar99_euler"), capital=avg("capital"),
            premium=avg("premium"),
        )
        if base is None:
            base = g
            row.update(churn=0, churn2=0, el_sub_drift=0.0)
            movers = ""
        else:
            row["churn"] = int((g["group"].values
                                != base["group"].values).sum())
            row["churn2"] = int((np.abs(g["group"].values
                                        - base["group"].values) >= 2).sum())
            # the level CANNOT move - calibrate_frequency pins
            # el_sub's exposure-weighted mean to paid/POLICIES for
            # every curve. Drift here means the harness is broken.
            row["el_sub_drift"] = row["el_sub"] - float(
                np.average(base["el_sub"].values, weights=w))
            d = g["premium"].values - base["premium"].values
            order = np.argsort(d)
            nm = gdf["name"].values
            movers = ("up " + ", ".join(
                f"{nm[i]} +{d[i]:.0f}" for i in order[-3:][::-1])
                + " | down " + ", ".join(
                    f"{nm[i]} {d[i]:.0f}" for i in order[:3]))
        rows.append(row)
        print(f"  premium GBP{row['premium']:.4f}  "
              f"el_sub GBP{row['el_sub']:.4f}  "
              f"capital GBP{row['capital']:.4f}  churn {row.get('churn', 0)}"
              f"  ({(time.time() - t1) / 60:.1f} min)", flush=True)
        if movers:
            print(f"  {movers}", flush=True)

    b = rows[0]
    print("\n" + "=" * 100, flush=True)
    print(f"{'variant':<16}{'share':>7}{'el_sub':>9}{'capital':>9}"
          f"{'premium':>10}{'vs base':>9}{'churn':>7}{'>=2 grp':>8}"
          f"{'el drift':>11}", flush=True)
    print("-" * 100, flush=True)
    for r in rows:
        d = (r["premium"] - b["premium"]) / b["premium"] * 100
        print(f"{r['key']:<16}{r['share']:>7.3f}{r['el_sub']:>9.4f}"
              f"{r['capital']:>9.4f}{r['premium']:>10.4f}{d:>8.3f}%"
              f"{r['churn']:>7}{r['churn2']:>8}"
              f"{r['el_sub_drift']:>11.2e}", flush=True)
    print("=" * 100, flush=True)
    for r in rows[1:]:
        if abs(r["el_sub_drift"]) > 1e-9:
            print(f"WARNING: {r['key']} el_sub drifted "
                  f"{r['el_sub_drift']:+.3e} - calibration failed to pin "
                  "the level, the harness is broken", flush=True)
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
