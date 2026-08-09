"""Station gust extremes from Met Office MIDAS Open (CEDA download).

The upgrade path over fetch_gusts.py: ERA5 reanalysis smooths gusts over
~31 km cells, while MIDAS stations measured them. Same reduction, better
observations — each station's daily gust maxima become

  gust_p98  : 98th percentile of daily gust maxima (routine storminess)
  gust_rp50 : 1-in-50-year gust, Gumbel fit to annual maxima

in the EXACT contract fetch_gusts.py established (x, y in EPSG:27700,
speeds in km/h), because scores_real._load_gusts() IDW-interpolates
whatever points it is given — station points are a drop-in.

CEDA requires an account (free, but a human signs up), so this script
CANNOT fetch. It processes a local download:

  1. register at https://services.ceda.ac.uk/cedasite/register/info/
  2. download the uk-mean-wind-obs dataset (any recent dataset-version)
     from  https://catalogue.ceda.ac.uk/uuid/91cb9985a6c2453d99084bde4ff5f314
     e.g. via the CEDA archive browser or, with an account,
     `wget -r -np -nH --user=... --ask-password
      https://dap.ceda.ac.uk/badc/ukmo-midas-open/data/uk-mean-wind-obs/`
     Keep whatever directory structure arrives; this script walks it.
  3. python scripts/gusts_from_midas.py <download-root>

Writes data/gusts_midas.csv by default. Swapping it in for the model is
DELIBERATELY a separate manual step (copy over data/gusts.csv and
rebuild) — replacing a committed model input should be a decision, not a
side effect of running a parser.

Files are BADC-CSV: `key,G,value...` header rows, then a `data` line,
a normal CSV header, rows, `end data`. Gust speeds arrive in KNOTS.
Only qc-version-1 files are used — qcv-0 is the unchecked feed.
"""

import argparse
import csv
import io
import os
import re
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_OUT = os.path.join(ROOT, "data", "gusts_midas.csv")

KNOT_KMH = 1.852
# A UK station gust above this is not weather, it is an instrument fault
# (the UK low-level record is 150 kn at Fraserburgh 1989).
MAX_PLAUSIBLE_KMH = 300.0
# Gumbel needs a real sample of annual maxima; a year needs most of its
# days observed or its "maximum" is just the maximum of a gap.
MIN_YEARS = 20
MIN_DAYS_PER_YEAR = 300
# Stations measure where THEY stand, not where homes do. The first real
# run's top extremes were Cairngorm summit (1,237 m, rp50 283 km/h) and
# Great Dun Fell (847 m) — true measurements of a climate no dwelling is
# exposed to, and IDW smeared them across the valley districts nearby
# (every top-10 mover vs ERA5 was a Sheffield district downwind of a
# 395 m moor). Highest sizeable UK settlements sit near 400 m; 300 m
# keeps every town while dropping summit stations. Stations with no
# height in their header are kept but counted.
MAX_STATION_ALTITUDE_M = 300.0


def parse_badc_csv(text):
    """(header dict, list of row dicts) from one BADC-CSV file.

    Header rows look like `location,G,51.479,-0.449` — key, a global
    flag, then one or more values. Data sit between a line whose first
    cell is `data` and one whose first cell is `end data`.
    """
    header = {}
    rows = []
    columns = None
    in_data = False
    for parts in csv.reader(io.StringIO(text)):
        if not parts:
            continue
        key = parts[0].strip().lower()
        if not in_data:
            if key == "data":
                in_data = True
            elif len(parts) >= 3:
                header.setdefault(key, parts[2:])
            continue
        if key == "end data":
            break
        if columns is None:
            columns = [c.strip() for c in parts]
            continue
        rows.append(dict(zip(columns, parts)))
    return header, rows


def station_location(header):
    """(lat, lon) from a data file's own header, or None.

    MIDAS Open files carry their station's coordinates in a `location`
    header row; the station-metadata capability file is preferred when
    present (see load_station_metadata) but a partial download without
    it should still work.
    """
    loc = header.get("location")
    if loc and len(loc) >= 2:
        try:
            lat, lon = float(loc[0]), float(loc[1])
            if 49.0 < lat < 61.5 and -8.5 < lon < 2.5:
                return lat, lon
        except ValueError:
            pass
    return None


