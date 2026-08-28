"""Daily tmin/tmax/rainfall 1960-2025 from ERA5, via the Open-Meteo archive.

The CROSS-CHECK arm of Gate 0. HadUK-Grid (scripts/fetch_haduk.py) is the
primary daily source; this is the same three variables from a different
kind of product entirely - ERA5 is a reanalysis, HadUK-Grid is an
interpolation of station observations. They will not agree exactly, and
the point is to find out by how much BEFORE a subsidence or freeze curve
is fitted to either.

That caution is earned. The last time this repo compared two wind
surfaces (compare_gust_surfaces.py, MIDAS stations vs ERA5 grid) they
disagreed materially - rp50 105-211 km/h against 124-196 - and the choice
between them moved the published model. A soil-moisture integral and a
cold-spell detector are both threshold-nonlinear, so they may be MORE
source-sensitive than a wind extreme, not less.

Open-Meteo needs no key and no token, which is the other reason this arm
exists: the CEDA token expired and only the account holder can renew it.
DATA_SOURCES #14 already records ERA5-via-Open-Meteo as this project's
no-CEDA fallback, and it is where history.csv's jja_deficit and jja_tmax
came from.

WHICH POINTS. Not a lat/lon grid - most of one is sea, and a plain land
grid weights the Highlands the same as London. Instead the district
centroids in data/districts_risk.geojson are binned coarsely and the
HIGHEST-HOUSEHOLD district in each bin wins. Every point is therefore on
land, and the set is spread geographically while leaning where the
exposure is. That matters because these points feed a NATIONAL index that
gets compared against ABI claim counts, and ABI counts are exposure-
weighted whether or not anyone says so.

This pass is the national index. Per-district relativities want the 12 km
HadUK-Grid field, not 60-odd interpolated points.

Resume-safe: each point is cached under data/cache/era5_daily/ and
skipped on rerun (this machine sleeps mid-run).

Usage:
  fetch_era5_daily.py                 # ~60 points, 1960-2025
  fetch_era5_daily.py --points 30     # coarser, faster
  fetch_era5_daily.py --list-only     # choose points, fetch nothing
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DISTRICTS = os.path.join(ROOT, "data", "districts_risk.geojson")
CACHE = os.path.join(ROOT, "data", "cache", "era5_daily")
API = "https://archive-api.open-meteo.com/v1/archive"
START, END = "1960-01-01", "2025-12-31"
DAILY = "temperature_2m_min,temperature_2m_max,precipitation_sum"
BATCH = 2            # points per call; 66 years of daily is a large response
PAUSE = 45.0         # Open-Meteo is free and rate-limited - be a good guest
RETRIES = 12


def seconds_to_next_hour():
    """Seconds until the wall clock rolls over to :00."""
    now = time.time()
    return 3600.0 - (now % 3600.0)


def exterior_rings(geom):
    """Every exterior ring in a geometry, whatever its type.

    data/districts_risk.geojson is not uniformly Polygon: 2,727 are, one
    is MultiPolygon, and EIGHT are GeometryCollection (BS2 among them),
    which has `geometries` and no `coordinates` at all. Anything walking
    this file has to handle all three or it dies eight features in.
    """
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"][0]]
    if t == "MultiPolygon":
        return [part[0] for part in geom["coordinates"]]
    if t == "GeometryCollection":
        out = []
        for sub in geom.get("geometries", []):
            out.extend(exterior_rings(sub))
        return out
    return []


def centroid(geom):
    """Mean of the largest exterior ring. Districts are small; precision
    here is irrelevant next to ERA5's ~28 km native cell."""
    rings = exterior_rings(geom)
    if not rings:
        return None
    a = np.asarray(max(rings, key=len), dtype=float)
    return float(a[:, 0].mean()), float(a[:, 1].mean())


def interleave(points):
    """Order points so that EVERY PREFIX is a national spread.

    Learned the hard way. The first run ordered north-to-south, hit
    Open-Meteo's hourly cap after six calls, and left 12 cached points
    that were all Highlands and Islands - PH33, IV x4, AB42, HS2, KW x3,
    ZE x2, and not one in England or Wales. A partial fetch like that
    cannot produce a national index at all, so an interrupted run was
    worth nothing rather than proportionally less.

    Farthest-point traversal fixes it: start at the largest district,
    then repeatedly take whichever point is furthest from everything
    taken so far. Stop the run at any moment and what is on disk is a
    coarse but genuinely national sample. Since this job is rate-limited
    into multiple hours on a laptop that sleeps, partial IS the normal
    case.
    """
    remaining = sorted(points, key=lambda t: -t[3])
    out = [remaining.pop(0)]
    while remaining:
        best_i, best_d = 0, -1.0
        for i, (_, la, lo, _) in enumerate(remaining):
            # equirectangular is ample for ordering; no need for haversine
            d = min((la - b[1]) ** 2
                    + ((lo - b[2]) * np.cos(np.radians(la))) ** 2
                    for b in out)
            if d > best_d:
                best_i, best_d = i, d
        out.append(remaining.pop(best_i))
    return out


