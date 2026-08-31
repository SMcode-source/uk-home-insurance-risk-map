"""Per-district daily climate from HadUK-Grid 1 km, streamed year by year.

Same output as haduk_district_daily.py and the same indices; the only
difference is resolution, and the resolution is why this script exists
separately.

WHY IT STREAMS. The full 1 km set is 174 GB (measured: 73.4 MB/file,
2,376 files) against 103 GB free. It does not fit, and it does not need
to - nothing downstream ever wants the grids, only the district table.
So each year is fetched (~2.6 GB), extracted, and DELETED before the next
one starts. Peak disk is about 3 GB regardless of how many years run.

WHY 1 km IS WORTH THE 14 HOURS. Measured against the 2,736 published
districts: at 12 km, 84% of households sit in a cell shared with another
district and one cell holds 89 of them. At 5 km that is 40% and 45. At
1 km it is 0% and 8 - every district but 42 gets its own cell. For the
subsidence leg that matters most in dense London clay, where a 5 km cell
still swallows up to 45 districts whole.

The honest caveat, recorded because it does not go away by ignoring it:
HadUK-Grid is INTERPOLATED from a station network, so 1 km grid spacing
is not 1 km of independent information. The extra resolution is real
where stations are dense and is smooth interpolation where they are not.
It buys district SEPARATION, not necessarily district ACCURACY.

SAMPLING. Point-in-polygon on cell centres, not area-weighted overlap. At
1 km a cell is small against a postcode district, so the two agree, and
the point join is far cheaper over 245,077 cells. Districts containing no
cell centre fall back to the nearest cell, and that count is printed.

RESUME. State is checkpointed after every year, because this machine
sleeps mid-run and 14 hours will not survive in one piece. Rerun the
same command and it picks up at the first unfinished year - the SMD and
freeze-spell integrals are carried in the checkpoint, so a resumed run
gives the same answer as an uninterrupted one.

This script MEASURES. Nothing here is wired into build_model.

Usage:
  haduk_1km_stream.py                    # 1960-2025, resumable
  haduk_1km_stream.py --from 2020        # a shorter pass
  haduk_1km_stream.py --keep             # do not delete the grids
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
HADUK = os.path.join(ROOT, "data", "haduk", "1km")
# The polygon set and the output/state paths are module globals so that
# append_csv and the helpers see one consistent set; --polygons/--tag
# rebind them in main() before any use. The tag keeps a sector run's
# checkpoint, weights cache and CSV from colliding with the district
# run's - a stale 2,736-district weights cache silently applied to
# 10,398 sectors would be the quiet kind of wrong.
DISTRICTS = os.path.join(ROOT, "data", "districts_risk.geojson")
OUT = os.path.join(ROOT, "data", "haduk_district_annual_1km.csv")
CKPT = os.path.join(ROOT, "data", "haduk_1km_state.npz")
WCACHE = os.path.join(ROOT, "data", "haduk_1km_weights.npz")

SMD_CAP = 150.0          # see haduk_district_daily.py for why both are kept
SPELL_MIN_DAYS = 3
VARS = ("tasmin", "tasmax", "rainfall")


def fetch_year(year):
    cmd = [sys.executable, "-u", os.path.join(HERE, "fetch_haduk.py"),
           "--res", "1km", "--from", str(year), "--to", str(year)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"fetch failed for {year}:\n{r.stdout[-2000:]}\n"
                         f"{r.stderr[-2000:]}")


def year_files(year, var):
    return sorted(glob.glob(os.path.join(
        HADUK, var, f"{var}_hadukgrid_uk_1km_day_{year}*.nc")))


def drop_year(year):
    for var in VARS:
        for f in year_files(year, var):
            os.remove(f)


def build_weights(sample):
    """cell -> district index, by point-in-polygon on cell centres."""
    if os.path.exists(WCACHE):
        z = np.load(WCACHE)
        print(f"  weights from cache: {len(z['iy']):,} land cells", flush=True)
        return z["iy"], z["ix"], z["dist"], z["names"]

    import geopandas as gpd
    import xarray as xr
    from shapely.geometry import MultiPoint

    with xr.open_dataset(sample) as ds:
        var = next(v for v in ds.data_vars if v in VARS)
        land = np.isfinite(ds[var].isel(time=0).values)
        x = ds["projection_x_coordinate"].values
        y = ds["projection_y_coordinate"].values
    iy, ix = np.nonzero(land)
    cx, cy = x[ix], y[iy]

    gdf = gpd.read_file(DISTRICTS).to_crs(27700)
    pts = gpd.GeoDataFrame(
        {"cell": np.arange(len(iy))},
        geometry=gpd.points_from_xy(cx, cy), crs=27700)
    join = gpd.sjoin(pts, gdf[["geometry"]].reset_index(names="dist"),
                     how="left", predicate="within")
    join = join.drop_duplicates("cell").sort_values("cell")
    dist = join["dist"].to_numpy()

    # cells in no district (sea-adjacent, or outside the polygon set) are
    # dropped; districts with no cell take their nearest one
    keep = np.isfinite(dist)
    iy, ix, cx, cy = iy[keep], ix[keep], cx[keep], cy[keep]
    dist = dist[keep].astype(np.int32)
    have = np.zeros(len(gdf), dtype=bool)
    have[dist] = True
    missing = np.nonzero(~have)[0]
    if len(missing):
        c = gdf.geometry.centroid
        add_iy, add_ix, add_d = [], [], []
        for d in missing:
            k = int(np.argmin((cx - c.x.iloc[d]) ** 2 + (cy - c.y.iloc[d]) ** 2))
            add_iy.append(iy[k]); add_ix.append(ix[k]); add_d.append(d)
        iy = np.concatenate([iy, add_iy])
        ix = np.concatenate([ix, add_ix])
        dist = np.concatenate([dist, np.array(add_d, dtype=np.int32)])
    print(f"  {len(gdf)} districts, {keep.sum():,} land cells in a district; "
          f"{len(missing)} districts fell back to nearest cell", flush=True)

    names = gdf["name"].to_numpy().astype(str)
    np.savez_compressed(WCACHE, iy=iy, ix=ix, dist=dist, names=names)
    return iy, ix, dist, names


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="y0", type=int, default=1960)
    ap.add_argument("--to", dest="y1", type=int, default=2025)
    ap.add_argument("--keep", action="store_true",
                    help="do not delete each year's grids after extraction")
    ap.add_argument("--hours", type=float, default=None,
                    help="stop cleanly after roughly this many hours; the "
                         "checkpoint means the next run resumes exactly")
    ap.add_argument("--recent-first", action="store_true",
                    help="process newest years first, so an interrupted run "
                         "leaves the most useful years done")
    ap.add_argument("--polygons", default=None,
                    help="alternative polygon set (e.g. "
                         "data/sectors_risk.geojson for the 10,398 postcode "
                         "sectors); needs a 'name' property per feature")
    ap.add_argument("--tag", default="",
                    help="suffix for the output CSV, checkpoint and weights "
                         "cache (e.g. _sectors), so runs over different "
                         "polygon sets cannot share state")
    ap.add_argument("--pet-sensitivity", action="store_true",
                    help="also run the drought integrals at PET x 0.85 and "
                         "x 0.70, emitting *_k85/*_k70 columns. Hargreaves "
                         "runs ~a third high in a maritime climate and the "
                         "bias does NOT cancel out of max(PET - rain, 0); "
                         "this measures whether it moves the MAP or only "
                         "the level. Same flag as haduk_district_daily.py.")
    args = ap.parse_args()

    global DISTRICTS, OUT, CKPT, WCACHE
    if args.polygons:
        DISTRICTS = os.path.join(ROOT, args.polygons) \
            if not os.path.isabs(args.polygons) else args.polygons
    if args.tag:
        OUT = OUT.replace(".csv", f"{args.tag}.csv")
        CKPT = CKPT.replace(".npz", f"{args.tag}.npz")
        WCACHE = WCACHE.replace(".npz", f"{args.tag}.npz")

    import xarray as xr

    # a sample file is needed before the weights can be built
    sample = None
    for y in range(args.y0, args.y1 + 1):
        fs = year_files(y, "tasmin")
        if fs:
            sample = fs[0]
            break
    if sample is None:
        print(f"fetching {args.y0} to establish the grid...", flush=True)
        fetch_year(args.y0)
        sample = year_files(args.y0, "tasmin")[0]
    iy, ix, dist, names = build_weights(sample)
    n_d = len(names)
    counts = np.bincount(dist, minlength=n_d).astype(float)

    # latitude per district, for Hargreaves Ra
    import geopandas as gpd
    gdf = gpd.read_file(DISTRICTS).to_crs(27700)
    lat = gdf.geometry.centroid.to_crs(4326).y.to_numpy()

    smd = np.zeros(n_d); cwd = np.zeros(n_d)
    run_len = np.zeros(n_d, dtype=int); run_sev = np.zeros(n_d)
    # PET-sensitivity state: only the capped bucket carries across years,
    # so only smd_s lives in the checkpoint. cwd_yr resets each 1 January
    # by definition, and cwd_run is not worth scaling - the robustness
    # question is about cwd_yr and smd_jja, the two indices the pricing
    # experiment actually uses.
    scales = (0.85, 0.70) if args.pet_sensitivity else ()
    tag = {k: f"_k{int(round(k * 100))}" for k in scales}
    smd_s = {k: np.zeros(n_d) for k in scales}
    # Rows are APPENDED to the CSV as each year finishes and are NOT held
    # in memory or in the checkpoint. Carrying them meant 2,736 dicts per
    # year accumulating to ~180,000, re-pickled into the checkpoint on
    # EVERY year - memory and checkpoint-write cost both growing linearly
    # in a run already measured in hours. State is 4 arrays of 2,736
    # floats; that is all a resume actually needs.
    done = set()
    if os.path.exists(CKPT):
        z = np.load(CKPT, allow_pickle=True)
        smd, cwd = z["smd"], z["cwd"]
        run_len, run_sev = z["run_len"], z["run_sev"]
        for k in scales:
            key = "smd" + tag[k]
            if key not in z:
                raise SystemExit(
                    "checkpoint predates --pet-sensitivity; delete "
                    f"{CKPT} and restart rather than resuming with "
                    "buckets that silently start cold mid-run")
            smd_s[k] = z[key]
        done = set(z["done"].tolist())
        print(f"resuming: {len(done)} years already done, "
              f"appending to the existing CSV", flush=True)

    t0 = time.time()
    years = list(range(args.y0, args.y1 + 1))
    if args.recent_first:
        # Running newest-first means the SMD bucket, the uncapped deficit
        # and any freeze spell would carry BACKWARDS across a year
        # boundary, which is meaningless. So in this mode every year
        # starts clean and years become independent. The cost is exact
        # and small: cwd_run_max (multi-year drought memory) cannot be
        # formed at all and is emitted blank, and a freeze spell running
        # across 31 December is split in two. cwd_yr_max, the index this
        # is actually for, is reset each 1 January anyway and is
        # IDENTICAL either way.
        years.reverse()
        print("  --recent-first: years processed independently; "
              "cwd_run_max_mm left blank, New Year freeze spells split",
              flush=True)
    for yr in years:
        if yr in done:
            continue
        if args.hours and (time.time() - t0) / 3600 >= args.hours:
            print(f"\n--hours {args.hours} reached: stopping cleanly after "
                  f"{len(done)} years. Rerun the same command to resume.",
                  flush=True)
            break
        if not year_files(yr, "rainfall"):
            fetch_year(yr)
        if args.recent_first:
            smd[:] = 0.0; cwd[:] = 0.0
            run_len[:] = 0; run_sev[:] = 0.0
            for k in scales:
                smd_s[k][:] = 0.0
        # WITHIN-YEAR deficit, reset every 1 January. The running cwd
        # below is floored at zero but not capped, so in a district that
        # never fully rewets it carries over - which makes its value
        # depend on which year the run STARTED. Caught by cross-checking
        # 1 km against 5 km for 1976: identical everywhere (corr 0.994+)
        # except cwd, 549 vs 415 mm, because one run had 1975 in front of
        # it and the other did not. cwd_yr is the comparable one; cwd_run
        # is kept because consecutive dry summers are exactly what made
        # 1976 severe, and that memory is real - it is just not a
        # per-year quantity.
        cwd_yr = np.zeros(n_d)
        cwd_yr_s = {k: np.zeros(n_d) for k in scales}
        acc = dict(rain=np.zeros(n_d), tmax=np.zeros(n_d), tmin=np.zeros(n_d),
                   pet=np.zeros(n_d), smd_max=np.zeros(n_d),
                   cwd_max=np.zeros(n_d), cwd_yr_max=np.zeros(n_d),
                   smd_jja=np.zeros(n_d),
                   frost=np.zeros(n_d), spells=np.zeros(n_d),
                   spell_days=np.zeros(n_d), worst=np.zeros(n_d))
        for k in scales:
            acc["smd_max" + tag[k]] = np.zeros(n_d)
            acc["cwd_yr_max" + tag[k]] = np.zeros(n_d)
            acc["smd_jja" + tag[k]] = np.zeros(n_d)
        days = jja_days = 0
        for mo in range(1, 13):
            paths = {}
            for v in VARS:
                p = [f for f in year_files(yr, v)
                     if os.path.basename(f).split("_day_")[1][4:6] == f"{mo:02d}"]
                if not p:
                    break
                paths[v] = p[0]
            if len(paths) != 3:
                raise SystemExit(f"{yr}-{mo:02d}: missing a variable")
            grids, doy = {}, None
            for v, p in paths.items():
                with xr.open_dataset(p) as ds:
                    grids[v] = ds[v].values[:, iy, ix].astype(np.float32)
                    if doy is None:
                        doy = ds["time"].dt.dayofyear.values.astype(float)
            # cell -> district: plain mean of the cells inside each district
            def agg(a):
                o = np.zeros((a.shape[0], n_d))
                for d in range(a.shape[0]):
                    o[d] = np.bincount(dist, weights=np.nan_to_num(a[d]),
                                       minlength=n_d) / counts
                return o
            tn, tx, rn = agg(grids["tasmin"]), agg(grids["tasmax"]), \
                agg(grids["rainfall"])
            del grids
            nd = tn.shape[0]
            ra = hargreaves_ra(lat, doy).T
            pet = 0.0023 * ra * (0.5 * (tn + tx) + 17.8) * np.sqrt(
                np.clip(tx - tn, 0, None))
            acc["rain"] += rn.sum(0); acc["tmax"] += tx.sum(0)
            acc["tmin"] += tn.sum(0); acc["pet"] += pet.sum(0)
            days += nd
            for d in range(nd):
                smd = np.clip(smd + pet[d] - rn[d], 0.0, SMD_CAP)
                cwd = np.maximum(cwd + pet[d] - rn[d], 0.0)
                cwd_yr = np.maximum(cwd_yr + pet[d] - rn[d], 0.0)
                acc["smd_max"] = np.maximum(acc["smd_max"], smd)
                acc["cwd_max"] = np.maximum(acc["cwd_max"], cwd)
                acc["cwd_yr_max"] = np.maximum(acc["cwd_yr_max"], cwd_yr)
                if mo in (6, 7, 8):
                    acc["smd_jja"] += smd
                for k in scales:
                    pk = k * pet[d]
                    smd_s[k] = np.clip(smd_s[k] + pk - rn[d], 0.0, SMD_CAP)
                    cwd_yr_s[k] = np.maximum(cwd_yr_s[k] + pk - rn[d], 0.0)
                    acc["smd_max" + tag[k]] = np.maximum(
                        acc["smd_max" + tag[k]], smd_s[k])
                    acc["cwd_yr_max" + tag[k]] = np.maximum(
                        acc["cwd_yr_max" + tag[k]], cwd_yr_s[k])
                    if mo in (6, 7, 8):
                        acc["smd_jja" + tag[k]] += smd_s[k]
                frost = tn[d] < 0.0
                acc["frost"] += frost
                run_len = np.where(frost, run_len + 1, 0)
                run_sev = np.where(frost, run_sev - np.minimum(tn[d], 0.0), 0.0)
                acc["spells"] += run_len == SPELL_MIN_DAYS
                deep = run_len >= SPELL_MIN_DAYS
                acc["spell_days"] += deep
                acc["worst"] = np.maximum(acc["worst"],
                                          np.where(deep, run_sev, 0.0))
            if mo in (6, 7, 8):
                jja_days += nd
        year_rows = []
        for i, code in enumerate(names):
            extra = {}
            for k in scales:
                extra["smd_max_mm" + tag[k]] = round(
                    float(acc["smd_max" + tag[k]][i]), 1)
                extra["cwd_yr_max_mm" + tag[k]] = round(
                    float(acc["cwd_yr_max" + tag[k]][i]), 1)
                extra["smd_jja_mean_mm" + tag[k]] = round(
                    float(acc["smd_jja" + tag[k]][i]) / max(jja_days, 1), 1)
            year_rows.append({
                "district": str(code), "year": yr,
                "rain_mm": round(float(acc["rain"][i]), 1),
                "tmax_mean_c": round(float(acc["tmax"][i]) / days, 2),
                "tmin_mean_c": round(float(acc["tmin"][i]) / days, 2),
                "pet_mm": round(float(acc["pet"][i]), 1),
                "smd_max_mm": round(float(acc["smd_max"][i]), 1),
                "cwd_yr_max_mm": round(float(acc["cwd_yr_max"][i]), 1),
                "cwd_run_max_mm": ("" if args.recent_first
                                   else round(float(acc["cwd_max"][i]), 1)),
                "smd_jja_mean_mm": round(
                    float(acc["smd_jja"][i]) / max(jja_days, 1), 1),
                "frost_days": int(acc["frost"][i]),
                "freeze_spells": int(acc["spells"][i]),
                "freeze_spell_days": int(acc["spell_days"][i]),
                "worst_spell_degc_days": round(float(acc["worst"][i]), 1),
                **extra,
            })
        append_csv(year_rows)
        if not args.keep:
            drop_year(yr)
        done.add(yr)
        np.savez_compressed(CKPT, smd=smd, cwd=cwd, run_len=run_len,
                            run_sev=run_sev, done=np.array(sorted(done)),
                            **{"smd" + tag[k]: smd_s[k] for k in scales})
        el = (time.time() - t0) / 60
        left = len(range(args.y0, args.y1 + 1)) - len(done)
        print(f"  {yr} done ({len(done)} of "
              f"{args.y1 - args.y0 + 1}), {el:.0f} min elapsed, "
              f"~{el / max(len(done), 1) * left:.0f} min left, "
              f"disk free {shutil.disk_usage(ROOT)[2] / 1e9:.0f} GB",
              flush=True)
    print(f"{OUT}: {len(done)} years done, "
          f"{(time.time() - t0) / 60:.0f} min this session", flush=True)


def append_csv(rows):
    """Append one year. The header is written only when the file is new,
    so a resumed session continues the same CSV instead of truncating it.
    """
    import csv
    if not rows:
        return
    new = not os.path.exists(OUT)
    with open(OUT, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)


def hargreaves_ra(lat_deg, doy):
    """Extraterrestrial radiation, mm/day equivalent. FAO-56 eq. 21."""
    phi = np.radians(lat_deg)[:, None]
    j = np.asarray(doy)[None, :]
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365.0)
    dec = 0.409 * np.sin(2 * np.pi * j / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1.0, 1.0))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(dec)
        + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return ra * 0.408


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
