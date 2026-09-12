"""Two observational checks on how far ahead weather is knowable.

A. The longest free operational forecast. Open-Meteo's seasonal
   endpoint serves the NOAA CFSv2 ensemble and refuses any lead past
   217 days, so nothing free even claims to reach a year. For the
   leads it does cover, compare the ensemble spread and mean against
   the ERA5 1991-2020 distribution for the same calendar days. Once
   spread equals the climatological spread, the forecast is saying
   nothing the calendar did not.

B. The model's own two annual indices (data/temperature_series.json,
   66 years). Lag-1 autocorrelation and walk-forward one-year-ahead
   skill against honest baselines. If nothing beats climatology plus
   trend, that IS the one-year forecast of what this model consumes.

    python -u scripts/nwp/forecast_horizon.py
"""

import argparse
import json
import os
import ssl
import sys
import urllib.request
from datetime import date, datetime, timedelta

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
UA = {"User-Agent": "uk-home-insurance-risk-map (github.com/SMcode-source)"}

# Four points spanning the model's geography, so a single grid cell's
# quirk cannot carry the conclusion.
POINTS = [
    ("London", 51.51, -0.12),
    ("Manchester", 53.48, -2.24),
    ("Edinburgh", 55.95, -3.19),
    ("Cardiff", 51.48, -3.18),
]
SEASONAL = "https://seasonal-api.open-meteo.com/v1/seasonal"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def get(url, timeout=240):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout,
                                context=ssl.create_default_context()) as r:
        return json.loads(r.read())


def seasonal_information(variable="temperature_2m_max", max_days=216,
                         verbose=True):
    """Ensemble spread and mean against the climatological distribution,
    as a function of lead time."""
    rows = []
    for name, lat, lon in POINTS:
        if verbose:
            print(f"  {name}: seasonal ensemble + ERA5 climatology ...",
                  flush=True)
        seas = get(f"{SEASONAL}?latitude={lat}&longitude={lon}"
                   f"&daily={variable}&forecast_days={max_days}")
        blk = seas["daily"]
        members = sorted(k for k in blk if k.startswith(variable + "_member"))
        if not members:
            raise SystemExit(
                f"no ensemble members for {variable!r}; the seasonal API "
                f"returned only {sorted(blk)[:6]}. Note it answers 200 with "
                f"NO data block at all for an unknown six-hourly variable.")
        days = blk["time"]
        fc = np.array([[np.nan if v is None else v for v in blk[m]]
                       for m in members])

        era = get(f"{ARCHIVE}?latitude={lat}&longitude={lon}"
                  f"&start_date=1991-01-01&end_date=2020-12-31"
                  f"&daily={variable}&timezone=UTC")
        et = np.array(era["daily"]["time"])
        ev = np.array([np.nan if v is None else v
                       for v in era["daily"][variable]], dtype=float)
        emd = np.array([s[5:] for s in et])

        start = date.fromisoformat(days[0])
        for lead in range(0, max_days, 15):
            d = start + timedelta(days=lead)
            sel = np.zeros(len(ev), bool)
            for off in range(-7, 8):
                sel |= (emd == (d + timedelta(days=off)).strftime("%m-%d"))
            clim = ev[sel & np.isfinite(ev)]
            col = fc[:, lead]
            col = col[np.isfinite(col)]
            if col.size < 5 or clim.size < 20:
                continue
            csd = clim.std(ddof=1)
            rows.append({
                "point": name, "variable": variable, "lead_days": lead,
                "date": str(d),
                "ensemble_mean": float(col.mean()),
                "ensemble_sd": float(col.std(ddof=1)),
                "clim_mean": float(clim.mean()),
                "clim_sd": float(csd),
                "spread_ratio": float(col.std(ddof=1) / csd),
                "mean_shift_in_clim_sd": float(abs(col.mean() - clim.mean()) / csd),
            })
    return rows


def summarise_seasonal(rows):
    """Average the two diagnostics over the points, by lead."""
    out = []
    for lead in sorted({r["lead_days"] for r in rows}):
        sel = [r for r in rows if r["lead_days"] == lead]
        out.append({
            "lead_days": lead,
            "n_points": len(sel),
            "spread_ratio": float(np.mean([r["spread_ratio"] for r in sel])),
            "mean_shift_in_clim_sd":
                float(np.mean([r["mean_shift_in_clim_sd"] for r in sel])),
        })
    return out


