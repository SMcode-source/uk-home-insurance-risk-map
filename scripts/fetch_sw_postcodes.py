"""Surface-water flood fractions as the share of unit POSTCODES in the extent.

fetch_surface_water.py measures the share of a unit's AREA inside the
national surface-water extents. The river/sea fractions moved to the
share of live unit postcodes on 2026-09-06 (fetch_flood_postcodes.py,
DATA_SOURCES #41) because area share puts valley towns at the wrong
end of the ranking; surface water had the healthier validation (+0.57
against NRW's people at risk) but the same denominator problem.

This script samples the SAME masks fetch_surface_water.py rasterises -
the EA rofsw category colours at 13 m/px, NRW FRAW surface water at
20 m/px, SEPA's likelihood MapServers at 20 m/px - at every live
small-user unit-postcode centroid (ONSPD, data/postcode_centroids.csv).
It runs in two stages so the slow part can be split across machines:

  --flags REGION [--climate] [--part i/n]
        Fetch the tiles of one region that hold postcodes and write the
        per-postcode flags to data/sw_flags_<region>[_p<i>][_cc].csv
        (postcode, in_high, in_low). A dropped tile makes the file
        .partial, never model input. --part i/n takes every n-th tile.

  (no --flags) [--climate]
        Read every flag file, require full coverage of the postcodes of
        the regions in play, aggregate to the grain load_districts()
        returns on this checkout (sector names contain a space) with
        the hierarchical beta-binomial shrinkage of
        fetch_flood_postcodes.py (K_PRIOR postcodes toward the parent),
        and write data/sw_fractions.csv (or sw_fractions_cc.csv).

The depth product (data/sw_depth.csv, fetch_sw_depth.py) stays an AREA
measurement: it gives the depth distribution CONDITIONAL on being
inside the envelope, and that conditional must be taken against the
envelope measured the same way. So the first aggregation keeps the
previous area-share file as data/sw_fractions_area.csv (and _cc), and
scores_real.sw_depth_severity reads its envelope from there. Frequency
comes from where the homes are; depth, given a home is in the water,
from the water.

--climate is England only (the EA rofsw_cc01 edition; NRW and SEPA
publish no equivalent), with England-only priors, exactly as
fetch_flood_postcodes.py --climate.
"""
import glob
import os
import re
import shutil
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_surface_water as sw                 # noqa: E402
from build_model import load_districts           # noqa: E402

DATA = "data"
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
K_PRIOR = 20        # postcodes of prior weight; see fetch_flood_postcodes.py
AREA_RE = re.compile(r"[A-Z]+")
COUNTRY = {"england": "England", "wales": "Wales", "scotland": "Scotland"}


def area_of(district):
    """Postcode area of a district or sector name: its leading letters."""
    return AREA_RE.match(district).group(0)


def flags_path(region, part, climate):
    tag = f"_p{part[0]}" if part else ""
    return os.path.join(DATA, f"sw_flags_{region}{tag}{'_cc' if climate else ''}.csv")