def load_station_metadata(root):
    """src_id -> (lat, lon) from any station-metadata capability file."""
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            if "station-metadata" not in name or not name.endswith(".csv"):
                continue
            with open(os.path.join(base, name), encoding="utf-8",
                      errors="replace") as fh:
                _hdr, rows = parse_badc_csv(fh.read())
            for row in rows:
                try:
                    sid = str(int(float(row["src_id"])))
                    out[sid] = (float(row["station_latitude"]),
                                float(row["station_longitude"]))
                except (KeyError, ValueError):
                    continue
    return out


def is_obs_file(name):
    """A qc-version-1 observations file, never qcv-0, never metadata."""
    return (name.endswith(".csv") and "qcv-1" in name
            and "station-metadata" not in name
            and "change-log" not in name)


def collect_daily_maxima(root):
    """station src_id -> {'days': {date: kmh}, 'latlon': (lat, lon)}."""
    stations = {}
    meta = load_station_metadata(root)
    n_files = 0
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not is_obs_file(name):
                continue
            with open(os.path.join(base, name), encoding="utf-8",
                      errors="replace") as fh:
                header, rows = parse_badc_csv(fh.read())
            if not rows or "max_gust_speed" not in rows[0]:
                continue
            n_files += 1
            sid = (header.get("midas_station_id", [""])[0].strip()
                   or re.sub(r"^0+", "", name.split("_")[-3]
                             if name.count("_") >= 3 else ""))
            sid = str(int(sid)) if sid.isdigit() else (sid or name)
            st = stations.setdefault(sid, {"days": {}, "latlon": None,
                                           "alt": None})
            if st["latlon"] is None:
                st["latlon"] = meta.get(sid) or station_location(header)
            if st["alt"] is None:
                hrow = header.get("height")
                if hrow:
                    try:
                        st["alt"] = float(hrow[0])
                    except ValueError:
                        pass
            days = st["days"]
            for row in rows:
                v = row.get("max_gust_speed", "").strip()
                if not v:
                    continue
                try:
                    kmh = float(v) * KNOT_KMH
                except ValueError:
                    continue
                if not (0.0 < kmh < MAX_PLAUSIBLE_KMH):
                    continue
                day = row.get("ob_end_time", "")[:10]
                if len(day) == 10:
                    days[day] = max(days.get(day, 0.0), kmh)
    return stations, n_files


def reduce_station(days):
    """(gust_p98, gust_rp50) in km/h, or None if the record is too thin."""
    by_year = defaultdict(list)
    for day, v in days.items():
        by_year[day[:4]].append(v)
    ann_max = [max(vs) for vs in by_year.values()
               if len(vs) >= MIN_DAYS_PER_YEAR]
    if len(ann_max) < MIN_YEARS:
        return None
    daily = np.array(list(days.values()))
    loc, scale = stats.gumbel_r.fit(np.array(ann_max))
    rp50 = float(stats.gumbel_r.ppf(1 - 1 / 50, loc, scale))
    return float(np.percentile(daily, 98)), rp50


def main(root, out_path):
    from pyproj import Transformer
    to_bng = Transformer.from_crs(4326, 27700, always_xy=True)

    stations, n_files = collect_daily_maxima(root)
    print(f"{n_files} observation files, {len(stations)} stations",
          flush=True)
    if not n_files:
        raise SystemExit(
            f"no qcv-1 uk-mean-wind-obs files under {root} - is this the "
            f"right directory? Expected files like midas-open_uk-mean-"
            f"wind-obs_dv-202407_..._qcv-1_1995.csv")

    kept, thin, unlocated, high, no_alt = 0, 0, 0, 0, 0
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["x", "y", "gust_p98", "gust_rp50"])
        for sid in sorted(stations):
            st = stations[sid]
            if st["latlon"] is None:
                unlocated += 1
                continue
            if st["alt"] is None:
                no_alt += 1
            elif st["alt"] > MAX_STATION_ALTITUDE_M:
                high += 1
                continue
            reduced = reduce_station(st["days"])
            if reduced is None:
                thin += 1
                continue
            p98, rp50 = reduced
            lat, lon = st["latlon"]
            x, y = to_bng.transform(lon, lat)
            w.writerow([round(x), round(y), round(p98, 1), round(rp50, 1)])
            kept += 1
    print(f"kept {kept} stations "
          f"({thin} below {MIN_YEARS}y/{MIN_DAYS_PER_YEAR}d coverage, "
          f"{high} above {MAX_STATION_ALTITUDE_M:.0f} m, "
          f"{unlocated} without coordinates, "
          f"{no_alt} kept without a height record)", flush=True)
    # A "successful" run that kept a handful of stations would IDW a few
    # points across the whole country and silently degrade the weather
    # score. Refuse instead - the ERA5 grid stays in place until the
    # MIDAS set is actually better.
    if kept < 50:
        os.remove(out_path)
        raise SystemExit(
            f"only {kept} stations survived - not enough to beat the "
            f"ERA5 grid (>=50 needed). Output removed; nothing changed.")
    print(f"wrote {out_path}", flush=True)
    print("To use in the model: compare against data/gusts.csv, then "
          "copy over it and rebuild (README, rebuild section).")


