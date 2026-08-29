"""Per-district daily climate from HadUK-Grid 5 km, 1960-2025.

Gate 2. Turns 2,376 gridded monthly files into a district x year table so
the subsidence and freeze legs can vary by GEOGRAPHY rather than riding a
single national series. Two indices come out, and they want opposite
things from the same data:

  SMD    an INTEGRAL. Clay shrink-swell tracks soil moisture deficit,
         which accumulates potential evapotranspiration net of rainfall
         over months. Hargreaves-Samani PET is used because it needs only
         tasmax/tasmin/latitude - the daily RANGE is its radiation proxy,
         which is what separates a hot SUNNY summer (foundations crack)
         from a hot cloudy one (they do not).
  FREEZE an EVENT DETECTOR. Pipes burst on the THAW after a spell deep
         enough to reach pipework in unheated voids, so what matters is
         RUNS of consecutive tasmin < 0, their accumulated severity, and
         how fast tasmax comes back up afterwards. The model's current
         air-frost DAY COUNT cannot see any of that: 30 isolated frosts
         and one ten-day freeze score the same.

WHY 5 km. Measured against the 2,736 published districts (see
fetch_haduk.py): at 12 km, 84% of households sit in a cell shared with
another district and one cell holds 89 of them - a national index, not a
geography. At 5 km that falls to 40% and 2,131 districts resolve
separately. 1 km resolves all but 42 and needs 174 GB, which did not fit.

SAMPLING. Area-weighted overlap of each district polygon with the grid,
NOT nearest-centroid. A large rural district spanning four cells should
be the average of what happened across it; centroid sampling would give
it whichever cell its middle landed in. Weights are renormalised over
LAND cells only - the sea is NaN, and letting it in would drag coastal
districts toward zero rainfall. Districts whose polygon misses every land
cell (small, entirely-coastal ones) fall back to the nearest land cell,
and the count of those is printed rather than hidden.

This script MEASURES. It writes data/haduk_district_annual.csv and
changes no model input. Nothing here is wired into build_model.

Usage:
  haduk_district_daily.py                  # 1960-2025, the full table
  haduk_district_daily.py --from 1975 --to 1976   # shape check
"""

import argparse
import glob
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
HADUK = os.path.join(ROOT, "data", "haduk")
DISTRICTS = os.path.join(ROOT, "data", "districts_risk.geojson")
OUT = os.path.join(ROOT, "data", "haduk_district_annual.csv")

# Soil moisture store, mm. A simple single-bucket cap: SMD accumulates
# PET net of rainfall and cannot exceed the store the soil can give up.
# 150 mm is the conventional value for a clay profile under grass and is
# used here only to bound the integral - the index that matters is the
# RELATIVITY between districts, and the cap moves every district the same
# way. It is NOT a model parameter; nothing downstream reads it yet.
SMD_CAP = 150.0

# A freeze SPELL is >= this many consecutive days of air frost. Three
# days is the shortest spell that gets frost through the fabric to
# pipework in an unheated void; single-night frosts do not burst pipes.
SPELL_MIN_DAYS = 3


def grid_geometry(path):
    """Cell edges and the land mask, from any one file."""
    import xarray as xr
    with xr.open_dataset(path) as ds:
        var = next(v for v in ds.data_vars
                   if v in ("tasmin", "tasmax", "rainfall"))
        a = ds[var]
        x = ds["projection_x_coordinate"].values
        y = ds["projection_y_coordinate"].values
        land = np.isfinite(a.isel(time=0).values)
    return x, y, land


