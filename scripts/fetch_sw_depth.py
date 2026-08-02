"""Fetch EA surface-water DEPTH bands per postcode district (England).

The NaFRA2 "risk of flooding from surface water" WMS carries, alongside the
headline `rofsw` extent, five nested depth layers:

    rofsw_0_2m_depth ... rofsw_1_2m_depth

Each shows the part of the surface-water envelope where modelled depth
exceeds that threshold, painted with the same three likelihood colours as
`rofsw` (High 1in30 / Medium 1in100 / Low 1in1000). Verified empirically:
over a Humber test tile the painted area falls 100% -> 48% -> 29% -> 10% ->
4.9% -> 2.3% and each mask nests inside the previous one to within the
antialiasing error at 13 m/px.

Why this matters: the model previously priced every surface-water claim at
one flat average severity. Depth is the single strongest driver of flood
damage per property, so knowing *how deep* the water gets in a district
lets the severity vary with the hazard instead of being a constant.

Output: data/sw_depth.csv, one row per district, with the fraction of
district area exceeding each depth threshold, split the same way as
sw_fractions.csv:
    d<NN>_high  High+Medium likelihood bands (matches sw_high)
    d<NN>_low   the full envelope            (matches sw_low)
`sw_low` from sw_fractions.csv is the depth>0 denominator - it is the same
layer at the same resolution, so it does not need refetching.

England only: NRW and SEPA publish no equivalent depth product, so Wales
and Scotland keep the flat severity (documented in the README).

The layers carry MaxScaleDenominator 50000, i.e. they do not render above
~14 m/px - hence 13 m/px tiles, exactly as fetch_surface_water.py does.

With --climate the same fetch runs against the EA's climate-change edition
of the identical product (`rofsw_cc01*`, same service family, same 1:50,000
scale cap) and writes data/sw_depth_cc.csv. Comparing that against the
present-day file is a like-for-like delta rather than two differently
derived products, which is what makes a repricing number meaningful.

Usage:
    python -u scripts/fetch_sw_depth.py            # resumes automatically
    python -u scripts/fetch_sw_depth.py --restart  # ignore the checkpoint
    python -u scripts/fetch_sw_depth.py --climate  # future-climate edition
"""

import csv
import io
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import shapely
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import load_districts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "sw_depth.csv")
CKPT = os.path.join(DATA, "cache", "sw_depth_progress.npz")

EA_SW = ("https://environment.data.gov.uk/spatialdata/"
         "nafra2-risk-of-flooding-from-surface-water/wms")
EA_SW_CC = ("https://environment.data.gov.uk/spatialdata/"
            "nafra2-risk-of-flooding-from-surface-water-climate-change/wms")

# (layer stem, csv key, threshold in metres). The climate-change edition
# uses the same names with a cc01 infix.
DEPTHS = [("0_2m_depth", "d02", 0.2),
          ("0_3m_depth", "d03", 0.3),
          ("0_6m_depth", "d06", 0.6),
          ("0_9m_depth", "d09", 0.9),
          ("1_2m_depth", "d12", 1.2)]


def layer_name(stem, climate):
    return f"rofsw_cc01_{stem}" if climate else f"rofsw_{stem}"

# Same legend anchors as fetch_surface_water.py (antialiasing -> nearest).
EA_ANCHORS = np.array([[85, 91, 157],     # High   1in30
                       [154, 159, 222],   # Medium 1in100
                       [195, 224, 255]])  # Low    1in1000

PX = 13.0
TILE = 2048
BBOX = (82000, 5000, 660000, 660000)      # England, BNG


# Tiles that could not be fetched at all - checked before writing, since a
# dropped tile is silently missing area rather than an error.
FAILED = []


