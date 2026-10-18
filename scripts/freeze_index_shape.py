"""Gate 2, freeze half: is a cold-spell/thaw index a DIFFERENT map?

The model's escape-of-water leg carries a freeze-sensitive slice scaled by
`frost_days` - the Met Office 1991-2020 annual air-frost-day climatology
(`fetch_metoffice.py`). Gate 2 proposes replacing that with a cold-spell /
thaw index, on the physical argument that pipes burst when a SUSTAINED
freeze THAWS, not on days the air happened to dip below zero.

That argument is about physics. This script asks the cheaper question
first, because if the answer is no the physics does not matter: **does a
cold-spell index rank places differently from an air-frost count?** A
relativity that reorders nothing cannot move a premium.

It runs on whatever `fetch_era5_daily.py` has already cached, which is the
point of that fetcher's farthest-point traversal: every prefix is a
national sample, so this is answerable long before the fetch finishes.
Print the point count with any result - it is the sample size.

Indices, all per year, all from daily tmin/tmax:
  frost_days     days tmin < 0                     - what the model uses
  spells         runs of >= SPELL consecutive frost days
  spell_days     days inside those runs
  fdd_in_spells  freeze-degree-days inside them    - depth, not just count
  thaw_events    runs that ended (i.e. thawed)
  thaw_jump      mean tmax-on-the-thaw-day less tmin-on-the-last-frost-day
                 - the closest thing here to "how violently it thawed"

Also cross-checks ERA5 against the model's own frost layer, which is a
different instrument (HadUK-Grid 1 km, area-averaged over the district)
at a different resolution (~31 km, point-sampled). Restricted to
1991-2020 so the comparison is like for like.

Usage:  freeze_index_shape.py
"""

import glob
import json
import os

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CACHE = os.path.join(ROOT, "data", "cache", "era5_daily")
DISTRICTS = os.path.join(ROOT, "data", "districts_risk.geojson")
SPELL = 3          # consecutive frost days that count as a sustained freeze
CLIM = (1991, 2020)   # the model's frost climatology period

INDEX_KEYS = ["frost_days", "spells", "spell_days", "fdd_in_spells",
              "thaw_events", "thaw_jump"]


def runs_of(mask):
    """Start/end indices of each True run in a boolean array."""
    d = np.diff(mask.astype(np.int8))
    starts = np.flatnonzero(d == 1) + 1
    ends = np.flatnonzero(d == -1) + 1
    if mask.size and mask[0]:
        starts = np.r_[0, starts]
    if mask.size and mask[-1]:
        ends = np.r_[ends, mask.size]
    return starts, ends


def indices(tmin, tmax, n_years):
    frost = tmin < 0.0
    starts, ends = runs_of(frost)
    long = (ends - starts) >= SPELL
    fdd, jumps = 0.0, []
    for s, e in zip(starts[long], ends[long]):
        seg = tmin[s:e]
        fdd += float(-seg[seg < 0].sum())
        if e < tmax.size:                    # the spell ended within the record
            jumps.append(float(tmax[e] - tmin[e - 1]))
    return {
        "frost_days": float(frost.sum()) / n_years,
        "spells": float(long.sum()) / n_years,
        "spell_days": float((ends - starts)[long].sum()) / n_years,
        "fdd_in_spells": fdd / n_years,
        "thaw_events": float(len(jumps)) / n_years,
        "thaw_jump": float(np.mean(jumps)) if jumps else 0.0,
    }


