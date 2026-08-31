"""The two national temperature series the site publishes, as one file.

The temperature page shows what the last 66 years of UK weather did to
the two perils temperature actually reaches - subsidence through summer
drought, escape of water through winter frost - and both series have to
be the model's OWN instruments, not a tidier public index, or the page
would be illustrating a different model from the one it links to.

So both are reduced here from the same gitignored per-district daily
extraction that produced data/smd_climatology.csv (HadUK-Grid 1 km
daily via CEDA; haduk_1km_stream.py on CI, DATA_SOURCES #34), weighted
by census households so the national figure is per-policy exposure
rather than per-square-kilometre:

  cwd_yr_mm    the annual peak of the within-year cumulative water
               deficit, reset each 1 January - the index the shipped
               SMD curve puts on subsidence frequency.
  frost_days   annual air-frost days - the index EOW_FREEZE_SHARE puts
               on escape-of-water frequency.

Committed as JSON because the input is 12 MB and gitignored while this
is ~4 KB: the make_smd_climatology.py rule, small reduction in, large
input out. Nothing on the site may hand-write a number that appears
here - the whole point of injecting it is that the prose cannot drift
away from the data (the stale-severity-column defect, README's
"Published figures" note).

Usage:  make_temperature_series.py [--src <annual csv>] [--out <json>]
"""

import argparse
import csv
import json
import os
from collections import defaultdict

import numpy as np
from scipy.stats import linregress

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "data", "haduk_district_annual_1km.csv")
GEOJSON = os.path.join(ROOT, "data", "districts_risk.geojson")
OUT = os.path.join(ROOT, "data", "temperature_series.json")

CLIM = (1991, 2020)          # the model's window, and every other climatology's
RECENT = (2006, 2025)        # the re-aim candidate measure_frost_era.py tested
PREVIOUS = (1961, 1990)      # the previous WMO normal

# The years UK subsidence surges are canonically dated to. Used only to
# mark the drought chart and to state the backtest hit rate; the model
# is never fitted to them.
CANONICAL = [1976, 1995, 2003, 2006, 2018, 2022]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--geojson", default=GEOJSON)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    with open(args.geojson) as fh:
        hh = {f["properties"]["name"]: f["properties"]["households"]
              for f in json.load(fh)["features"]}
    cols = {"cwd_yr_mm": "cwd_yr_max_mm", "frost_days": "frost_days"}
    acc = {k: defaultdict(dict) for k in cols}
    with open(args.src, newline="") as fh:
        for r in csv.DictReader(fh):
            for key, col in cols.items():
                acc[key][r["district"]][int(r["year"])] = float(r[col])

    names = sorted(set(acc["frost_days"]) & set(hh))
    if not names:
        raise SystemExit(f"{args.src} and {args.geojson} share no names "
                         "- wrong grain?")
    w = np.array([hh[n] for n in names], float)
    years = sorted({y for d in acc["frost_days"].values() for y in d})

    out = {"years": years, "n_polygons": len(names),
           "canonical_subsidence_years": CANONICAL,
           "clim": list(CLIM), "recent": list(RECENT),
           "previous": list(PREVIOUS),
           "source": ("HadUK-Grid 1 km daily (Met Office via CEDA, OGL), "
                      "integrated per postcode district and weighted by "
                      "census households")}

    for key in cols:
        series = np.array([np.average([acc[key][n][y] for n in names],
                                      weights=w) for y in years])
        lr = linregress(years, series)
        era = lambda a, b: float(np.mean(  # noqa: E731
            [series[years.index(y)] for y in range(a, b + 1)]))
        out[key] = [round(float(v), 2) for v in series]
        out[key + "_stats"] = {
            "slope_per_year": round(float(lr.slope), 4),
            "p_value": float(f"{lr.pvalue:.3g}"),
            "pct_per_decade": round(float(lr.slope * 10 / series.mean() * 100), 1),
            "clim_mean": round(era(*CLIM), 2),
            "recent_mean": round(era(*RECENT), 2),
            "previous_mean": round(era(*PREVIOUS), 2),
        }
        out[key + "_stats"]["previous_to_clim_pct"] = round(
            (out[key + "_stats"]["clim_mean"]
             / out[key + "_stats"]["previous_mean"] - 1) * 100, 1)

    # The drought backtest, stated as a rank rather than a fitted score:
    # how many canonical surge years land in the index's own top ten.
    order = sorted(years, key=lambda y: -out["cwd_yr_mm"][years.index(y)])
    top10 = order[:10]
    out["cwd_top10"] = top10
    out["cwd_canonical_hits"] = sorted(set(top10) & set(CANONICAL))
    out["cwd_canonical_misses"] = sorted(set(CANONICAL) - set(top10))

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    s = out["frost_days_stats"]
    d = out["cwd_yr_mm_stats"]
    print(f"wrote {args.out}: {len(years)} years, {len(names)} districts")
    print(f"  frost {s['clim_mean']:.1f} d ({s['pct_per_decade']:+.1f}%/decade, "
          f"p={s['p_value']}), drought {d['clim_mean']:.0f} mm "
          f"({d['pct_per_decade']:+.1f}%/decade, p={d['p_value']})")
    print(f"  canonical years in the drought top ten: "
          f"{len(out['cwd_canonical_hits'])} of {len(CANONICAL)} "
          f"(missing {out['cwd_canonical_misses']})")


if __name__ == "__main__":
    main()
