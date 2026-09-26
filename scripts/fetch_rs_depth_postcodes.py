"""River/sea DEPTH bands as the share of unit POSTCODES (England).

Surface water has carried a depth-conditioned severity since 2026-08
(fetch_sw_depth_postcodes.py, scores_real.sw_depth_severity); rivers
and sea have been priced at one flat ABI claim size everywhere. The EA
publishes the river/sea risk product the model reads since 2026-09-25
(rofrs_4band, DATA_SOURCES #44) with five depth layers alongside it:
rofrs_4band_<d>_depth for d = 0.2 / 0.3 / 0.6 / 0.9 / 1.2 m, each the
same four risk bands for flooding DEEPER than d. They share
rofrs_4band's legend exactly (measured 2026-09-26: 81-90% of opaque
pixels are an exact legend colour, the rest the polygon strokes the
band classifier already settles by neighbourhood vote), and they nest:
a deeper threshold reads riskier than a shallower one at 0.1-0.35% of
pixels, which is stroke noise, clipped below.

This script samples them at every live unit-postcode centroid in
England, in the two stages of the surface-water depth fetch:

  --flags [--climate] [--part i/n]
        Fetch the England tiles that hold postcodes, six layers each -
        the band itself (rofrs_4band, b00) and the five depth layers -
        classify each postcode's pixel with fetch_flood_postcodes.
        classify_rofrs, and write data/cache/rs_depth_bands[_p<i>][_cc].csv
        (postcode, b00, b02 ... b12 band codes). A dropped tile makes the
        file .partial, never model input.

  (no --flags) [--climate]
        Read the band files, turn them into flags on the same bands as
        f_high / f_low (High+Medium, and High+Medium+Low), enforce
        nesting and clip each postcode to its OWN band (b00), aggregate to the checkout's grain with the hierarchical
        shrinkage of fetch_flood_postcodes.py, and write
        data/rs_depth[_cc].csv (name, e_high, e_low, d02_high, d02_low,
        ... d12_low, basis = "postcode"), zero-filled outside England.

THE ENVELOPE IS READ IN THE SAME PASS. b00 is rofrs_4band on the same
tiles, the same pixel indices and the same classifier settings as
fetch_flood_postcodes.rofrs_england, so it reproduces that fetch's
per-postcode bands unless the EA has republished in between - and the
aggregation reports the agreement whenever data/cache/rofrs_bands[_cc]
.csv is present to compare against. Reading it here rather than from
that file keeps the band files self-contained: rofrs_bands is a
gitignored intermediate of a different fetch, and a depth aggregation
that needs it has to run in that fetch's job or not at all. With b00
the band files are the whole input, and the SAME files aggregate at
either grain.

DEPTH IS NOT PUBLISHED EVERYWHERE THE BAND IS. The present-day depth
layers paint "Unavailable" (the legend's grey) over areas where
rofrs_4band itself gives a band: 9.8% of the 26 km tile at the fen
edge north of Cambridge, identically in all five layers (2026-09-26).
Read as "none" those postcodes would price as shallow, which in the
fens is the wrong way round. So the depth distribution is taken over
the postcodes where depth IS published: e_high / e_low are the
envelope counted over those postcodes only, the d* bands are counted
over the same set, and scores_real.rs_depth_severity conditions on
the file's own e_* rather than on the caller's f_high / f_low. A unit
with no published depth in its own envelope takes its parent's depth
distribution through the shrinkage prior (PE11, PE13 and PE14 - the
Fens - get the PE area's, 2026-09-26), and flat severity only if the
parent has none either.

The deep layers' small polygons are mostly stroke, so the classifier
searches wider neighbourhoods here (DEPTH_WINDOWS): at the default
(5, 11, 21) px the 1.2 m layer over York left 11 of 200,000 sampled
pixels with no readable pixel within 10 px, and the classifier stops
rather than guess.

--climate reads the rofrs_cc01 edition. Where the climate band is
"Unavailable" the present-day depth band is carried, exactly as
fetch_flood_postcodes.rofrs_england does for the band itself.

England only: NRW and SEPA publish no river/sea depth product in this
form, so Welsh and Scottish units keep the flat severity.
"""
import glob
import os
import re
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_flood_postcodes as fp                # noqa: E402
import fetch_flood as ff                          # noqa: E402
from build_model import load_districts           # noqa: E402

DATA = "data"
CACHE = os.path.join(DATA, "cache")
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
K_PRIOR = fp.K_PRIOR
AREA_RE = re.compile(r"[A-Z]+")
PRESENT = fp.EA_RS_PRESENT
CLIMATE_SVC = PRESENT.replace("rivers-and-sea/wms", "rivers-and-sea-climate-change/wms")
DEPTHS = [("0_2", "d02"), ("0_3", "d03"), ("0_6", "d06"), ("0_9", "d09"), ("1_2", "d12")]
KEYS = [k for _, k in DEPTHS]
BANDS = [f"b{k[1:]}" for k in KEYS]                # b02 ... b12
ENV = "b00"                                        # rofrs_4band itself
DCOLS = [f"{k}_{b}" for k in KEYS for b in ("high", "low")]
COLS = ["e_high", "e_low"] + DCOLS
DEPTH_WINDOWS = (5, 11, 21, 41, 81)
HIGH, LOW = (3, 4), (2, 3, 4)                      # as f_high / f_low