def overlap_weights(x, y, land):
    """Sparse district x land-cell area-weight matrix."""
    import geopandas as gpd
    from shapely.geometry import box
    from scipy import sparse

    gdf = gpd.read_file(DISTRICTS).to_crs(27700)
    dx = float(np.diff(x)[0])
    dy = float(np.diff(y)[0])
    iy, ix = np.nonzero(land)
    cells = gpd.GeoDataFrame(
        {"cell": np.arange(len(iy))},
        geometry=[box(x[j] - dx / 2, y[i] - dy / 2, x[j] + dx / 2,
                      y[i] + dy / 2) for i, j in zip(iy, ix)],
        crs=27700)

    join = gpd.overlay(
        gdf[["geometry"]].reset_index(names="dist"), cells, how="intersection")
    join["w"] = join.geometry.area
    rows = join["dist"].to_numpy()
    cols = join["cell"].to_numpy()
    vals = join["w"].to_numpy()

    n_d, n_c = len(gdf), len(iy)
    # districts that overlap no land cell at all -> nearest land cell
    covered = np.zeros(n_d, dtype=bool)
    covered[rows] = True
    missing = np.nonzero(~covered)[0]
    if len(missing):
        cx, cy = x[ix], y[iy]
        c = gdf.geometry.centroid
        for d in missing:
            k = int(np.argmin((cx - c.x.iloc[d]) ** 2
                              + (cy - c.y.iloc[d]) ** 2))
            rows = np.append(rows, d)
            cols = np.append(cols, k)
            vals = np.append(vals, 1.0)
    print(f"  {n_d} districts, {n_c} land cells; "
          f"{len(missing)} districts fell back to nearest cell", flush=True)

    W = sparse.csr_matrix((vals, (rows, cols)), shape=(n_d, n_c))
    W = sparse.diags(1.0 / np.asarray(W.sum(1)).ravel()) @ W   # rows sum to 1
    return gdf, W, iy, ix


def hargreaves_ra(lat_deg, doy):
    """Extraterrestrial radiation, mm/day equivalent. FAO-56 eq. 21."""
    phi = np.radians(lat_deg)[:, None]
    j = doy[None, :]
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365.0)
    dec = 0.409 * np.sin(2 * np.pi * j / 365.0 - 1.39)
    # clipped so polar-night/day maths stays finite at UK latitudes
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1.0, 1.0))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(dec)
        + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return ra * 0.408                                     # MJ/m2/day -> mm/day


def months(year_from, year_to):
    pat = os.path.join(HADUK, "**", "tasmin_*_5km_day_*.nc")
    out = []
    for f in glob.glob(pat, recursive=True):
        m = re.search(r"_(\d{4})(\d{2})\d{2}-", os.path.basename(f))
        y, mo = int(m.group(1)), int(m.group(2))
        if year_from <= y <= year_to:
            out.append((y, mo, f))
    return sorted(out)