def http_image(url):
    delay = 5
    for attempt in range(6):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (uk-risk-map)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGBA")
        except Exception as e:
            print(f"    retry {attempt + 1}/6 in {delay}s: {e}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 120)
    FAILED.append(url)
    return None


def masks_for_tile(layer, bbox, service=EA_SW):
    """Return {'high': mask, 'low': mask} for one depth layer, or None."""
    minx, miny, maxx, maxy = bbox
    q = dict(service="WMS", version="1.3.0", request="GetMap",
             layers=layer, crs="EPSG:27700",
             bbox=f"{minx},{miny},{maxx},{maxy}",
             width=TILE, height=TILE, format="image/png", transparent="true")
    img = http_image(service + "?" + urllib.parse.urlencode(q))
    if img is None:
        return None
    a = np.asarray(img)
    painted = a[:, :, 3] > 16
    if not painted.any():
        return {}
    rgb = a[:, :, :3].astype(np.int32)
    d = ((rgb[:, :, None, :] - EA_ANCHORS[None, None, :, :]) ** 2).sum(-1)
    nearest = d.argmin(-1)
    return {"high": painted & (nearest <= 1), "low": painted}


def main():
    global OUT, CKPT
    args = sys.argv[1:]
    restart = "--restart" in args
    climate = "--climate" in args
    service = EA_SW_CC if climate else EA_SW
    if climate:
        OUT = os.path.join(DATA, "sw_depth_cc.csv")
        CKPT = os.path.join(DATA, "cache", "sw_depth_cc_progress.npz")
        print("CLIMATE-CHANGE edition -> sw_depth_cc.csv", flush=True)

    print("loading districts...", flush=True)
    gdf = load_districts().to_crs(27700)
    names = gdf["name"].values
    tree = shapely.STRtree(gdf.geometry.values)
    n = len(gdf)
    area = shapely.area(gdf.geometry.values)

    keys = [k for _, k, _ in DEPTHS]
    frac = {f"{k}_{b}": np.zeros(n) for k in keys for b in ("high", "low")}
    done_cols = set()

    if not restart and os.path.exists(CKPT):
        z = np.load(CKPT, allow_pickle=False)
        if int(z["n"]) == n:
            for key in frac:
                if key in z:
                    frac[key] = z[key]
            done_cols = set(int(v) for v in z["done_cols"])
            print(f"resuming: {len(done_cols)} columns already done", flush=True)
        else:
            print("checkpoint district count differs - restarting", flush=True)

    minx, miny, maxx, maxy = BBOX
    nx = int(np.ceil((maxx - minx) / (TILE * PX)))
    ny = int(np.ceil((maxy - miny) / (TILE * PX)))
    print(f"england: {nx}x{ny} tiles at {PX}m/px, {len(DEPTHS)} depth layers",
          flush=True)

    t_start = time.time()
    for ix in range(nx):
        if ix in done_cols:
            continue
        n_fetched = 0
        for iy in range(ny):
            x0, y0 = minx + ix * TILE * PX, miny + iy * TILE * PX
            bbox = (x0, y0, x0 + TILE * PX, y0 + TILE * PX)
            if len(tree.query(shapely.box(*bbox))) == 0:
                continue          # no district overlaps this tile (sea)
            for stem, key, _ in DEPTHS:
                layer = layer_name(stem, climate)
                masks = masks_for_tile(layer, bbox, service)
                if masks is None:
                    print(f"    !! giving up on {layer} at {bbox}", flush=True)
                    continue
                n_fetched += 1
                if not masks:
                    continue      # nothing painted anywhere in this tile
                for band, mask in masks.items():
                    if not mask.any():
                        continue
                    rows, cols = np.nonzero(mask)
                    pts = shapely.points(bbox[0] + (cols + 0.5) * PX,
                                         bbox[3] - (rows + 0.5) * PX)
                    pairs = tree.query(pts, predicate="intersects")
                    frac[f"{key}_{band}"] += (
                        np.bincount(pairs[1], minlength=n) * PX * PX) / area
                time.sleep(0.1)
        done_cols.add(ix)
        os.makedirs(os.path.dirname(CKPT), exist_ok=True)
        np.savez(CKPT, n=np.array(n), done_cols=np.array(sorted(done_cols)),
                 **frac)
        el = time.time() - t_start
        print(f"  col {ix + 1}/{nx} ({n_fetched} requests, "
              f"{el / 60:.1f} min elapsed)", flush=True)

    write_csv(names, frac, n)


def write_csv(names, frac, n):
    global OUT
    # A dropped tile reads as "no water this deep here", which nothing
    # downstream can distinguish from real data. Refuse to write over the
    # real filename if any tile was lost. The per-column checkpoint means a
    # rerun resumes rather than starting over.
    if FAILED:
        OUT = OUT + ".partial"
        print(f"\n  !! {len(FAILED)} tile(s) could not be fetched. The result "
              f"is INCOMPLETE - missing tiles read as 'no depth here'.\n"
              f"  !! writing {OUT} instead; rerun to resume and fill them.",
              flush=True)
    keys = [k for _, k, _ in DEPTHS]
    # enforce the nesting the data should already satisfy: a deeper band can
    # never cover more area than a shallower one, and 'high' <= 'low'.
    for band in ("high", "low"):
        for i in range(len(keys) - 1, 0, -1):
            deeper, shallower = f"{keys[i]}_{band}", f"{keys[i - 1]}_{band}"
            frac[shallower] = np.maximum(frac[shallower], frac[deeper])
    for k in keys:
        frac[f"{k}_low"] = np.maximum(frac[f"{k}_low"], frac[f"{k}_high"])

    cols = [f"{k}_{b}" for k in keys for b in ("high", "low")]
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name"] + cols)
        for i in range(n):
            w.writerow([names[i]]
                       + [round(float(np.clip(frac[c][i], 0, 1)), 6)
                          for c in cols])
    print(f"wrote {OUT}", flush=True)
    for c in cols:
        v = np.clip(frac[c], 0, 1)
        print(f"  {c}: mean {v.mean():.5f}  max {v.max():.4f}  "
              f"nonzero {int((v > 0).sum())}", flush=True)


if __name__ == "__main__":
    main()