def layer(stem, climate):
    return f"rofrs_cc01_4band_{stem}m_depth" if climate else f"rofrs_4band_{stem}m_depth"


def area_of(name):
    return AREA_RE.match(name).group(0)


def bands_path(part, climate):
    tag = f"_p{part[0]}" if part else ""
    return os.path.join(CACHE, f"rs_depth_bands{tag}{'_cc' if climate else ''}.csv")


def stage_flags(climate, part):
    pc = pd.read_csv(CENTROIDS)
    pc = pc[pc["country"] == "England"].reset_index(drop=True)
    x = pc["easting"].values.astype(float)
    y = pc["northing"].values.astype(float)
    minx, miny, maxx, maxy = fp.ENGLAND_BBOX
    T = fp.RS_PX * fp.RS_TILE
    nx = int(np.ceil((maxx - minx) / T))
    ny = int(np.ceil((maxy - miny) / T))
    ix_all = np.clip(((x - minx) // T).astype(int), 0, nx - 1)
    iy_all = np.clip(((y - miny) // T).astype(int), 0, ny - 1)
    tiles = sorted(set(zip(ix_all.tolist(), iy_all.tolist())))
    if part:
        i, n = part
        tiles = [t for k, t in enumerate(tiles) if k % n == i]
    svc = CLIMATE_SVC if climate else PRESENT
    print(f"england: {len(tiles)} tiles of {T / 1000:.1f} km hold postcodes, "
          f"the band + {len(DEPTHS)} {'climate ' if climate else ''}depth "
          "layers each", flush=True)
    code = np.full((len(pc), len(DEPTHS)), -1, dtype=np.int8)
    carried = np.zeros((len(pc), len(DEPTHS)), dtype=bool)
    env = np.full(len(pc), -1, dtype=np.int8)
    env_layer = "rofrs_cc01_4band" if climate else fp.EA_RS_PRESENT_LAYER
    sampled = np.zeros(len(pc), dtype=bool)
    ff.FAILED.clear()
    t0 = time.time()
    for k, (ix, iy) in enumerate(tiles):
        x0, y0 = minx + ix * T, miny + iy * T
        bbox = (x0, y0, x0 + T, y0 + T)
        idx = np.nonzero((ix_all == ix) & (iy_all == iy))[0]
        cols = np.clip(((x[idx] - x0) / fp.RS_PX).astype(int), 0, fp.RS_TILE - 1)
        rows = np.clip(((bbox[3] - y[idx]) / fp.RS_PX).astype(int), 0, fp.RS_TILE - 1)
        # The band, exactly as rofrs_england reads it: default windows,
        # and in the climate edition the present-day band where the
        # climate one is Unavailable.
        a = fp.http_rgba(fp.rofrs_url(svc, env_layer, bbox))
        ok = a is not None
        if ok:
            c, _ = fp.classify_rofrs(a, rows, cols)
            gap = c == 5
            if climate and gap.any():
                p = fp.http_rgba(fp.rofrs_url(PRESENT, fp.EA_RS_PRESENT_LAYER, bbox))
                ok = p is not None
                if ok:
                    c[gap], _ = fp.classify_rofrs(p, rows[gap], cols[gap])
            env[idx] = c
        for j, (stem, _) in enumerate(DEPTHS):
            if not ok:
                break
            a = fp.http_rgba(fp.rofrs_url(svc, layer(stem, climate), bbox))
            if a is None:
                ok = False                     # recorded in ff.FAILED
                break
            c, _ = fp.classify_rofrs(a, rows, cols, DEPTH_WINDOWS)
            gap = c == 5
            if climate and gap.any():
                p = fp.http_rgba(fp.rofrs_url(PRESENT, layer(stem, False), bbox))
                if p is None:
                    ok = False
                    break
                c[gap], _ = fp.classify_rofrs(p, rows[gap], cols[gap], DEPTH_WINDOWS)
                carried[idx[gap], j] = True
            code[idx, j] = c
            time.sleep(0.1)
        if ok:
            sampled[idx] = True
        if (k + 1) % 10 == 0 or k + 1 == len(tiles):
            print(f"  {k + 1}/{len(tiles)} tiles, {(time.time() - t0) / 60:.1f} min",
                  flush=True)
    # Unavailable (5) is kept as its own code: the aggregation leaves
    # those postcodes out of the depth distribution (see the docstring).
    out = bands_path(part, climate)
    if ff.FAILED:
        out += ".partial"
        print(f"  !! {len(ff.FAILED)} request(s) failed - writing {out}, "
              "NOT model input", flush=True)
    os.makedirs(CACHE, exist_ok=True)
    df = pd.DataFrame(code[sampled], columns=BANDS)
    df.insert(0, ENV, env[sampled])
    df.insert(0, "postcode", pc["postcode"].values[sampled])
    df.to_csv(out, index=False)
    s = code[sampled]
    print(f"wrote {out}: {int(sampled.sum()):,} of {len(pc):,} postcodes; >=1% band "
          + ", ".join(f"{k} {np.isin(s[:, j], HIGH).mean():.3%}" for j, k in enumerate(KEYS)),
          flush=True)
    print(f"  depth Unavailable in some layer: {(s == 5).any(1).mean():.2%} of "
          f"postcodes; in every layer: {(s == 5).all(1).mean():.2%}", flush=True)
    if climate:
        print(f"  climate band unavailable, present-day carried: "
              f"{carried[sampled].any(1).mean():.2%} of postcodes", flush=True)


def stage_aggregate(climate):
    pc = pd.read_csv(CENTROIDS)
    pc = pc[pc["country"] == "England"].reset_index(drop=True)
    pc["area"] = pc["district"].map(area_of)
    suffix = "_cc" if climate else ""
    files = [f for f in glob.glob(os.path.join(CACHE, f"rs_depth_bands*{suffix}.csv"))
             if f.endswith("_cc.csv") == climate]
    if not files:
        raise SystemExit("no band files - run --flags first")
    bands = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if bands["postcode"].duplicated().any():
        raise SystemExit("a postcode appears in two band files - parts overlap")
    pc = pc.merge(bands, on="postcode", how="left")
    if pc[BANDS[0]].isna().any():
        raise SystemExit(f"{int(pc[BANDS[0]].isna().sum()):,} England postcodes have "
                         "no depth bands - a part is missing")
    for b, k in zip(BANDS, KEYS):
        pc[f"{k}_high"] = pc[b].isin(HIGH)
        pc[f"{k}_low"] = pc[b].isin(LOW)
    # The envelope is each postcode's own band, read in the same pass
    # (b00). Where the frequency fetch's own record is present, say how
    # far the two agree: they are the same layer on the same pixels, so
    # anything short of ~100% means the EA republished in between.
    pc["env_band"] = pc[ENV]
    if (pc["env_band"] < 0).any() or (pc["env_band"] == 5).any():
        raise SystemExit("the band envelope is unreadable or Unavailable at "
                         f"{int(((pc['env_band'] < 0) | (pc['env_band'] == 5)).sum()):,} "
                         "English postcodes")
    ref_path = os.path.join(CACHE, f"rofrs_bands{suffix}.csv")
    if os.path.exists(ref_path):
        ref = pd.read_csv(ref_path).set_index("postcode")["band"]
        r = ref.reindex(pc["postcode"]).values
        both = ~np.isnan(r)
        agree = (r[both] == pc["env_band"].values[both]).mean()
        hi = (np.isin(r[both], HIGH) == pc["env_band"].isin(HIGH).values[both]).mean()
        print(f"b00 vs {ref_path}: same band at {agree:.3%} of {int(both.sum()):,} "
              f"postcodes, same >=1% flag at {hi:.3%}", flush=True)
    avail = ~(pc[BANDS] == 5).any(axis=1)
    in_high = pc["env_band"].isin(HIGH) & avail
    in_low = pc["env_band"].isin(LOW) & avail
    print(f"depth published for {avail.mean():.2%} of English postcodes; of those "
          f"in the >=1% band, {avail[pc['env_band'].isin(HIGH)].mean():.2%}", flush=True)
    pc["e_high"], pc["e_low"] = in_high, in_low
    before = {c: int(pc[c].sum()) for c in DCOLS}
    for deep, shallow in zip(reversed(KEYS), reversed(KEYS[:-1])):
        for b in ("high", "low"):
            pc[f"{shallow}_{b}"] |= pc[f"{deep}_{b}"]
    for k in KEYS:
        pc[f"{k}_high"] &= in_high
        pc[f"{k}_low"] &= in_low
    moved = sum(int(pc[c].sum()) - before[c] for c in DCOLS)
    print(f"nesting/envelope enforced: net {moved:+,} flags across the "
          f"{len(DCOLS)} bands", flush=True)
    print(f"{len(files)} band files, {len(pc):,} postcodes; "
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
    country = pd.read_csv(os.path.join(DATA, "country.csv")).set_index("name")["country"]
    rows, thin, outside = [], 0, 0
    for n in names:
        p = n.split(" ")[0] if grain == "sector" else area_of(n)
        unit_country = country.get(n, country.get(n.split(" ")[0], ""))
        if unit_country != "England" or p not in prior.index:
            outside += 1
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
        # e_* and d* are shrunk with the same weights toward priors built
        # from the same postcodes, so d <= e survives the shrinkage.
        rows.append([n] + vals.tolist())
    out = pd.DataFrame(rows, columns=["name"] + COLS)
    out["basis"] = "postcode"
    path = os.path.join(DATA, f"rs_depth{suffix}.csv")
    out.to_csv(path, index=False, float_format="%.6f")
    print(f"wrote {path}: {len(out)} {grain}s ({thin} with fewer than {K_PRIOR} "
          f"postcodes, shrunk toward their parent; {outside} outside England, "
          f"zero-filled)", flush=True)


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
