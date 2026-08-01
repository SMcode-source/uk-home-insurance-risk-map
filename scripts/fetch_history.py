"""Historical per-year hazard drivers for the backtest (ERA5 via Open-Meteo).

Pulls daily gusts, precipitation and max temperature 1990-2024 for a small
set of representative UK points, and reduces each calendar year to national
hazard-driver indices:

  storm_days   mean count of days with gust >= 70 km/h
  max_gust     mean annual maximum gust (km/h)
  rain5d       mean annual maximum 5-day rainfall total (mm) - flood driver
  jja_deficit  mean JJA rainfall shortfall vs the point's own 1991-2020
               JJA mean (mm) - the shrink-swell subsidence driver
  jja_tmax     mean JJA daily max temperature (degC)

This validates the model's PERIL DRIVERS against real years. It does not
validate loss amounts - that needs claims data.

Output: data/history.csv (year + the five indices)
"""

import csv
import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np

OUT = os.path.join("data", "history.csv")
API = "https://archive-api.open-meteo.com/v1/archive"
START, END = "1990-01-01", "2024-12-31"
BATCH = 2
PAUSE = 45.0
GUST_THRESHOLD = 70.0     # km/h, ~ a named-storm gust inland

# Representative spread: Atlantic west, exposed north, dry south-east,
# the clay belt, and the flood-prone north-west / Humber.
POINTS = [
    (50.4, -4.8, "Cornwall"), (51.5, -0.1, "London"),
    (51.45, -2.6, "Bristol"), (52.5, -1.9, "Birmingham"),
    (53.5, -2.2, "Manchester"), (53.75, -0.35, "Hull"),
    (54.6, -3.1, "Cumbria"), (55.9, -3.2, "Edinburgh"),
    (57.5, -4.2, "Highlands"), (52.6, 1.3, "Norwich"),
    (51.05, -1.8, "Salisbury"), (53.4, -3.0, "Liverpool"),
]


def fetch(chunk):
    q = dict(
        latitude=",".join(f"{la:.3f}" for la, _, _ in chunk),
        longitude=",".join(f"{lo:.3f}" for _, lo, _ in chunk),
        start_date=START, end_date=END,
        daily="wind_gusts_10m_max,precipitation_sum,temperature_2m_max",
        timezone="UTC",
    )
    url = API + "?" + urllib.parse.urlencode(q)
    for attempt in range(12):
        try:
            with urllib.request.urlopen(url, timeout=600) as r:
                data = json.load(r)
            return data if isinstance(data, list) else [data]
        except Exception as e:
            wait = 150 if "429" in str(e) else 15
            print(f"    retry {attempt + 1} (wait {wait}s): {e}", flush=True)
            time.sleep(wait)
    raise SystemExit("open-meteo failed")


def reduce_point(daily):
    """-> {year: (storm_days, max_gust, rain5d, jja_rain, jja_tmax)}"""
    dates = daily["time"]
    gust = np.array([v if v is not None else np.nan
                     for v in daily["wind_gusts_10m_max"]], dtype=float)
    rain = np.array([v if v is not None else np.nan
                     for v in daily["precipitation_sum"]], dtype=float)
    tmax = np.array([v if v is not None else np.nan
                     for v in daily["temperature_2m_max"]], dtype=float)
    # rolling 5-day rainfall
    kern = np.ones(5)
    r5 = np.convolve(np.nan_to_num(rain), kern, mode="same")

    years = sorted({d[:4] for d in dates})
    idx = {y: [] for y in years}
    for i, d in enumerate(dates):
        idx[d[:4]].append(i)

    out = {}
    for y, ii in idx.items():
        ii = np.array(ii)
        months = np.array([int(dates[i][5:7]) for i in ii])
        jja = ii[(months >= 6) & (months <= 8)]
        g = gust[ii]
        out[y] = (
            float(np.nansum(g >= GUST_THRESHOLD)),
            float(np.nanmax(g)),
            float(np.nanmax(r5[ii])),
            float(np.nansum(rain[jja])),
            float(np.nanmean(tmax[jja])),
        )
    return out


def main():
    per_point = []
    for i in range(0, len(POINTS), BATCH):
        chunk = POINTS[i:i + BATCH]
        for (la, lo, name), res in zip(chunk, fetch(chunk)):
            per_point.append((name, reduce_point(res["daily"])))
            print(f"  {name}", flush=True)
        time.sleep(PAUSE)

    years = sorted(per_point[0][1].keys())
    # each point's own 1991-2020 JJA rainfall normal
    normals = {}
    for name, d in per_point:
        base = [d[y][3] for y in years if 1991 <= int(y) <= 2020]
        normals[name] = float(np.mean(base))

    rows = []
    for y in years:
        sd = np.mean([d[y][0] for _, d in per_point])
        mg = np.mean([d[y][1] for _, d in per_point])
        r5 = np.mean([d[y][2] for _, d in per_point])
        deficit = np.mean([normals[n] - d[y][3] for n, d in per_point])
        tj = np.mean([d[y][4] for _, d in per_point])
        rows.append([y, round(sd, 2), round(mg, 1), round(r5, 1),
                     round(deficit, 1), round(tj, 2)])

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "storm_days", "max_gust", "rain5d",
                    "jja_deficit", "jja_tmax"])
        w.writerows(rows)
    print(f"wrote {OUT}: {len(rows)} years", flush=True)


if __name__ == "__main__":
    main()