def sample_region(region_name, pc, part):
    """Boolean in_high / in_low for the postcodes of one region."""
    region = sw.REGIONS[region_name]
    px, tile = region["px"], region["tile"]
    minx, miny, maxx, maxy = region["bbox"]
    T = px * tile
    nx = int(np.ceil((maxx - minx) / T))
    ny = int(np.ceil((maxy - miny) / T))
    x = pc["easting"].values.astype(float)
    y = pc["northing"].values.astype(float)
    in_high = np.zeros(len(pc), dtype=bool)
    in_low = np.zeros(len(pc), dtype=bool)
    sampled = np.zeros(len(pc), dtype=bool)
    ix_all = np.clip(((x - minx) // T).astype(int), 0, nx - 1)
    iy_all = np.clip(((y - miny) // T).astype(int), 0, ny - 1)
    tiles = sorted(set(zip(ix_all.tolist(), iy_all.tolist())))
    if part:
        i, n = part
        tiles = [t for k, t in enumerate(tiles) if k % n == i]
    print(f"{region_name}: {len(tiles)} tiles of {T / 1000:.1f} km hold "
          f"postcodes (grid {nx}x{ny}, {px} m/px)", flush=True)
    t0 = time.time()
    for k, (ix, iy) in enumerate(tiles):
        x0, y0 = minx + ix * T, miny + iy * T
        bbox = (x0, y0, x0 + T, y0 + T)
        idx = np.nonzero((ix_all == ix) & (iy_all == iy))[0]
        masks = sw.masks_for_tile(region, bbox)
        if masks is None:
            continue                       # recorded in sw.FAILED
        sampled[idx] = True
        if masks:
            cols = np.clip(((x[idx] - x0) / px).astype(int), 0, tile - 1)
            rows = np.clip(((bbox[3] - y[idx]) / px).astype(int), 0, tile - 1)
            if "high" in masks:
                in_high[idx] |= masks["high"][rows, cols]
            if "low" in masks:
                in_low[idx] |= masks["low"][rows, cols]
        print(f"  tile {ix},{iy} ({k + 1}/{len(tiles)}): {len(idx):,} postcodes, "
              f"{(time.time() - t0) / 60:.1f} min", flush=True)
        time.sleep(0.1)
    return in_high, in_low | in_high, sampled


def stage_flags(regions, climate, part):
    pc = pd.read_csv(CENTROIDS)
    for region_name in regions:
        p = pc[pc["country"] == COUNTRY[region_name]].reset_index(drop=True)
        sw.FAILED.clear()
        in_high, in_low, sampled = sample_region(region_name, p, part)
        out = flags_path(region_name, part, climate)
        if sw.FAILED:
            out += ".partial"
            print(f"  !! {len(sw.FAILED)} tile(s) failed - writing {out}, "
                  "NOT model input", flush=True)
        # only the postcodes whose tile was fetched: parts must not overlap
        # and an unfetched postcode must be absent, not a silent zero
        pd.DataFrame({"postcode": p["postcode"][sampled],
                      "in_high": in_high[sampled].astype(int),
                      "in_low": in_low[sampled].astype(int)}).to_csv(out, index=False)
        print(f"wrote {out}: {int(sampled.sum()):,} of {len(p):,} postcodes, in high "
              f"{in_high[sampled].mean():.3%}, low {in_low[sampled].mean():.3%}",
              flush=True)


def stage_aggregate(climate):
    pc = pd.read_csv(CENTROIDS)
    countries = ["England"] if climate else ["England", "Wales", "Scotland"]
    pc = pc[pc["country"].isin(countries)].reset_index(drop=True)
    pc["area"] = pc["district"].map(area_of)
    suffix = "_cc" if climate else ""
    files = [f for f in glob.glob(os.path.join(DATA, f"sw_flags_*{suffix}.csv"))
             if (f.endswith("_cc.csv")) == climate]
    if not files:
        raise SystemExit("no flag files - run --flags first")
    flags = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if flags["postcode"].duplicated().any():
        raise SystemExit("a postcode appears in two flag files - parts overlap")
    pc = pc.merge(flags, on="postcode", how="left")
    missing = pc["in_high"].isna()
    if missing.any():
        by = pc[missing].groupby("country").size().to_dict()
        raise SystemExit(f"{int(missing.sum()):,} postcodes have no flags "
                         f"({by}) - a region or part is missing")
    pc["in_high"] = pc["in_high"].astype(bool)
    pc["in_low"] = pc["in_low"].astype(bool) | pc["in_high"]
    print(f"{len(files)} flag files, {len(pc):,} postcodes; in high "
          f"{pc['in_high'].mean():.3%}, low {pc['in_low'].mean():.3%}", flush=True)

    names = load_districts()["name"].tolist()
    grain = "sector" if any(" " in n for n in names) else "district"
    own = pc.groupby(grain).agg(n=("in_high", "size"), h=("in_high", "sum"),
                                l=("in_low", "sum"))
    area = pc.groupby("area").agg(f_high=("in_high", "mean"),
                                  f_low=("in_low", "mean"))
    if grain == "district":
        prior = area
    else:
        dist = pc.groupby("district").agg(n=("in_high", "size"),
                                          h=("in_high", "sum"),
                                          l=("in_low", "sum"))
        pa = area.reindex(dist.index.map(area_of)).set_index(dist.index)
        prior = pd.DataFrame({
            "f_high": (dist["h"] + K_PRIOR * pa["f_high"]) / (dist["n"] + K_PRIOR),
            "f_low": (dist["l"] + K_PRIOR * pa["f_low"]) / (dist["n"] + K_PRIOR)})
    rows, thin, missing = [], 0, 0
    for n in names:
        p = n.split(" ")[0] if grain == "sector" else area_of(n)
        if p not in prior.index:
            missing += 1
            continue
        ph, pl = prior.loc[p, "f_high"], prior.loc[p, "f_low"]
        if n in own.index:
            cnt, h, l = own.loc[n, ["n", "h", "l"]]
            if cnt < K_PRIOR:
                thin += 1
            fh = (h + K_PRIOR * ph) / (cnt + K_PRIOR)
            fl = (l + K_PRIOR * pl) / (cnt + K_PRIOR)
        else:
            thin += 1
            fh, fl = ph, pl
        rows.append((n, fh, fl))

    out = os.path.join(DATA, f"sw_fractions{suffix}.csv")
    keep = os.path.join(DATA, f"sw_fractions_area{suffix}.csv")
    if os.path.exists(out) and not os.path.exists(keep):
        # the area-share file the depth conditional needs; see docstring
        shutil.copy(out, keep)
        print(f"kept the area-share file as {keep}", flush=True)
    pd.DataFrame(rows, columns=["name", "sw_high", "sw_low"]).to_csv(
        out, index=False, float_format="%.6f")
    print(f"wrote {out}: {len(rows)} {grain}s ({thin} with fewer than {K_PRIOR} "
          f"postcodes, shrunk toward their parent; {missing} left to the "
          f"median fallback)", flush=True)


def main():
    args = sys.argv[1:]
    climate = "--climate" in args
    part = None
    if "--part" in args:
        i, n = args[args.index("--part") + 1].split("/")
        part = (int(i), int(n))
    if climate:
        sw.EA_SW_LAYER = "rofsw_cc01"
        sw.REGIONS["england"]["service"] = sw.EA_SW_CC
    if not os.path.exists(CENTROIDS):
        raise SystemExit(f"{CENTROIDS} missing - run scripts/fetch_onspd.py first")
    if "--flags" in args:
        regions = [a for a in args if a in sw.REGIONS] or (
            ["england"] if climate else list(sw.REGIONS))
        if climate and regions != ["england"]:
            raise SystemExit("--climate is England only")
        stage_flags(regions, climate, part)
    else:
        stage_aggregate(climate)


if __name__ == "__main__":
    main()