def pick_points(target):
    """Exposure-weighted, geographically spread district centroids."""
    with open(DISTRICTS, encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    pts, skipped = [], 0
    for f in feats:
        c = centroid(f["geometry"] or {})
        if c is None:
            skipped += 1
            continue
        lon, lat = c
        p = f["properties"]
        pts.append((p["name"], lat, lon, float(p.get("households") or 0.0)))
    if skipped:
        print(f"  WARNING: {skipped} districts had no usable ring", flush=True)
    lats = [p[1] for p in pts]
    lons = [p[2] for p in pts]
    if not (49 < min(lats) < 62 and -9 < min(lons) < 3):
        raise SystemExit(
            f"centroids do not look like WGS84 UK "
            f"(lat {min(lats):.1f}..{max(lats):.1f}, "
            f"lon {min(lons):.1f}..{max(lons):.1f})")

    # Bin size chosen so the number of OCCUPIED bins lands near `target`.
    # Longitude bins are widened by 1/cos(lat) so bins are roughly square
    # on the ground rather than squeezed at 58N.
    span_lat = max(lats) - min(lats)
    lo, hi = 0.15, 6.0
    best = None
    for _ in range(40):
        step = (lo + hi) / 2
        chosen = {}
        for name, lat, lon, hh in pts:
            key = (int((lat - min(lats)) / step),
                   int((lon - min(lons)) / (step / np.cos(np.radians(lat)))))
            if key not in chosen or hh > chosen[key][3]:
                chosen[key] = (name, lat, lon, hh)
        n = len(chosen)
        best = chosen
        if n > target:
            lo = step
        else:
            hi = step
        if abs(n - target) <= max(2, target // 20):
            break
    out = interleave(list(best.values()))
    print(f"  {len(out)} points from {len(pts)} districts "
          f"(lat {min(lats):.1f}..{max(lats):.1f}, "
          f"lon {min(lons):.1f}..{max(lons):.1f}), span {span_lat:.1f} deg",
          flush=True)
    return out


def fetch(chunk):
    q = dict(
        latitude=",".join(f"{la:.3f}" for _, la, _, _ in chunk),
        longitude=",".join(f"{lo:.3f}" for _, _, lo, _ in chunk),
        start_date=START, end_date=END, daily=DAILY, timezone="UTC",
    )
    url = API + "?" + urllib.parse.urlencode(q)
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=900) as r:
                data = json.load(r)
            return data if isinstance(data, list) else [data]
        except Exception as e:            # noqa: BLE001 - retried, then raised
            msg = str(e)
            if "429" in msg:
                # Open-Meteo's free cap is HOURLY and weighted by
                # locations x days x variables, so one 66-year 2-point
                # 3-variable call is worth ~100 ordinary ones and about
                # six of them exhaust the hour. The reply says so
                # verbatim: "Hourly API request limit exceeded. Please
                # try again in the next hour." Retrying on a 150 s timer
                # therefore just burns all the attempts inside the same
                # dead hour and exits having fetched nothing - which is
                # exactly what the first run did. Sleep to the boundary.
                wait = seconds_to_next_hour() + 90
                print(f"    hourly cap hit - sleeping "
                      f"{wait / 60:.1f} min to the next hour "
                      f"(attempt {attempt + 1}/{RETRIES})", flush=True)
            else:
                wait = 20
                print(f"    retry {attempt + 1} (wait {wait}s): "
                      f"{msg[:120]}", flush=True)
            time.sleep(wait)
    raise SystemExit("open-meteo failed after retries")


def cache_path(name):
    return os.path.join(CACHE, name.replace("/", "_") + ".npz")


def store(name, daily):
    """Save one point as float32 arrays plus the date axis."""
    def arr(key):
        return np.array([np.nan if v is None else v
                         for v in daily[key]], dtype=np.float32)
    dates = np.array(daily["time"], dtype="U10")
    np.savez_compressed(
        cache_path(name), dates=dates,
        tmin=arr("temperature_2m_min"),
        tmax=arr("temperature_2m_max"),
        rain=arr("precipitation_sum"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--points", type=int, default=60)
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    print(f"ERA5 daily {START}..{END} via Open-Meteo", flush=True)
    points = pick_points(args.points)
    todo = [p for p in points if not os.path.exists(cache_path(p[0]))]
    print(f"  {len(points)} points, {len(points) - len(todo)} cached, "
          f"{len(todo)} to fetch "
          f"(~{len(todo) / BATCH * PAUSE / 60:.0f} min at {PAUSE:.0f}s/batch)",
          flush=True)
    if args.list_only:
        for name, la, lo, hh in points:
            print(f"    {name:>6}  {la:6.2f} {lo:7.2f}  {hh:>9,.0f} hh")
        return
    if not todo:
        print("all points already cached", flush=True)
        return

    t0 = time.time()
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        for (name, la, lo, _), res in zip(chunk, fetch(chunk)):
            d = res["daily"]
            store(name, d)
            n = len(d["time"])
            print(f"  [{i + 1:>3}/{len(todo)}] {name:>6} "
                  f"{la:6.2f} {lo:7.2f}  {n:,} days", flush=True)
        if i + BATCH < len(todo):
            time.sleep(PAUSE)
    print(f"complete: {len(todo)} points in "
          f"{(time.time() - t0) / 60:.1f} min, cached under {CACHE}",
          flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    # A four-hour job on a laptop that sleeps WILL die at some point, and
    # the first time it did so it left exit code 1 and not one word of
    # explanation - stderr went nowhere useful. Anything that reaches
    # here now says so on stdout, which is the stream being tailed.
    try:
        main()
    except BaseException as e:                 # noqa: BLE001 - re-raised
        import traceback
        print("", flush=True)
        print(f"DIED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise
