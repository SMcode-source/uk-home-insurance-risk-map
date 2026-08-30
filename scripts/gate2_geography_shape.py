"""Gate 2: does the per-district HadUK record change either GEOGRAPHY?

Reads data/haduk_district_annual.csv (haduk_district_daily.py, 5 km,
area-weighted) and the published district file, and answers the gate's
two halves as SHAPE questions before anything is priced:

FREEZE  the model scales escape-of-water's freeze-sensitive slice by
        `frost_days`, a 1991-2020 air-frost-day climatology. Gate 2
        proposed a cold-spell/thaw index instead. The ERA5 check said
        no-reorder at 22 points (rho >= 0.99) but ERA5 is unusable in
        Scotland, where freeze exposure lives. This is the same question
        at all 2,736 districts on the model's own instrument family
        (HadUK-Grid), restricted to the same 1991-2020 window.

SUB     subsidence geography is geology alone - p_sub = 0.002 +
        0.028*sub_score^1.5, no weather anywhere in it. Gate 2 proposed
        an SMD curve on top. There is no incumbent layer to reorder, so
        the questions are: how much spatial spread does a drought
        climatology carry, how collinear is it with the geology it would
        multiply (clay country and dry country are both the southeast),
        and how far would an EOW_FREEZE_SHARE-style blend actually
        re-rank p_sub?

This script MEASURES. Nothing here is wired into build_model, and a
relativity that reorders nothing cannot move a premium - that finding
would close the gate's half without a CI run.
"""

import argparse
import csv
import json
import os
from collections import defaultdict

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
ANNUAL = os.path.join(ROOT, "data", "haduk_district_annual.csv")
DISTRICTS = os.path.join(ROOT, "data", "districts_risk.geojson")

CLIM = (1991, 2020)          # the window the model's frost layer uses

FREEZE_KEYS = ["frost_days", "freeze_spells", "freeze_spell_days",
               "worst_spell_degc_days"]
SUB_KEYS = ["smd_jja_mean_mm", "smd_max_mm", "cwd_yr_max_mm",
            "cwd_run_max_mm"]


def load_annual(path=ANNUAL):
    """district -> column -> np.array over years, plus the year vector."""
    rows = defaultdict(dict)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            rows[r["district"]][int(r["year"])] = r
    years = sorted(next(iter(rows.values())))
    out = {}
    for d, byyear in rows.items():
        if sorted(byyear) != years:      # partial district - refuse quietly
            continue
        out[d] = {k: np.array([float(byyear[y][k]) for y in years])
                  for k in FREEZE_KEYS + SUB_KEYS}
    return out, np.array(years)


