"""The freeze re-aim, priced: what a warming winter can and cannot cost.

Six full-fidelity runs off ONE scored frame, the price_smd_curve.py
pattern - scoring is the expensive half and is identical across
variants, so every variant re-calibrates and re-simulates the same
frame with the same seed and all differences are PAIRED.

WHAT IS ACTUALLY AT STAKE. The model reads winter through one column:

    eow_rate = ABI_TARGET_FREQ["eow"]
               * ((1 - EOW_FREEZE_SHARE) + EOW_FREEZE_SHARE * frost/wmean(frost))

Dividing frost by its own exposure-weighted mean removes the LEVEL
exactly, so the measured decline in UK frost days - -0.326 days/yr,
p=0.0002, -7.5% of the mean per decade, 49.0 days in 1961-1990 against
38.9 in 1991-2020 (measure_frost_era.py, agreeing to the third decimal
at 1 km and 5 km) - is invisible to this model by construction. Two
things are not invisible: the SHAPE of the frost map, and the SHARE.

The shape was measured first and does NOT justify a re-aim. Every
candidate window was compared against within-era controls that hold the
climate fixed and vary only the sample, because a shorter, more recent
window is a noisier estimate as well as a more current one. The two
windows a careful modeller would consider sit far inside their
controls: 1996-2025 moves the relativity by |drel| p95 = 0.045 and
2006-2025 by 0.091, against 0.158 for two 15-year halves of the
published era itself. The recent decade (0.187) does exceed its
sample-matched control - but only just (0.178 for two disjoint decades
INSIDE the stable era), which is the definition of no signal. Even the
1961-1990 map, a genuinely different climate 30 years back, differs
from the published one by no more than two arbitrary decades of the
published era differ from each other.

So the map stays, and this harness prices what is left:

  share 0.31   published. The ABI's own weather-attribution arithmetic,
               two releases agreeing (0.311/0.307) - DATA_SOURCES #26.
  share 0.266  0.31 x (33.39/38.95), the last decade's frost over the
               published era's. What the share becomes IF the
               freeze-driven part of escape of water scales with frost
               days while the rest of the peril does not. That "if" is
               an assumption, not an anchor, and is the whole reason
               this is a dose-response and not a proposal.
  share 0.20   a lower bracket, consistent with the observed trend
               continuing. Explicitly not a projection - no UK
               publication attributes escape-of-water claims to freeze
               by era, so there is nothing to calibrate a projection
               against.
  share 0.40   the upper bracket, for symmetry: the dose-response has
               to show both directions or it is an argument, not a
               measurement.

Two more variants isolate the instrument from the era, so the era
answer cannot be confounded by how frost was measured:

  daily_1991_2020  the published era, but frost integrated from the
                   daily extraction over each polygon instead of IDW'd
                   from the gridded climatology (+0.98 agreement, 40.5
                   vs 40.0 days). The instrument change ALONE.
  era_2006_2025    the same daily instrument, aimed at the recent 20
                   years. Read against daily_1991_2020, this is the era
                   change alone - and the measurement above predicts it
                   prices to nearly nothing. A prediction worth testing
                   rather than asserting.

MEASUREMENT ONLY. Nothing here touches the published model and there is
no commit step. The output is a table the user decides on.

Usage:
  price_freeze_share.py               # all six, full N_SIM
  price_freeze_share.py --nsim 2000   # shape check, NOT quotable
"""

import argparse
import csv
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import build_model as bm  # noqa: E402

FROST = os.path.join(ROOT, "data", "frost_climatology.csv")
OUT = os.path.join(ROOT, "data", "freeze_share_pricing.json")

# (label, era column or None for the published gridded instrument, share)
SHARES = [0.20, 0.266, 0.40]
ERA_COL = "frost_2006_2025"
BASE_COL = "frost_1991_2020"


class _Scored(Exception):
    """Raised to hand main()'s scored frame back before it simulates."""


def scored_frame():
    """Reuse main()'s scoring rather than copying it, so the experiment
    cannot silently score a different model from the one it prices."""
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