def index_predictability(series_path=None, warmup=30):
    """Lag-1 memory and one-year-ahead skill of the model's own indices."""
    series_path = series_path or os.path.join(ROOT, "data",
                                              "temperature_series.json")
    ts = json.load(open(series_path))
    years = np.array(ts["years"], float)
    out = {}
    for key in ("cwd_yr_mm", "frost_days"):
        y = np.array(ts[key], float)
        n = len(y)
        lr = stats.linregress(years, y)
        detr = y - (lr.intercept + lr.slope * years)
        r1 = float(np.corrcoef(detr[:-1], detr[1:])[0, 1])
        t = r1 * np.sqrt((n - 3) / max(1 - r1 ** 2, 1e-12))
        p = float(2 * (1 - stats.t.cdf(abs(t), n - 3)))

        errs = {k: [] for k in ("climatology", "trend", "persistence",
                                "AR1 on detrended", "last 10y mean")}
        for i in range(warmup, n):
            hy, hv, tgt = years[:i], y[:i], y[i]
            l = stats.linregress(hy, hv)
            hdet = hv - (l.intercept + l.slope * hy)
            r = np.corrcoef(hdet[:-1], hdet[1:])[0, 1]
            fit = l.intercept + l.slope * years[i]
            errs["climatology"].append(hv.mean() - tgt)
            errs["trend"].append(fit - tgt)
            errs["persistence"].append(hv[-1] - tgt)
            errs["AR1 on detrended"].append(fit + r * hdet[-1] - tgt)
            errs["last 10y mean"].append(hv[-10:].mean() - tgt)

        rmse = {k: float(np.sqrt(np.mean(np.array(v) ** 2)))
                for k, v in errs.items()}
        base = rmse["climatology"]
        out[key] = {
            "n_years": n,
            "mean": float(y.mean()),
            "sd": float(y.std(ddof=1)),
            "trend_per_year": float(lr.slope),
            "trend_p": float(lr.pvalue),
            "detrended_sd": float(detr.std(ddof=1)),
            "lag1_autocorr_detrended": r1,
            "lag1_p": p,
            "lag_autocorr": {str(k): float(np.corrcoef(detr[:-k], detr[k:])[0, 1])
                             for k in (1, 2, 3, 5)},
            "backtest_years": n - warmup,
            "rmse": rmse,
            "skill_vs_climatology_pct":
                {k: float(100 * (1 - v / base)) for k, v in rmse.items()},
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "data",
                                                  "forecast_horizon.json"))
    ap.add_argument("--skip-seasonal", action="store_true")
    args = ap.parse_args(argv)

    result = {"generated": datetime.now().isoformat(timespec="seconds")}

    if not args.skip_seasonal:
        print("A. the longest free forecast, against climatology", flush=True)
        rows = []
        for var in ("temperature_2m_max", "precipitation_sum"):
            print(f"  variable: {var}", flush=True)
            rows += seasonal_information(var)
        result["seasonal_rows"] = rows
        for var in ("temperature_2m_max", "precipitation_sum"):
            s = summarise_seasonal([r for r in rows if r["variable"] == var])
            result[f"seasonal_summary_{var}"] = s
            print(f"\n  {var}: lead   spread/clim   |mean shift| in clim sd",
                  flush=True)
            for r in s:
                print(f"      {r['lead_days']:5d} d      {r['spread_ratio']:5.2f}"
                      f"          {r['mean_shift_in_clim_sd']:5.2f}", flush=True)
        print("\n  spread/clim -> 1 and shift -> 0 means the forecast has "
              "become the climatology.", flush=True)

    print("\nB. the model's own indices, one year ahead", flush=True)
    idx = index_predictability()
    result["index_predictability"] = idx
    for key, v in idx.items():
        print(f"\n  {key}: n={v['n_years']}, sd {v['sd']:.1f}, "
              f"trend {v['trend_per_year']:+.3f}/yr (p={v['trend_p']:.4f})",
              flush=True)
        print(f"    lag-1 autocorrelation of the detrended series "
              f"{v['lag1_autocorr_detrended']:+.3f} (p={v['lag1_p']:.3f})",
              flush=True)
        for k, s in v["skill_vs_climatology_pct"].items():
            print(f"      {k:20s} RMSE {v['rmse'][k]:7.2f}   "
                  f"skill vs climatology {s:+6.1f}%", flush=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=1)
    print(f"\nwrote {args.out}", flush=True)
    return result


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