def main():
    files = sorted(glob.glob(os.path.join(CACHE, "*.npz")))
    if not files:
        raise SystemExit(f"no cached points under {CACHE} - run "
                         "fetch_era5_daily.py first")

    rows = []
    for f in files:
        d = np.load(f, allow_pickle=True)
        tmin, tmax = d["tmin"], d["tmax"]
        if not (np.isfinite(tmin).all() and np.isfinite(tmax).all()):
            raise SystemExit(f"{f} has non-finite temperatures")
        yr = np.array([int(s[:4]) for s in d["dates"]])
        clim = (yr >= CLIM[0]) & (yr <= CLIM[1])
        early, late = yr < 1993, yr >= 1993
        nu = lambda sel: len(np.unique(yr[sel]))  # noqa: E731
        r = dict(pcd=os.path.basename(f)[:-4],
                 **indices(tmin, tmax, len(np.unique(yr))))
        r["frost_clim"] = indices(tmin[clim], tmax[clim],
                                  nu(clim))["frost_days"]
        for lbl, sel in (("early", early), ("late", late)):
            got = indices(tmin[sel], tmax[sel], nu(sel))
            r[f"frost_{lbl}"] = got["frost_days"]
            r[f"spells_{lbl}"] = got["spells"]
        rows.append(r)

    n = len(rows)
    print(f"{n} cached points (of 57 planned) - THIS IS THE SAMPLE SIZE\n")
    print(f"{'pcd':<7}" + "".join(f"{k:>15}" for k in INDEX_KEYS))
    print("-" * (7 + 15 * len(INDEX_KEYS)))
    for r in sorted(rows, key=lambda r: -r["frost_days"]):
        print(f"{r['pcd']:<7}" + "".join(f"{r[k]:>15.2f}" for k in INDEX_KEYS))

    print(f"\nQ1. Does any index REORDER the map vs frost_days? (n={n})")
    fd = np.array([r["frost_days"] for r in rows])
    for k in INDEX_KEYS[1:]:
        v = np.array([r[k] for r in rows])
        print(f"  {k:<16} Spearman rho = "
              f"{stats.spearmanr(fd, v).statistic:+.3f}")

    print("\nQ2. Is the map itself moving? 1960-1992 vs 1993-2025")
    for lbl, a, b in (("frost days", "frost_early", "frost_late"),
                      (f"spells>={SPELL}d", "spells_early", "spells_late")):
        e = np.array([r[a] for r in rows])
        l = np.array([r[b] for r in rows])  # noqa: E741
        print(f"  {lbl:<12} {e.mean():7.2f} -> {l.mean():.2f} "
              f"({100 * (l.mean() / e.mean() - 1):+.1f}%), "
              f"rank rho {stats.spearmanr(e, l).statistic:+.3f}")

    print(f"\nQ3. ERA5 vs the model's frost layer, both {CLIM[0]}-{CLIM[1]}")
    with open(DISTRICTS, encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    props = {ft["properties"]["name"]: ft["properties"] for ft in feats}
    by_country = {}
    for r in rows:
        p = props.get(r["pcd"])
        if p is None or p.get("frost_days") is None:
            continue
        by_country.setdefault(p.get("country", "?"), []).append(
            (r["pcd"], r["frost_clim"], p["frost_days"]))

    def block(label, v):
        if len(v) < 3:
            return
        a = np.array([x[1] for x in v])
        m = np.array([x[2] for x in v])
        print(f"  {label:<18} n={len(v):<3} ERA5 {a.mean():5.1f} vs HadUK "
              f"{m.mean():5.1f} ({100 * (a.mean() / m.mean() - 1):+.0f}%), "
              f"Pearson {stats.pearsonr(a, m).statistic:+.3f}, "
              f"mean |diff| {np.abs(a - m).mean():.1f} d")

    allv = [x for v in by_country.values() for x in v]
    block("all", allv)
    block("Scotland", by_country.get("Scotland", []))
    block("England & Wales",
          [x for c, v in by_country.items() if c != "Scotland" for x in v])
    print("\n  worst disagreements:")
    for k, a, m in sorted(allv, key=lambda x: -abs(x[1] - x[2]))[:8]:
        print(f"    {k:<7}{a:>7.1f}{m:>8.1f}{a - m:>+8.1f}")


if __name__ == "__main__":
    main()