def era_frost(gdf):
    """The committed per-era frost climatologies, aligned to the frame."""
    idx = {}
    with open(FROST, newline="") as fh:
        for r in csv.DictReader(fh):
            idx[r["district"]] = r
    missing = [n for n in gdf["name"] if n not in idx]
    if missing:
        raise SystemExit(f"{len(missing)} of {len(gdf)} names missing from "
                         f"frost_climatology.csv, e.g. {missing[:5]} "
                         "- wrong grain?")
    return {c: np.array([float(idx[n][c]) for n in gdf["name"]])
            for c in (BASE_COL, ERA_COL)}


def price(gdf, rate):
    """Re-calibrate and re-simulate the frame under one eow_rate column."""
    g = gdf.copy()
    g["eow_rate"] = rate
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
    print("scoring once (this is the expensive half)...", flush=True)
    gdf = scored_frame()
    print(f"  scored {len(gdf)} districts in "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)

    w = gdf["households"].values
    anchor = bm.ABI_TARGET_FREQ["eow"]
    published_frost = gdf["frost_days"].values
    eras = era_frost(gdf)

    def rate_for(frost, share):
        rel = frost / np.average(frost, weights=w)
        return anchor * ((1.0 - share) + share * rel)

    variants = [("baseline", published_frost, bm.EOW_FREEZE_SHARE)]
    variants += [(f"share_{int(round(s * 1000)):03d}", published_frost, s)
                 for s in SHARES]
    variants += [("daily_1991_2020", eras[BASE_COL], bm.EOW_FREEZE_SHARE),
                 ("era_2006_2025", eras[ERA_COL], bm.EOW_FREEZE_SHARE)]

    rows, base = [], None
    for name, frost, share in variants:
        t1 = time.time()
        rate = rate_for(frost, share)
        rel = rate / anchor
        print(f"\n=== {name}: share {share:.3f}, eow relativity p5/p50/p95 "
              f"{np.percentile(rel, 5):.3f}/{np.percentile(rel, 50):.3f}/"
              f"{np.percentile(rel, 95):.3f} ===", flush=True)
        g = price(gdf, rate)
        avg = lambda c: float(np.average(g[c].values, weights=w))  # noqa: E731
        row = dict(key=name, share=share,
                   el_total=avg("el_total"), el_eow=avg("el_eow"),
                   tvar99_euler=avg("tvar99_euler"),
                   capital=avg("capital"), premium=avg("premium"))
        if base is None:
            base = g
            row.update(churn=0, churn2=0, el_eow_drift=0.0)
        else:
            row["churn"] = int((g["group"].values
                                != base["group"].values).sum())
            row["churn2"] = int((np.abs(g["group"].values
                                        - base["group"].values) >= 2).sum())
            # the national EoW level is pinned by calibrate_frequency; a
            # drift here would mean the relativity leaked into the level.
            # Tolerance, never bit-equality - this is an algebraic
            # identity computed in floating point (the Gate 1 lesson).
            drift = abs(row["el_eow"] / rows[0]["el_eow"] - 1.0)
            row["el_eow_drift"] = drift
            if drift > 1e-9:
                print(f"  !! el_eow drifted {drift:.3e} - the freeze share "
                      "is supposed to be a pure relativity", flush=True)
            d = g["premium"].values - base["premium"].values
            o = np.argsort(d)
            row["movers_up"] = [(base["name"].values[i], round(float(d[i]), 2))
                                for i in o[-5:][::-1]]
            row["movers_down"] = [(base["name"].values[i], round(float(d[i]), 2))
                                  for i in o[:5]]
        rows.append(row)
        print(f"  premium {row['premium']:.4f}  capital {row['capital']:.4f}"
              f"  el_eow {row['el_eow']:.4f}  churn {row.get('churn', 0)}"
              f"  [{(time.time() - t1) / 60:.1f} min]", flush=True)

    print("\n" + "=" * 78)
    print(f"{'variant':18s} {'share':>6s} {'premium':>10s} {'capital':>9s} "
          f"{'el_eow':>8s} {'churn':>6s} {'>=2':>4s}")
    for r in rows:
        print(f"{r['key']:18s} {r['share']:6.3f} {r['premium']:10.4f} "
              f"{r['capital']:9.4f} {r['el_eow']:8.4f} "
              f"{r.get('churn', 0):6d} {r.get('churn2', 0):4d}")
    with open(OUT, "w") as fh:
        json.dump(rows, fh, indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
