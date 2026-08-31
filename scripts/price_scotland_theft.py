"""The Scottish theft basis, priced: is 7,381 the right comparator?

Four full-fidelity runs off ONE scored frame, the price_freeze_share.py
pattern - scoring is the expensive half and is identical across
variants, so every variant re-calibrates and re-simulates the same frame
with the same seed and all differences are PAIRED.

WHAT IS ACTUALLY AT STAKE. Theft geography comes from police.uk, which
has no Scottish forces, so every Scottish district is overridden with
one national rate (scores_real.theft_from_police):

    scot_rate = SCOTLAND_HOUSEBREAKING_2024_25 / households[Scotland]

with the constant set to 7,381 - TOTAL Housebreaking, all premises,
Recorded Crime in Scotland 2024-25 Table A6. That table splits into:

    Dwelling       3,661
    Non-dwelling   1,531   (garages, sheds - domestic outbuildings)
    Domestic       5,192   = dwelling + non-dwelling, 70.3% of total
    Other          2,189   (shops, offices - non-domestic premises)
    Total          7,381

England and Wales are NOT all-premises: Phase 2a (eebb5c2, 2026-08-17)
divides each district's burglary count by households PLUS its VOA
non-domestic premises count, attributing each district only the
residential share of its burglary points. Scotland was touched in that
commit only to note that VOA is E&W-only; the comparator was never
revisited. So the two countries stopped being like-for-like, and the
question this harness asks is how much that is worth.

The naive answer - Scotland is inflated by 7381/5192 = 1.42x - is WRONG,
and measuring it is the point. The E&W correction is a geographic
attribution, not a category filter: it moves burglaries away from
commercial cores but nationally retains 91.2% of them (measured below,
and printed by this script rather than typed into it). So E&W is
residential-ish, not residential, and the like-for-like gap is nearer
0.703/0.912 = 1.30x than 1.42x. Both numbers are measured here.

The LEVEL does not price. calibrate_frequency pins the exposure-weighted
national theft frequency to the ABI anchor, so a uniform change to every
district cancels exactly. What survives is the RATIO between Scotland
and E&W, and that is what each variant moves:

  baseline   7,381 all-premises over Scottish households. Published.
  domestic   5,192. Scotland corrected to domestic property - the
             closest category match to what a household policy covers,
             outbuildings included. E&W left as it is: this is the
             one-sided correction, and it is here to be read against
             `matched` rather than adopted on its own.
  dwelling   3,661. Dwellings only, the strict lower bracket. Excludes
             the garage and the shed, which home insurance does not.
  matched    5,192 for Scotland AND E&W scaled to the same residential
             share, so neither country carries commercial burglary the
             other has had removed. The scale is Scotland's measured
             domestic share over E&W's measured implied share; it
             assumes the two countries split burglary between homes and
             businesses alike, which is an assumption and is why this is
             a bracket and not a proposal.

MEASUREMENT ONLY. Nothing here touches the published model and there is
no commit step. The output is a table the user decides on.

Usage:
  price_scotland_theft.py               # all four, full N_SIM
  price_scotland_theft.py --nsim 2000   # shape check, NOT quotable
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

import build_model as bm        # noqa: E402
import scores_real as sr        # noqa: E402

OUT = os.path.join(ROOT, "data", "scotland_theft_pricing.json")

# Recorded Crime in Scotland 2024-25, Table A6 (gov.scot, OGL v3.0),
# cached at data/cache/scotland_recorded_crime_2024_25.xlsx.
HB_TOTAL = 7_381
HB_DOMESTIC = 5_192
HB_DWELLING = 3_661


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


def ew_residential_share(names, households):
    """E&W's IMPLIED residential share of burglary under the Phase 2a
    denominator: sum(annual x hh/(hh+prem)) / sum(annual).

    This is what makes the harness honest. The Phase 2a correction is
    usually described as removing commercial burglary; this measures how
    much of it the correction actually removes, so `matched` can align
    the two countries on a number rather than on the description.
    """
    def _load(fname, *cols):
        path = os.path.join(bm.DATA, fname)
        with open(path, newline="") as fh:
            return {r["name"]: tuple(float(r[c]) for c in cols)
                    for r in csv.DictReader(fh)}

    burg = _load("burglary.csv", "burglaries", "months")
    prem = _load("premises.csv", "premises")

    scot = np.array(sr.load_country(list(names))) == "Scotland"
    hh = np.maximum(np.asarray(households, dtype=float), 1.0)
    annual = np.array([burg[n][0] / burg[n][1] * 12.0 for n in names])
    p = np.array([prem.get(n, (0.0,))[0] for n in names])

    ew = ~scot
    total = float(annual[ew].sum())
    resid = float((annual[ew] * hh[ew] / (hh[ew] + p[ew])).sum())
    return scot, total, resid, resid / total


def theft_rate(names, households, scot_count, ew_scale):
    """The published theft column, rebuilt under one Scottish comparator
    and one E&W scale.

    The Scottish constant is patched on the module rather than
    reimplemented, so the cap, the premises assertion and the geography
    are the ones the model actually uses. The E&W scale is applied AFTER
    the function returns, which is exactly equivalent to applying it
    before: the cap is a percentile OF the E&W rates, so it scales with
    them and min(a*r, a*cap) == a*min(r, cap). Scotland sits two orders
    below the cap and never touches it.
    """
    held = sr.SCOTLAND_HOUSEBREAKING_2024_25
    sr.SCOTLAND_HOUSEBREAKING_2024_25 = scot_count
    try:
        rate = sr.theft_from_police(names, households)
    finally:
        sr.SCOTLAND_HOUSEBREAKING_2024_25 = held
    scot = np.array(sr.load_country(list(names))) == "Scotland"
    if ew_scale != 1.0:
        rate = rate.copy()
        rate[~scot] *= ew_scale
    return rate


def price(gdf, rate):
    """Re-calibrate and re-simulate the frame under one th_rate column.

    ct_th has to be renormalised here, and missing it is the trap
    price_freeze_share.price() names for ct_eow: build_model scales the
    four attritional severities by the council-tax band mix and
    normalises each with CLAIM weights - households x that peril's OWN
    rate - so its claim-weighted mean is exactly 1 and the ABI severity
    level survives. That makes ct_th a function of th_rate. Overwrite
    th_rate on an already-scored frame and the multiplier left behind
    belongs to the old rate: the claim-weighted mean is no longer 1, the
    theft LEVEL drifts with the SHAPE of the relativity, and the drift
    reads exactly like a priced effect.

    The constant cancels, so the frame's own normalised column is all
    that is needed: ct_rel/A renormalised on the new weights gives
    ct_rel/B exactly, whatever A was.
    """
    g = gdf.copy()
    g["th_rate"] = rate
    wgt = g["households"].values * rate
    g["ct_th"] = g["ct_th"].values / np.average(g["ct_th"].values,
                                                weights=wgt)
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

    names = list(gdf["name"].values)
    hh = gdf["households"].values
    w = hh

    # The void-run guard. Every variant is built by re-running
    # theft_from_police with a patched constant, so if the rebuild does
    # not reproduce the frame's OWN column at the published 7,381 then
    # the harness is pricing something other than the model - and it
    # would still finish, with a table that looks like an answer. Assert
    # here, after the expensive half and before four simulations.
    rebuilt = theft_rate(names, hh, HB_TOTAL, 1.0)
    drift = float(np.abs(rebuilt - gdf["th_rate"].values).max())
    if drift > 1e-12:
        raise SystemExit(
            f"rebuilt baseline th_rate differs from the scored frame by "
            f"{drift:.3e} - theft_from_police is not being re-run the way "
            "build_model called it, and every variant below would be "
            "measured against the wrong baseline")

    scot, ew_total, ew_resid, ew_share = ew_residential_share(names, hh)
    scot_hh = float(hh[scot].sum())
    dom_share = HB_DOMESTIC / HB_TOTAL
    matched_scale = dom_share / ew_share

    print(f"\n{int(scot.sum())} Scottish districts, {scot_hh:,.0f} households")
    print(f"  E&W burglary {ew_total:,.0f}/yr all premises; "
          f"{ew_resid:,.0f}/yr attributed residential "
          f"= {ew_share:.1%} implied residential share")
    print(f"  Scotland domestic share {dom_share:.1%} "
          f"({HB_DOMESTIC:,} of {HB_TOTAL:,})")
    print(f"  matched E&W scale {matched_scale:.4f} "
          f"(= {dom_share:.3f} / {ew_share:.3f})")

    variants = [("baseline", HB_TOTAL, 1.0),
                ("domestic", HB_DOMESTIC, 1.0),
                ("dwelling", HB_DWELLING, 1.0),
                ("matched", HB_DOMESTIC, matched_scale)]

    rows, base = [], None
    for name, count, scale in variants:
        t1 = time.time()
        rate = theft_rate(names, hh, count, scale)
        s_mean = float(np.average(rate[scot], weights=hh[scot]))
        e_mean = float(np.average(rate[~scot], weights=hh[~scot]))
        print(f"\n=== {name}: Scotland {count:,} "
              f"({s_mean:.4%}/yr), E&W x{scale:.4f} ({e_mean:.4%}/yr), "
              f"ratio {s_mean / e_mean:.4f} ===", flush=True)
        g = price(gdf, rate)
        avg = lambda c: float(np.average(g[c].values, weights=w))  # noqa: E731
        savg = lambda c: float(np.average(g[c].values[scot],  # noqa: E731
                                          weights=hh[scot]))
        eavg = lambda c: float(np.average(g[c].values[~scot],  # noqa: E731
                                          weights=hh[~scot]))
        row = dict(key=name, scot_count=count, ew_scale=scale,
                   scot_rate=s_mean, ew_rate=e_mean, rate_ratio=s_mean / e_mean,
                   el_total=avg("el_total"), el_th=avg("el_th"),
                   tvar99_euler=avg("tvar99_euler"),
                   capital=avg("capital"), premium=avg("premium"),
                   premium_scotland=savg("premium"), premium_ew=eavg("premium"),
                   el_th_scotland=savg("el_th"), el_th_ew=eavg("el_th"))
        if base is None:
            base = g
            row.update(churn=0, churn2=0, el_th_drift=0.0)
        else:
            row["churn"] = int((g["group"].values
                                != base["group"].values).sum())
            row["churn2"] = int((np.abs(g["group"].values
                                        - base["group"].values) >= 2).sum())
            # The national theft level is pinned by calibrate_frequency,
            # so el_th must come back unchanged whatever the Scottish
            # comparator is; a drift here would mean the relativity
            # leaked into the level - which is exactly what a missing
            # ct_th renormalisation looks like. Tolerance, never
            # bit-equality: this is an algebraic identity computed in
            # floating point (the Gate 1 lesson).
            drift = abs(row["el_th"] / rows[0]["el_th"] - 1.0)
            row["el_th_drift"] = drift
            if drift > 1e-9:
                print(f"  !! el_th drifted {drift:.3e} - the Scottish basis "
                      "is supposed to be a pure relativity", flush=True)
            d = g["premium"].values - base["premium"].values
            o = np.argsort(d)
            row["movers_up"] = [(base["name"].values[i], round(float(d[i]), 2))
                                for i in o[-5:][::-1]]
            row["movers_down"] = [(base["name"].values[i], round(float(d[i]), 2))
                                  for i in o[:5]]
        rows.append(row)
        print(f"  premium {row['premium']:.4f}  Scotland "
              f"{row['premium_scotland']:.4f}  E&W {row['premium_ew']:.4f}"
              f"  el_th {row['el_th']:.4f}  churn {row.get('churn', 0)}"
              f"  [{(time.time() - t1) / 60:.1f} min]", flush=True)

    print("\n" + "=" * 86)
    print(f"{'variant':10s} {'scot':>7s} {'ratio':>7s} {'premium':>10s} "
          f"{'Scotland':>10s} {'E&W':>10s} {'el_th':>8s} {'churn':>6s} "
          f"{'>=2':>4s}")
    for r in rows:
        print(f"{r['key']:10s} {r['scot_count']:7,d} {r['rate_ratio']:7.4f} "
              f"{r['premium']:10.4f} {r['premium_scotland']:10.4f} "
              f"{r['premium_ew']:10.4f} {r['el_th']:8.4f} "
              f"{r.get('churn', 0):6d} {r.get('churn2', 0):4d}")
    with open(OUT, "w") as fh:
        json.dump(dict(ew_burglary_total=ew_total,
                       ew_burglary_residential=ew_resid,
                       ew_residential_share=ew_share,
                       scotland_domestic_share=dom_share,
                       matched_ew_scale=matched_scale,
                       variants=rows), fh, indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
