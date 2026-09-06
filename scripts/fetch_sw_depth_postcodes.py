"""Surface-water DEPTH bands as the share of unit POSTCODES (England).

fetch_sw_depth.py measures, for each unit, the share of its AREA where
modelled surface-water depth exceeds 0.2 / 0.3 / 0.6 / 0.9 / 1.2 m, in
the High+Medium band and in the whole envelope. scores_real.
sw_depth_severity turns those into a depth distribution CONDITIONAL on
being inside the envelope, so the envelope it divides by has to be
measured the same way. When the frequency fractions moved to postcode
share on 2026-09-06 (fetch_sw_postcodes.py, DATA_SOURCES #41) the depth
product stayed on area and the severity kept reading the area-share
envelope from sw_fractions_area[_cc].csv: consistent, but two
denominators for one peril, and a depth distribution over the water
rather than over the homes in it (people build on the higher ground of
a floodplain, so the water under the homes is not the water's average).

This script samples the SAME five depth layers fetch_sw_depth.py
rasterises (EA rofsw_<d>_depth WMS at 13 m/px, category colours decoded
per pixel) at every live unit-postcode centroid in England, in the two
stages of fetch_sw_postcodes.py:

  --flags [--climate] [--part i/n]
        Fetch the England tiles that hold postcodes, five layers each,
        and write data/sw_depth_flags_england[_p<i>][_cc].csv
        (postcode, d02_high, d02_low, ..., d12_low). A dropped tile
        makes the file .partial, never model input.

  (no --flags) [--climate]
        Read the flag files, require full coverage of England's
        postcodes, aggregate to the grain load_districts() returns with
        the hierarchical shrinkage of fetch_flood_postcodes.py (K_PRIOR
        postcodes toward the parent; England-only priors), and write
        data/sw_depth.csv (or sw_depth_cc.csv) in the layout
        fetch_sw_depth.py wrote, zero-filled outside England, plus a
        `basis` column = "postcode". sw_depth_severity reads that column
        and, for a postcode-basis table, conditions on the caller's
        postcode-share sw_high / sw_low instead of the area envelope.
        The previous area-share table is kept as
        data/sw_depth_area[_cc].csv the first time.

Nesting (d02 >= d03 >= ... >= d12, and each *_high <= its *_low) holds
per postcode by construction and survives the shrinkage because every
band is shrunk with the same weights toward priors that nest too.

--climate is the EA rofsw_cc01 edition: same layers, cc01 infix, the
climate-change service; England only, as everything about depth is.
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
import fetch_sw_depth as sd                       # noqa: E402
from build_model import load_districts           # noqa: E402

DATA = "data"
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
K_PRIOR = 20
AREA_RE = re.compile(r"[A-Z]+")
KEYS = [k for _, k, _ in sd.DEPTHS]               # d02 d03 d06 d09 d12
COLS = [f"{k}_{b}" for k in KEYS for b in ("high", "low")]


def area_of(name):
    return AREA_RE.match(name).group(0)


def flags_path(part, climate):
    tag = f"_p{part[0]}" if part else ""
    return os.path.join(DATA, f"sw_depth_flags_england{tag}{'_cc' if climate else ''}.csv")


def stage_flags(climate, part):
    pc = pd.read_csv(CENTROIDS)
    pc = pc[pc["country"] == "England"].reset_index(drop=True)
    x = pc["easting"].values.astype(float)
    y = pc["northing"].values.astype(float)
    minx, miny, maxx, maxy = sd.BBOX
    T = sd.PX * sd.TILE
    nx = int(np.ceil((maxx - minx) / T))
    ny = int(np.ceil((maxy - miny) / T))
    ix_all = np.clip(((x - minx) // T).astype(int), 0, nx - 1)
    iy_all = np.clip(((y - miny) // T).astype(int), 0, ny - 1)
    tiles = sorted(set(zip(ix_all.tolist(), iy_all.tolist())))
    if part:
        i, n = part
        tiles = [t for k, t in enumerate(tiles) if k % n == i]
    service = sd.EA_SW_CC if climate else sd.EA_SW
    layers = [sd.layer_name(stem, climate) for stem, _, _ in sd.DEPTHS]
    print(f"england: {len(tiles)} tiles of {T / 1000:.1f} km hold postcodes "
          f"(grid {nx}x{ny}, {sd.PX} m/px), {len(layers)} depth layers each",
          flush=True)
    flags = np.zeros((len(pc), len(COLS)), dtype=bool)
    sampled = np.zeros(len(pc), dtype=bool)
    sd.FAILED.clear()
    t0 = time.time()
    for k, (ix, iy) in enumerate(tiles):
        x0, y0 = minx + ix * T, miny + iy * T
        bbox = (x0, y0, x0 + T, y0 + T)
        idx = np.nonzero((ix_all == ix) & (iy_all == iy))[0]
        cols = np.clip(((x[idx] - x0) / sd.PX).astype(int), 0, sd.TILE - 1)
        rows = np.clip(((bbox[3] - y[idx]) / sd.PX).astype(int), 0, sd.TILE - 1)
        ok = True
        for j, layer in enumerate(layers):
            masks = sd.masks_for_tile(layer, bbox, service)
            if masks is None:
                ok = False                     # recorded in sd.FAILED
                break
            if masks:
                flags[idx, 2 * j] |= masks["high"][rows, cols]
                flags[idx, 2 * j + 1] |= masks["low"][rows, cols]
            time.sleep(0.1)
        if ok:
            sampled[idx] = True
        print(f"  tile {ix},{iy} ({k + 1}/{len(tiles)}): {len(idx):,} postcodes, "
              f"{(time.time() - t0) / 60:.1f} min", flush=True)
    out = flags_path(part, climate)
    if sd.FAILED:
        out += ".partial"
        print(f"  !! {len(sd.FAILED)} request(s) failed - writing {out}, "
              "NOT model input", flush=True)
    df = pd.DataFrame(flags[sampled].astype(int), columns=COLS)
    df.insert(0, "postcode", pc["postcode"].values[sampled])
    df.to_csv(out, index=False)
    print(f"wrote {out}: {int(sampled.sum()):,} of {len(pc):,} postcodes; "
          + ", ".join(f"{c} {flags[sampled, i].mean():.3%}" for i, c in enumerate(COLS)),
          flush=True)


def stage_aggregate(climate):
    pc = pd.read_csv(CENTROIDS)
    pc = pc[pc["country"] == "England"].reset_index(drop=True)
    pc["area"] = pc["district"].map(area_of)
    suffix = "_cc" if climate else ""
    files = [f for f in glob.glob(os.path.join(DATA, f"sw_depth_flags_england*{suffix}.csv"))
             if f.endswith("_cc.csv") == climate]
    if not files:
        raise SystemExit("no flag files - run --flags first")
    flags = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if flags["postcode"].duplicated().any():
        raise SystemExit("a postcode appears in two flag files - parts overlap")
    pc = pc.merge(flags, on="postcode", how="left")
    missing = pc[COLS[0]].isna()
    if missing.any():
        raise SystemExit(f"{int(missing.sum()):,} England postcodes have no depth "
                         "flags - a part is missing")
    for c in COLS:
        pc[c] = pc[c].astype(bool)
    print(f"{len(files)} flag files, {len(pc):,} postcodes; "
          + ", ".join(f"{c} {pc[c].mean():.3%}" for c in COLS), flush=True)

    names = load_districts()["name"].tolist()
    grain = "sector" if any(" " in n for n in names) else "district"
    own = pc.groupby(grain).agg(n=(COLS[0], "size"), **{c: (c, "sum") for c in COLS})
    area = pc.groupby("area")[COLS].mean()
    if grain == "district":
        prior = area
    else:
        dist = pc.groupby("district").agg(n=(COLS[0], "size"),
                                          **{c: (c, "sum") for c in COLS})
        pa = area.reindex(dist.index.map(area_of)).set_index(dist.index)
        prior = pd.DataFrame({c: (dist[c] + K_PRIOR * pa[c]) / (dist["n"] + K_PRIOR)
                              for c in COLS})
    rows, thin, outside = [], 0, 0
    for n in names:
        p = n.split(" ")[0] if grain == "sector" else area_of(n)
        if p not in prior.index:
            outside += 1                     # Wales / Scotland: zero-filled
            rows.append([n] + [0.0] * len(COLS))
            continue
        pr = prior.loc[p, COLS].values.astype(float)
        if n in own.index:
            cnt = own.loc[n, "n"]
            sums = own.loc[n, COLS].values.astype(float)
            if cnt < K_PRIOR:
                thin += 1
            vals = (sums + K_PRIOR * pr) / (cnt + K_PRIOR)
        else:
            thin += 1
            vals = pr
        rows.append([n] + vals.tolist())
    out = pd.DataFrame(rows, columns=["name"] + COLS)
    out["basis"] = "postcode"
    path = os.path.join(DATA, f"sw_depth{suffix}.csv")
    keep = os.path.join(DATA, f"sw_depth_area{suffix}.csv")
    if os.path.exists(path) and not os.path.exists(keep):
        prev = pd.read_csv(path, nrows=1)
        if "basis" not in prev.columns or prev["basis"].iloc[0] != "postcode":
            shutil.copy(path, keep)
            print(f"kept the area-share table as {keep}", flush=True)
    out.to_csv(path, index=False, float_format="%.6f")
    print(f"wrote {path}: {len(out)} {grain}s ({thin} with fewer than {K_PRIOR} "
          f"postcodes, shrunk toward their parent; {outside} outside England, "
          "zero-filled)", flush=True)


def main():
    args = sys.argv[1:]
    climate = "--climate" in args
    part = None
    if "--part" in args:
        i, n = args[args.index("--part") + 1].split("/")
        part = (int(i), int(n))
    if not os.path.exists(CENTROIDS):
        raise SystemExit(f"{CENTROIDS} missing - run scripts/fetch_onspd.py first")
    if "--flags" in args:
        stage_flags(climate, part)
    else:
        stage_aggregate(climate)


if __name__ == "__main__":
    main()