def sibling(path, var):
    b = os.path.basename(path).replace("tasmin_", var + "_", 1)
    return os.path.join(os.path.dirname(path).replace("tasmin", var), b)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="y0", type=int, default=1960)
    ap.add_argument("--to", dest="y1", type=int, default=2025)
    args = ap.parse_args()

    import xarray as xr

    todo = months(args.y0, args.y1)
    if not todo:
        raise SystemExit("no 5 km files in range - run fetch_haduk.py --res 5km")
    print(f"{len(todo)} months, {args.y0}-{args.y1}", flush=True)

    x, y, land = grid_geometry(todo[0][2])
    gdf, W, iy, ix = overlap_weights(x, y, land)
    # centroid in BNG, THEN reprojected - taking a centroid in a
    # geographic CRS is what geopandas warns about, and gets it wrong.
    lat = gdf.geometry.centroid.to_crs(4326).y.to_numpy()
    n_d = len(gdf)

    # carried ACROSS months and years - SMD is a running integral, and a
    # freeze spell does not stop at a month boundary
    smd = np.zeros(n_d)
    cwd = np.zeros(n_d)          # the same integral with NO cap - see below
    run_len = np.zeros(n_d, dtype=int)
    run_sev = np.zeros(n_d)

    acc, rows = {}, []
    t0 = time.time()
    for n, (yr, mo, f) in enumerate(todo, 1):
        with xr.open_dataset(f) as ds:
            tn = ds["tasmin"].values[:, iy, ix]
            # real day-of-year off the file's own time axis, so leap
            # years are right - a hand-rolled month-length table puts
            # everything after 29 February one day out
            doy = ds["time"].dt.dayofyear.values.astype(float)
        with xr.open_dataset(sibling(f, "tasmax")) as ds:
            tx = ds["tasmax"].values[:, iy, ix]
        with xr.open_dataset(sibling(f, "rainfall")) as ds:
            rn = ds["rainfall"].values[:, iy, ix]
        # grid -> district, area-weighted. nan_to_num is safe because the
        # weights already exclude sea cells; any NaN left is a masked land
        # cell, and zeroing it inside a renormalised row is the same as
        # dropping it.
        tn, tx, rn = ((W @ np.nan_to_num(v).T).T for v in (tn, tx, rn))
        # EVERYTHING from here is (days, districts). The transform above
        # returns that shape, and mixing it with the (districts, days) that
        # hargreaves_ra returns is the one broadcast that silently fits.
        nd = tn.shape[0]
        ra = hargreaves_ra(lat, doy).T                         # -> days x dist
        tmean = 0.5 * (tn + tx)
        pet = 0.0023 * ra * (tmean + 17.8) * np.sqrt(
            np.clip(tx - tn, 0, None))

        a = acc.setdefault((yr), {
            "rain": np.zeros(n_d), "tmax": np.zeros(n_d),
            "tmin": np.zeros(n_d), "pet": np.zeros(n_d), "days": 0,
            "smd_max": np.zeros(n_d), "smd_jja": np.zeros(n_d),
            "cwd_max": np.zeros(n_d),
            "jja_days": 0, "frost_days": np.zeros(n_d),
            "spells": np.zeros(n_d), "worst_spell": np.zeros(n_d),
            "spell_days": np.zeros(n_d)})
        a["rain"] += rn.sum(0)          # sum over DAYS, one value per district
        a["tmax"] += tx.sum(0)
        a["tmin"] += tn.sum(0)
        a["pet"] += pet.sum(0)
        a["days"] += nd

        for d in range(nd):
            smd = np.clip(smd + pet[d] - rn[d], 0.0, SMD_CAP)
            a["smd_max"] = np.maximum(a["smd_max"], smd)
            # Same running integral without the cap. SMD_CAP is physically
            # right - soil cannot give up more water than it holds - but it
            # destroys the index: 94-96% of districts peg at 150 mm and
            # 1976 becomes indistinguishable from 1975. The uncapped
            # deficit is not a soil state, it is a DROUGHT SEVERITY
            # measure, and it is the one that discriminates.
            cwd = np.maximum(cwd + pet[d] - rn[d], 0.0)
            a["cwd_max"] = np.maximum(a["cwd_max"], cwd)
            if mo in (6, 7, 8):
                a["smd_jja"] += smd
            frost = tn[d] < 0.0
            a["frost_days"] += frost
            run_len = np.where(frost, run_len + 1, 0)
            run_sev = np.where(frost, run_sev - np.minimum(tn[d], 0.0), 0.0)
            # a spell is BANKED the day it reaches the threshold, and
            # keeps deepening while it lasts
            hit = run_len == SPELL_MIN_DAYS
            a["spells"] += hit
            deep = run_len >= SPELL_MIN_DAYS
            a["spell_days"] += deep
            a["worst_spell"] = np.maximum(a["worst_spell"],
                                          np.where(deep, run_sev, 0.0))
        if mo in (6, 7, 8):
            a["jja_days"] += nd
        if n % 60 == 0:
            print(f"  {n}/{len(todo)} months "
                  f"({(time.time() - t0) / 60:.1f} min)", flush=True)

    for yr in sorted(acc):
        a = acc[yr]
        if a["days"] < 365:                     # partial year, do not emit
            continue
        for i, code in enumerate(gdf["name"]):
            rows.append({
                "district": code, "year": yr,
                "rain_mm": round(float(a["rain"][i]), 1),
                "tmax_mean_c": round(float(a["tmax"][i]) / a["days"], 2),
                "tmin_mean_c": round(float(a["tmin"][i]) / a["days"], 2),
                "pet_mm": round(float(a["pet"][i]), 1),
                "smd_max_mm": round(float(a["smd_max"][i]), 1),
                "cwd_max_mm": round(float(a["cwd_max"][i]), 1),
                "smd_jja_mean_mm": round(
                    float(a["smd_jja"][i]) / max(a["jja_days"], 1), 1),
                "frost_days": int(a["frost_days"][i]),
                "freeze_spells": int(a["spells"][i]),
                "freeze_spell_days": int(a["spell_days"][i]),
                "worst_spell_degc_days": round(float(a["worst_spell"][i]), 1),
            })

    import csv
    with open(OUT, "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"\nwrote {OUT}: {len(rows):,} rows "
          f"({len(acc)} years x {n_d} districts), "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
