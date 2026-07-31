"""Storm gust extremes from ERA5 reanalysis (Open-Meteo archive API,
free/anonymous; ERA5 is ECMWF, not Met Office — documented in
DATA_SOURCES.md).

Samples a ~0.5 deg grid over GB, pulls 35 years (1990-2024) of daily
10 m wind-gust maxima per point, and reduces each point to:
  gust_p98  : 98th percentile of daily gust maxima (routine storminess)
  gust_rp50 : 1-in-50-year gust from a Gumbel fit to annual maxima
              (extreme-value upgrade over climatological means)

Output: data/gusts.csv (x, y in EPSG:27700, gust_p98, gust_rp50 in km/h)
"""

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import shapely
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import load_districts  # noqa: E402

OUT = os.path.join("data", "gusts.csv")
API = "https://archive-api.open-meteo.com/v1/archive"
START, END = "1990-01-01", "2024-12-31"
BATCH = 2           # free tier weights calls by data volume; stay gentle
PAUSE = 45.0        # seconds between batches


def grid_points():
    """~0.5 deg grid, kept only within 0.4 deg of any district."""
    gdf = load_districts()
    hull = shapely.unary_union(gdf.geometry.simplify(0.01).values).buffer(0.4)
    lats = np.arange(49.9, 60.9, 0.55)
    lons = np.arange(-7.6, 1.9, 0.75)
    pts = [(la, lo) for la in lats for lo in lons
           if shapely.intersects(hull, shapely.points(lo, la))]
    return pts


def fetch_batch(pts):
    q = dict(
        latitude=",".join(f"{la:.3f}" for la, _ in pts),
        longitude=",".join(f"{lo:.3f}" for _, lo in pts),
        start_date=START, end_date=END,
        daily="wind_gusts_10m_max", timezone="UTC",
    )
    url = API + "?" + urllib.parse.urlencode(q)
    for attempt in range(12):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                data = json.load(r)
            return data if isinstance(data, list) else [data]
        except Exception as e:
            wait = 150 if "429" in str(e) else 10
            print(f"    retry {attempt + 1} (wait {wait}s): {e}", flush=True)
            time.sleep(wait)
    raise SystemExit("open-meteo batch failed")


def reduce_point(daily):
    g = np.array([v for v in daily["wind_gusts_10m_max"] if v is not None],
                 dtype=float)
    dates = daily["time"]
    years = {}
    for d, v in zip(dates, daily["wind_gusts_10m_max"]):
        if v is None:
            continue
        y = d[:4]
        years[y] = max(years.get(y, 0.0), v)
    ann_max = np.array(list(years.values()))
    loc, scale = stats.gumbel_r.fit(ann_max)
    rp50 = float(stats.gumbel_r.ppf(1 - 1 / 50, loc, scale))
    return float(np.percentile(g, 98)), rp50


def main():
    from pyproj import Transformer
    t = Transformer.from_crs(4326, 27700, always_xy=True)
    pts = grid_points()
    print(f"{len(pts)} grid points", flush=True)

    # resume: skip points already in the CSV (keyed by BNG coords)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, newline="") as fh:
            for row in csv.DictReader(fh):
                done.add((float(row["x"]), float(row["y"])))
    new_file = not done
    todo = []
    for la, lo in pts:
        x, y = t.transform(lo, la)
        if (round(x, 0), round(y, 0)) not in done:
            todo.append((la, lo, round(x, 0), round(y, 0)))
    if done:
        # quota economy on resume: gust climatology is smooth, thin the
        # remaining grid to every 2nd point
        todo = todo[::2]
    print(f"{len(done)} already fetched, {len(todo)} to go", flush=True)

    with open(OUT, "a", newline="") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["x", "y", "gust_p98", "gust_rp50"])
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            results = fetch_batch([(la, lo) for la, lo, _, _ in chunk])
            for (la, lo, x, y), res in zip(chunk, results):
                p98, rp50 = reduce_point(res["daily"])
                w.writerow([x, y, round(p98, 1), round(rp50, 1)])
            fh.flush()
            print(f"  {len(done) + min(i + BATCH, len(todo))}/{len(pts)}",
                  flush=True)
            time.sleep(PAUSE)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