def window_mean(series, years, y0, y1):
    m = (years >= y0) & (years <= y1)
    return float(series[m].mean())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--annual", default=ANNUAL,
                    help="which extraction to read - the 5 km table by "
                         "default, or the merged 1 km one")
    args = ap.parse_args()
    print(f"table: {os.path.basename(args.annual)}")
    ann, years = load_annual(args.annual)
    with open(DISTRICTS, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    props = {f["properties"]["name"]: f["properties"] for f in feats}

    common = sorted(set(ann) & set(props))
    print(f"{len(common)} districts with a complete {years[0]}-{years[-1]} "
          f"record and a published row ({len(props)} published)")

    hh = np.array([props[d]["households"] for d in common], dtype=float)
    model_frost = np.array([props[d]["frost_days"] for d in common])
    sub_score = np.array([props[d]["sub_score"] for d in common])
    el_sub = np.array([props[d]["el_sub"] for d in common])

    clim = {k: np.array([window_mean(ann[d][k], years, *CLIM)
                         for d in common])
            for k in FREEZE_KEYS + SUB_KEYS}
    full = {k: np.array([float(ann[d][k].mean()) for d in common])
            for k in SUB_KEYS}

    # ---------------------------------------------------------- freeze
    print(f"\nFREEZE - spell indices vs the model's frost_days layer, "
          f"all districts, {CLIM[0]}-{CLIM[1]} means")
    print(f"  instrument agreement first: 5 km {CLIM[0]}-{CLIM[1]} "
          f"frost_days vs the 1 km layer the model carries:")
    rho = stats.spearmanr(clim["frost_days"], model_frost).statistic
    r = stats.pearsonr(clim["frost_days"], model_frost).statistic
    print(f"    spearman {rho:+.3f}  pearson {r:+.3f}  "
          f"(means {clim['frost_days'].mean():.1f} vs "
          f"{model_frost.mean():.1f} days)")
    print("  and the gate's question - does a spell index rank places "
          "differently:")
    for k in FREEZE_KEYS:
        rho_m = stats.spearmanr(clim[k], model_frost).statistic
        rho_h = stats.spearmanr(clim[k], clim["frost_days"]).statistic
        print(f"    {k:24s} vs model frost {rho_m:+.4f}   "
              f"vs 5km frost (like-for-like) {rho_h:+.4f}")

    # ------------------------------------------------------------- sub
    print(f"\nSUB - drought climatology vs the geology it would multiply")
    for label, table in (("1991-2020", clim), ("1960-2025", full)):
        print(f"  window {label}:")
        for k in SUB_KEYS:
            v = table[k]
            rho_g = stats.spearmanr(v, sub_score).statistic
            # el_sub is already per policy - do NOT divide by households
            rho_e = stats.spearmanr(v, el_sub).statistic
            wmean = float(np.average(v, weights=hh))
            rel = v / wmean
            p5, p50, p95 = np.percentile(rel, [5, 50, 95])
            print(f"    {k:18s} vs sub_score {rho_g:+.3f}  "
                  f"vs el_sub {rho_e:+.3f}  "
                  f"relativity p5/p50/p95 {p5:.2f}/{p50:.2f}/{p95:.2f}")

    # what a freeze-share-style blend would re-rank. smd_jja is the
    # best-behaved candidate (the cap tames it without pegging), cwd_yr
    # the most discriminating; cwd_run is NOT offered - its multi-year
    # memory makes it a trend, not a geography (see the national check).
    p_sub = 0.002 + 0.028 * sub_score ** 1.5
    for k in ("smd_jja_mean_mm", "cwd_yr_max_mm"):
        v = clim[k]
        rel = v / float(np.average(v, weights=hh))
        print(f"\n  blend p_sub * (1-share + share*rel), rel from {k} "
              f"{CLIM[0]}-{CLIM[1]}:")
        for share in (0.2, 0.31, 0.5, 1.0):
            p_new = p_sub * ((1 - share) + share * rel)
            rho = stats.spearmanr(p_new, p_sub).statistic
            moved = np.abs(p_new / p_sub - 1)
            big = int((moved > 0.10).sum())
            print(f"    share {share:.2f}: rank rho vs today {rho:+.4f}, "
                  f"{big} districts move >10% in p_sub")

        order = np.argsort(rel)
        lo = [common[i] for i in order[:8]]
        hi = [common[i] for i in order[-8:]]
        print(f"  {k} relativity extremes (eyeball check - dry southeast "
              f"should top, wet northwest bottom):")
        print(f"    lowest : {', '.join(lo)}")
        print(f"    highest: {', '.join(hi)}")

    # ---------------------------------------------- temporal validation
    # The index must also recover the KNOWN subsidence years when
    # aggregated nationally, or its geography is not measuring drought.
    # hh-weighted so the aggregate is exposure's view of the summer, the
    # same weighting every calibration in the model uses.
    print("\nNATIONAL - does the hh-weighted index recover the canonical "
          "subsidence years (1976, 1995, 2003, 2006, 2018, 2022)?")
    for k in ("smd_jja_mean_mm", "cwd_yr_max_mm", "cwd_run_max_mm"):
        nat = np.array([
            np.average(np.array([ann[d][k][i] for d in common]), weights=hh)
            for i in range(len(years))])
        top = years[np.argsort(nat)[::-1][:10]]
        hits = sorted(set(top) & {1976, 1995, 2003, 2006, 2018, 2022})
        print(f"  {k:18s} top ten: {', '.join(str(y) for y in sorted(top))}"
              f"  ({len(hits)}/6 canonical: {', '.join(map(str, hits))})")


if __name__ == "__main__":
    main()
