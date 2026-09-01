"""Scottish theft geography, priced: what 32 councils buy over one rate.

Five full-fidelity runs off ONE scored frame, the price_freeze_share.py
pattern: scoring is identical across variants, so every variant
re-calibrates and re-simulates the same frame with the same seed and all
differences are PAIRED.

WHAT IS AT STAKE. police.uk has no Scottish forces, so all 442 Scottish
districts share ONE theft rate - 7,381 housebreakings over 2,504,952
households, 0.2947%/yr, identical from Shetland to central Edinburgh.
England and Wales get street-level burglary points. This is the largest
remaining geography gap in a peril worth 13.43% of claim cost, and
LIMITATIONS section 7 has ranked it as the free one to close.

`fetch_housebreaking.py` closes it to COUNCIL resolution:
statistics.gov.scot publishes Group 3 Housebreaking for all 32 council
areas, and those 32 sum to exactly the 7,381 the model already uses, so
this is the same measurement disaggregated. Apportioned to districts by
the households each contributes to each council, the flat 0.2947%
becomes 0.0459% (HS3, Na h-Eileanan Siar) to 0.6209% (EH2, Edinburgh) -
a 13.5x range where there is currently none. It is a 32-value step
function, so districts inside one council still share a value; that is
the honest limit of the source, not a defect in the join.

TWO QUESTIONS, DELIBERATELY SEPARATED. The apportionment conserves the
total exactly, so geography alone cannot move the Scottish level. But
the window can, and it is a live question this harness got wrong once
already:

  When `price_scotland_theft.py` ran on 2026-09-01 it recorded that
  period was not a confound, because the newest published Scottish year
  was 2024-25 and the police.uk archive (2023-07 to 2026-06) is centred
  on December 2024. That was wrong. statistics.gov.scot carries
  2025-26 - 6,968 housebreakings, a complete year - so the window is
  three-quarters covered, not half. Month-weighted over the 33 published
  months of it, the archive-matched Scottish figure is 7,681/yr, 4.1%
  ABOVE the constant in the model. Scotland is under-stated on period by
  about as much as the basis work found it over-stated on definition,
  and in the opposite direction.

So the variants price level and shape separately, and only then
together:

  baseline         flat 7,381 over Scottish households. Published.
  level_3yr        flat 7,794 - the 2023-24/2024-25/2025-26 mean, still
                   ONE rate everywhere. The period correction alone,
                   with no geography at all. (7,794 brackets the
                   month-weighted 7,681 from above; the two differ only
                   in how the part-years are weighted.)
  geog_1yr         council geography from 2024-25, whose total IS 7,381.
                   Geography alone, level bit-untouched.
  geog_3yr_shape   council geography from the three-year mean,
                   renormalised back to 7,381. Shape alone, but a
                   quieter shape: Shetland recorded SIX housebreakings in
                   2024-25, Na h-Eileanan Siar seven, Orkney eight, and a
                   one-year rate for those is mostly Poisson noise.
  geog_3yr_level   the three-year geography at its own 7,794. Both
                   corrections together - the candidate.

The national theft LEVEL cannot move in any of them: calibrate_frequency
pins the exposure-weighted UK frequency to the ABI anchor, so `el_th`
must come back identical and every variant is a pure relativity. What
moves is who inside Scotland pays it, and how much Scotland pays against
England and Wales.

MEASUREMENT ONLY. Nothing here touches the published model and there is
no commit step. The output is a table the user decides on.

Usage:
  price_scotland_theft_geography.py             # all five, full N_SIM
  price_scotland_theft_geography.py --nsim 2000 # shape check, NOT quotable
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

HOUSEBREAKING = os.path.join(ROOT, "data", "housebreaking.csv")
OUT = os.path.join(ROOT, "data", "scotland_theft_geography_pricing.json")


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


def housebreaking(names):
    """-> {column: array aligned to names} of annual housebreaking counts.

    Missing districts are NOT zero-filled. A Scottish district absent
    from the file is a join failure, and zero-filling one would read as a
    crime-free district rather than as a broken key - the households.csv
    void-run trap. Non-Scottish districts are absent by design and get
    NaN, which the caller never reads.
    """
    if not os.path.exists(HOUSEBREAKING):
        raise SystemExit("data/housebreaking.csv missing - run "
                         "scripts/fetch_housebreaking.py first")
    cols = ("hb_1yr", "hb_3yr")
    table = {}
    with open(HOUSEBREAKING, newline="") as fh:
        rdr = csv.DictReader(fh)
        missing = [c for c in cols if c not in (rdr.fieldnames or [])]
        if missing:
            raise SystemExit(f"housebreaking.csv has no {missing} - stale "
                             "file? Rerun scripts/fetch_housebreaking.py")
        for r in rdr:
            table[r["name"]] = [float(r[c]) for c in cols]
    return {c: np.array([table.get(n, [np.nan] * len(cols))[i] for n in names])
            for i, c in enumerate(cols)}


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
    print("scoring once...", flush=True)
    gdf = scored_frame()
    print(f"  scored {len(gdf)} districts in "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)

    names = list(gdf["name"].values)
    hh = gdf["households"].values
    w = hh
    scot = np.array(sr.load_country(names)) == "Scotland"
    base_rate = gdf["th_rate"].values.copy()
    scot_hh = float(hh[scot].sum())

    # The void-run guard. Every variant replaces the Scottish slice of
    # th_rate, so if the frame is not the FLAT-override model the
    # comparison has no baseline - and it would still finish, with a
    # table that looks like an answer. The published override is one rate
    # for every Scottish district; assert exactly that, after the
    # expensive half and before five simulations.
    flat = sr.SCOTLAND_HOUSEBREAKING_2024_25 / scot_hh
    spread = float(np.ptp(base_rate[scot]))
    if spread > 1e-15 or abs(float(base_rate[scot][0]) / flat - 1.0) > 1e-12:
        raise SystemExit(
            f"the scored frame's Scottish th_rate spans {spread:.3e} around "
            f"{base_rate[scot][0]:.6%} against an expected flat "
            f"{flat:.6%} - this is not the published override, so every "
            "variant below would be measured against the wrong baseline")

    hb = housebreaking(names)
    bad = [n for n, s, v in zip(names, scot, hb["hb_1yr"])
           if s and not np.isfinite(v)]
    if bad:
        raise SystemExit(
            f"{len(bad)} Scottish districts missing from housebreaking.csv "
            f"(first: {bad[:5]}) - stale file? Rerun "
            "scripts/fetch_housebreaking.py")

    tot_1yr = float(hb["hb_1yr"][scot].sum())
    tot_3yr = float(hb["hb_3yr"][scot].sum())
    print(f"\n{int(scot.sum())} Scottish districts, {scot_hh:,.0f} households")
    print(f"  published: one flat rate {flat:.4%}/yr, "
          f"{sr.SCOTLAND_HOUSEBREAKING_2024_25:,} housebreakings")
    _r1 = hb["hb_1yr"][scot] / hh[scot]
    print(f"  council geography 2024-25: {tot_1yr:,.0f} placed, rates "
          f"{_r1.min():.4%} .. {_r1.max():.4%} ({_r1.max() / _r1.min():.1f}x)")
    print(f"  council geography 3-year mean: {tot_3yr:,.0f} placed "
          f"({tot_3yr / tot_1yr:.3f}x the published level)")

    def scot_rate(values, total=None):
        """One full-length th_rate column: E&W untouched, Scotland from
        `values` (annual counts), optionally renormalised to `total`."""
        r = base_rate.copy()
        v = values[scot].astype(float)
        if total is not None:
            v = v * (total / v.sum())
        r[scot] = v / hh[scot]
        return r

    flat_3yr = np.where(scot, tot_3yr * hh / scot_hh, 0.0)

    variants = [
        ("baseline", base_rate),
        ("level_3yr", scot_rate(flat_3yr)),
        ("geog_1yr", scot_rate(hb["hb_1yr"])),
        ("geog_3yr_shape", scot_rate(hb["hb_3yr"], total=tot_1yr)),
        ("geog_3yr_level", scot_rate(hb["hb_3yr"])),
    ]

    rows, base = [], None
    for name, rate in variants:
        t1 = time.time()
        s_mean = float(np.average(rate[scot], weights=hh[scot]))
        e_mean = float(np.average(rate[~scot], weights=hh[~scot]))
        s_min, s_max = float(rate[scot].min()), float(rate[scot].max())
        print(f"\n=== {name}: Scotland {s_mean:.4%}/yr mean, "
              f"{s_min:.4%}..{s_max:.4%} ({s_max / s_min:.1f}x), "
              f"ratio to E&W {s_mean / e_mean:.4f} ===", flush=True)
        g = price(gdf, rate)

        def avg(c, m=None):
            v, ww = g[c].values, hh
            return float(np.average(v if m is None else v[m],
                                    weights=ww if m is None else ww[m]))

        row = dict(key=name, scot_total=float((rate * hh)[scot].sum()),
                   scot_rate=s_mean, scot_rate_min=s_min, scot_rate_max=s_max,
                   rate_ratio=s_mean / e_mean,
                   el_total=avg("el_total"), el_th=avg("el_th"),
                   tvar99_euler=avg("tvar99_euler"),
                   capital=avg("capital"), premium=avg("premium"),
                   premium_scotland=avg("premium", scot),
                   premium_ew=avg("premium", ~scot),
                   el_th_scotland=avg("el_th", scot),
                   el_th_ew=avg("el_th", ~scot))
        if base is None:
            base = g
            row.update(churn=0, churn2=0, churn_scotland=0, el_th_drift=0.0,
                       premium_scot_p5=0.0, premium_scot_p95=0.0)
        else:
            moved = g["group"].values != base["group"].values
            row["churn"] = int(moved.sum())
            row["churn_scotland"] = int((moved & scot).sum())
            row["churn2"] = int((np.abs(g["group"].values
                                        - base["group"].values) >= 2).sum())
            # The national theft level is pinned by calibrate_frequency,
            # so el_th must come back unchanged whatever the Scottish
            # geography is; a drift would mean the relativity leaked into
            # the level - exactly what a missing ct_th renormalisation
            # looks like. Tolerance, never bit-equality: this is an
            # algebraic identity in floating point (the Gate 1 lesson).
            drift = abs(row["el_th"] / rows[0]["el_th"] - 1.0)
            row["el_th_drift"] = drift
            if drift > 1e-9:
                print(f"  !! el_th drifted {drift:.3e} - the Scottish "
                      "geography is supposed to be a pure relativity",
                      flush=True)
            d = g["premium"].values - base["premium"].values
            row["premium_scot_p5"] = float(np.percentile(d[scot], 5))
            row["premium_scot_p95"] = float(np.percentile(d[scot], 95))
            o = np.argsort(d)
            row["movers_up"] = [(base["name"].values[i], round(float(d[i]), 2))
                                for i in o[-5:][::-1]]
            row["movers_down"] = [(base["name"].values[i],
                                   round(float(d[i]), 2)) for i in o[:5]]
        rows.append(row)
        print(f"  premium {row['premium']:.4f}  Scotland "
              f"{row['premium_scotland']:.4f}  E&W {row['premium_ew']:.4f}"
              f"  el_th {row['el_th']:.4f}  churn {row.get('churn', 0)}"
              f" ({row.get('churn_scotland', 0)} Scottish)"
              f"  [{(time.time() - t1) / 60:.1f} min]", flush=True)

    print("\n" + "=" * 100)
    print(f"{'variant':16s} {'scot n':>7s} {'range':>7s} {'premium':>10s} "
          f"{'Scotland':>10s} {'E&W':>10s} {'el_th':>8s} {'churn':>6s} "
          f"{'scot':>5s} {'>=2':>4s}")
    for r in rows:
        print(f"{r['key']:16s} {r['scot_total']:7,.0f} "
              f"{r['scot_rate_max'] / r['scot_rate_min']:6.1f}x "
              f"{r['premium']:10.4f} {r['premium_scotland']:10.4f} "
              f"{r['premium_ew']:10.4f} {r['el_th']:8.4f} "
              f"{r.get('churn', 0):6d} {r.get('churn_scotland', 0):5d} "
              f"{r.get('churn2', 0):4d}")
    with open(OUT, "w") as fh:
        json.dump(dict(scotland_households=scot_hh,
                       published_flat_rate=flat,
                       housebreaking_1yr=tot_1yr,
                       housebreaking_3yr=tot_3yr,
                       variants=rows), fh, indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