# ---------------------------------------------------------------- selftest --

SELFTEST_STATION = """Conventions,G,BADC-CSV,1
title,G,synthetic test station
midas_station_id,G,{sid}
location,G,{lat},{lon}
height,G,{alt},m
data
ob_end_time,id,max_gust_speed,max_gust_speed_q
{rows}
end data
"""


def _selftest():
    """Build a synthetic MIDAS tree, run the pipeline, check the output.

    Verifies the parts a format drift would break silently: BADC-CSV
    framing, knots -> km/h, daily-max collapse of hourly rows, the
    coverage gate, and the station-metadata override. Real-data checks
    still happen on first genuine run (station count gate + the printed
    range for eyeballing against the ERA5 grid).
    """
    import tempfile
    rng = np.random.default_rng(42)
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "qc-version-1"))
        # 25 years for the good station; the thin station gets 5 years
        # and must be dropped; the summit station parses a 1200 m height
        # (the altitude gate itself lives in main's loop).
        for sid, lat, lon, alt, years in (("901", 51.5, -0.1, 25.0, 25),
                                          ("902", 53.0, -1.5, 80.0, 5),
                                          ("903", 57.1, -3.6, 1200.0, 25)):
            rows = []
            # 12 months x 28 days = 336 distinct dates per year, above
            # the 300-day coverage gate, with no invalid calendar dates
            for yy in range(2000, 2000 + years):
                for idx in range(336):
                    day = f"{yy}-{idx // 28 + 1:02d}-{idx % 28 + 1:02d}"
                    lo, hi = sorted(rng.gumbel(20, 6, size=2))
                    rows.append(f"{day} 09:00:00,{sid},{lo:.1f},0")
                    rows.append(f"{day} 18:00:00,{sid},{hi:.1f},0")
            path = os.path.join(
                tmp, "qc-version-1",
                f"midas-open_uk-mean-wind-obs_dv-202407_test_"
                f"{sid.zfill(5)}_x_qcv-1_{sid}.csv")
            with open(path, "w") as fh:
                fh.write(SELFTEST_STATION.format(
                    sid=sid, lat=lat, lon=lon, alt=alt,
                    rows="\n".join(rows)))

        stations, n_files = collect_daily_maxima(tmp)
        assert n_files == 3, f"expected 3 files, saw {n_files}"
        good = stations["901"]
        assert good["latlon"] == (51.5, -0.1)
        assert good["alt"] == 25.0, f"height row not parsed: {good['alt']}"
        assert stations["903"]["alt"] > MAX_STATION_ALTITUDE_M, (
            "the summit station must parse as above the altitude gate")
        # two obs per day must collapse to one daily maximum
        assert len(good["days"]) == 336 * 25, len(good["days"])
        reduced = reduce_station(good["days"])
        assert reduced is not None
        p98, rp50 = reduced
        # Gumbel(20,6) daily draws in knots: p98 of daily max ~ 40 kn
        # (74 km/h), rp50 of annual max comfortably above p98
        assert 55 < p98 < 110, f"p98 {p98:.1f} km/h out of range"
        assert rp50 > p98, "1-in-50 must exceed the 98th percentile"
        assert reduce_station(stations["902"]["days"]) is None, (
            "a 5-year record must be rejected, not Gumbel-fitted")
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?",
                    help="directory holding the CEDA uk-mean-wind-obs "
                         "download (walked recursively)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        sys.exit(0)
    if not args.root:
        ap.error("root directory required (or --selftest)")
    main(args.root, args.out)
