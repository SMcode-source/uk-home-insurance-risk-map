"""River/sea flood fractions as the share of unit POSTCODES in the extent.

fetch_flood.py measures the share of a district's AREA inside the
national flood extents. The model's first external validation
(2026-09-05, HANDOFF) held that ordering against NRW's people at risk
per household in Wales and found sea at Spearman +0.70, surface water
+0.57 and rivers at -0.13: in valley geography the floodplain is a
sliver of the district and carries most of the housing, so area share
is a poor proxy for the share of homes. Sampling the SAME extents at
every Code-Point Open / ONSPD unit-postcode centroid instead (each
unit postcode is ~15 addresses) took rivers to +0.42 (high band) and
+0.58 (envelope), and river+sea to +0.75.

This script does that for all of Great Britain in one pass:

  England  : EA NaFRA2 Risk of Flooding from Rivers and Sea
             (`rofrs_4band`, DATA_SOURCES #44), decoded per pixel at
             13 m from its four legend colours and sampled at the
             postcode's pixel: f_high = High + Medium (>= 1% a year),
             f_low = High + Medium + Low (>= 0.1%). Very Low is below
             the low band and counts as neither. Until
             exp/rofrs-4band this read the defended EXTENTS
             (`Rivers_1in100_Sea_1in200_defended_extents`), which is
             land an event covers, not the chance at a property - and
             not even one return period, since it unions rivers at 1%
             with sea at 0.5%. Measured against the EA's own residential
             properties at risk (validate_flood_england.py) the extents
             ranked constituencies at Spearman +0.832 while surface
             water, already on the EA's risk product, ranked at +0.932.
  Wales    : NRW FRAW rivers + sea, same masks.
  Scotland : SEPA river + coastal likelihood polygons, point-in-polygon.

Every postcode row carries its district and sector, so one fetch
serves both grains; the grain written is the one whose names
load_districts() returns on this checkout (sector names contain a
space). Thin units are shrunk toward their parent (sector -> district,
district -> postcode area) with a prior worth K_PRIOR postcodes, so a
sector with two postcodes cannot land on 0 or 1; the 816 sectors with
no live postcode at all in this ONSPD vintage (0.46% of households)
take their district's share outright. Anything still missing falls to
the national median inside scores_real._load_fraction_csv, as before.

Needs data/postcode_centroids.csv (fetch_onspd.py). Same output file
and columns as fetch_flood.py, same meaning of high/low, different
denominator:

    data/flood_fractions.csv   name, f_high, f_low

--climate: England only, the EA's climate-change edition of the same
risk product (`rofrs_cc01_4band`, same legend, same scale cap), sampled
at the same English postcodes and shrunk with England-only priors, to
data/flood_fractions_cc.csv. The present-day and climate fractions
must share a denominator: flood_future() substitutes one for the other,
and an area-share future against a postcode-share present would report
Hull's flood risk FALLING under climate change.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_flood as ff                          # noqa: E402
from build_model import load_districts           # noqa: E402

PX, TILE = ff.PX, ff.TILE
DATA = "data"
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
OUT = os.path.join(DATA, "flood_fractions.csv")
K_PRIOR = 20        # postcodes of prior weight; see main()
AREA_RE = re.compile(r"[A-Z]+")


def area_of(district):
    """Postcode area of a district or sector name: its leading letters."""
    return AREA_RE.match(district).group(0)


CLIMATE = "--climate" in sys.argv[1:]
if CLIMATE:
    OUT = os.path.join(DATA, "flood_fractions_cc.csv")

# England: the EA's risk product. Same service family, legend and
# 1:50,000 scale cap as the surface-water product fetch_surface_water.py
# decodes, so the same 13 m / 2048 px tiles.
EA_RS = ("https://environment.data.gov.uk/spatialdata/"
         "nafra2-risk-of-flooding-from-rivers-and-sea"
         + ("-climate-change" if CLIMATE else "") + "/wms")
EA_RS_LAYER = "rofrs_cc01_4band" if CLIMATE else "rofrs_4band"
# The climate edition is "Unavailable" - not published - over whole
# districts of exactly the ground that floods: measured 2026-09-22 at
# 1.9% of English postcodes, 100% of PE11-PE25 and CB6, the Somerset
# Levels (TA8, TA10) and the Lincolnshire coast. Read as "none", PE11's
# f_high would go from 0.65 today to 0 under climate change, the same
# fall the area-share climate file once reported for Hull. So where the
# climate band is unavailable, the postcode keeps its PRESENT-DAY band:
# no climate uplift where none was modelled, and never a fall. The
# present-day tile is fetched here, by this run, rather than read from
# the present-day run's cache - an input recovered from another run's
# output is an undeclared dependency.
EA_RS_PRESENT = ("https://environment.data.gov.uk/spatialdata/"
                 "nafra2-risk-of-flooding-from-rivers-and-sea/wms")
EA_RS_PRESENT_LAYER = "rofrs_4band"
RS_PX, RS_TILE = 13.0, 2048
ENGLAND_BBOX = (82000, 5000, 660000, 660000)

# The legend (GetLegendGraphic, read 2026-09-22), in code order. The fill
# colours are exact in the tiles; what is not exact is a thin grey stroke
# (112,112,112) the style draws round every polygon and along the
# product's internal tile grid, blended over whatever fill it crosses.
# Nearest-colour on a stroke pixel is a coin toss, and the one boundary
# that matters most - Low against Very Low, which is f_low's edge - is
# also the closest pair of colours in the legend (23 RGB units apart).
# So a pixel is classed by colour only when it is opaque and within
# RS_EXACT of an anchor, and every other painted pixel takes the most
# common confident class round it, widening through RS_WINDOWS until one
# is found. Transparent pixels vote too, for "none": a stroke on the
# OUTER edge of a polygon is half outside it, and letting only the fills
# vote would grow every polygon by a pixel. What must not happen is a
# fallback to the nearest colour - a dark-grey stroke is nearest to High,
# and dense strokes are where the houses are.
RS_ANCHORS = np.array([[85, 91, 157],     # 4 High     (>= 3.3%)
                       [154, 159, 222],   # 3 Medium   (1 - 3.3%)
                       [195, 224, 255],   # 2 Low      (0.1 - 1%)
                       [200, 247, 255],   # 1 Very low (< 0.1%)
                       [176, 179, 180]])  # 5 Unavailable
RS_CODE = np.array([4, 3, 2, 1, 5], dtype=np.int8)
RS_NAMES = {0: "none", 1: "very low", 2: "low", 3: "medium", 4: "high",
            5: "unavailable"}
RS_EXACT = 12               # RGB distance for a pixel to be read by colour
RS_WINDOWS = (5, 11, 21)    # neighbourhoods tried in turn, in pixels
RS_FAINT = 128              # an inexact pixel fainter than this is "none"


def classify_rofrs(a, rows, cols):
    """Band codes (RS_NAMES) at pixels (rows, cols) of an RGBA tile, and
    whether each was read directly rather than settled by its neighbours.

    Only the requested pixels are settled: the model needs the band at
    each postcode's pixel, and settling a whole 2048-px tile costs ten
    times the fetch."""
    rgb = a[:, :, :3].astype(np.int32)
    alpha = a[:, :, 3]
    clear = alpha <= 16
    d = ((rgb[:, :, None, :] - RS_ANCHORS[None, None, :, :]) ** 2).sum(-1)
    exact = ~clear & (alpha >= 250) & (d.min(-1) <= RS_EXACT ** 2)
    grid = np.zeros(alpha.shape, dtype=np.int8)
    grid[exact] = RS_CODE[d.argmin(-1)[exact]]
    known = exact | clear

    out = grid[rows, cols].copy()
    direct = known[rows, cols]
    todo = ~direct & (alpha[rows, cols] >= RS_FAINT)
    H, W = alpha.shape
    for win in RS_WINDOWS:
        if not todo.any():
            break
        i = np.nonzero(todo)[0]
        off = np.arange(win) - win // 2
        rr = np.clip(rows[i, None, None] + off[None, :, None], 0, H - 1)
        cc = np.clip(cols[i, None, None] + off[None, None, :], 0, W - 1)
        ok = known[rr, cc].reshape(len(i), -1)
        cls = grid[rr, cc].reshape(len(i), -1).astype(np.int64)
        votes = np.zeros((len(i), 6), dtype=np.int64)
        np.add.at(votes, (np.repeat(np.arange(len(i)), ok.shape[1])[ok.ravel()],
                          cls.ravel()[ok.ravel()]), 1)
        has = votes.sum(1) > 0
        out[i[has]] = votes[has].argmax(1).astype(np.int8)
        todo[i[has]] = False
    if todo.any():
        raise SystemExit(f"{int(todo.sum())} pixels with no readable pixel "
                         f"within {RS_WINDOWS[-1] // 2} of them - the style "
                         f"has changed; re-read the legend")
    return out, direct


def http_rgba(url):
    """One tile as an RGBA array, or None (recorded in ff.FAILED)."""
    import io
    from PIL import Image
    delay = 5
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return np.asarray(Image.open(io.BytesIO(r.read())).convert("RGBA"))
        except Exception as e:                        # noqa: BLE001
            print(f"    retry {attempt + 1}/6 in {delay}s: {e}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 120)
    print(f"    !! GIVING UP on {url[:120]}", flush=True)
    ff.FAILED.append(url)
    return None


def rofrs_url(base, layer, bbox):
    q = dict(service="WMS", version="1.3.0", request="GetMap",
             layers=layer, crs="EPSG:27700",
             bbox=",".join(f"{v:.0f}" for v in bbox),
             width=RS_TILE, height=RS_TILE, format="image/png",
             transparent="true")
    return base + "?" + urllib.parse.urlencode(q)


def rofrs_england(pc, x, y, in_high, in_low):
    """Band codes for every English postcode, from the tiles that hold one."""
    minx, miny, maxx, maxy = ENGLAND_BBOX
    T = RS_PX * RS_TILE
    nx = int(np.ceil((maxx - minx) / T))
    ny = int(np.ceil((maxy - miny) / T))
    code = np.full(len(pc), -1, dtype=np.int8)        # -1: not sampled
    direct = np.zeros(len(pc), dtype=bool)
    carried = np.zeros(len(pc), dtype=bool)     # climate gap -> present day
    eng = (pc["country"] == "England").values
    ix_all = np.clip(((x - minx) // T).astype(int), 0, nx - 1)
    iy_all = np.clip(((y - miny) // T).astype(int), 0, ny - 1)
    tiles = sorted(set(zip(ix_all[eng].tolist(), iy_all[eng].tolist())))
    print(f"england: {EA_RS_LAYER}, {len(tiles)} tiles of {T / 1000:.1f} km "
          f"hold postcodes ({RS_PX} m/px)", flush=True)
    t0 = time.time()
    for k, (ix, iy) in enumerate(tiles):
        x0, y0 = minx + ix * T, miny + iy * T
        bbox = (x0, y0, x0 + T, y0 + T)
        a = http_rgba(rofrs_url(EA_RS, EA_RS_LAYER, bbox))
        if a is None:
            continue
        idx = np.nonzero(eng & (ix_all == ix) & (iy_all == iy))[0]
        cols = np.clip(((x[idx] - x0) / RS_PX).astype(int), 0, RS_TILE - 1)
        rows = np.clip(((bbox[3] - y[idx]) / RS_PX).astype(int), 0, RS_TILE - 1)
        code[idx], direct[idx] = classify_rofrs(a, rows, cols)
        gap = code[idx] == 5
        if CLIMATE and gap.any():
            p = http_rgba(rofrs_url(EA_RS_PRESENT, EA_RS_PRESENT_LAYER, bbox))
            if p is None:
                continue
            sub = idx[gap]
            code[sub], direct[sub] = classify_rofrs(p, rows[gap], cols[gap])
            carried[sub] = True
        if (k + 1) % 25 == 0 or k + 1 == len(tiles):
            print(f"  {k + 1}/{len(tiles)} tiles, {time.time() - t0:.0f}s",
                  flush=True)
        time.sleep(0.15)
    in_high[eng] = np.isin(code[eng], (3, 4))
    in_low[eng] = np.isin(code[eng], (2, 3, 4))
    n = int(eng.sum())
    tally = ", ".join(f"{RS_NAMES[c]} {int((code[eng] == c).sum()) / n:.3%}"
                      for c in (4, 3, 2, 1, 0, 5))
    print(f"  english postcodes by band: {tally}", flush=True)
    print(f"  read directly by colour: {direct[eng].mean():.2%}; the rest sat "
          f"on a polygon stroke and took their neighbourhood's band", flush=True)
    if CLIMATE:
        print(f"  climate band unavailable, present-day band carried: "
              f"{carried[eng].mean():.2%} of English postcodes", flush=True)
    if (code[eng] == 5).any():
        raise SystemExit(f"{int((code[eng] == 5).sum())} English postcodes "
                         f"have no published band at all - read as 'none' "
                         f"they would price as dry")
    unsampled = int((code[eng] < 0).sum())
    if unsampled and not ff.FAILED:
        raise SystemExit(f"{unsampled} English postcodes were never sampled")
    return code


def raster_region(name, pc, x, y, in_high, in_low):
    region = ff.REGIONS[name]
    minx, miny, maxx, maxy = region["bbox"]
    nx = int(np.ceil((maxx - minx) / (TILE * PX)))
    ny = int(np.ceil((maxy - miny) / (TILE * PX)))
    ctry = (pc["country"] == name.capitalize()).values
    for ix in range(nx):
        for iy in range(ny):
            x0, y0 = minx + ix * TILE * PX, miny + iy * TILE * PX
            bbox = (x0, y0, x0 + TILE * PX, y0 + TILE * PX)
            sel = ctry & (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
            if not sel.any():
                continue
            idx = np.nonzero(sel)[0]
            cols = np.clip(((x[idx] - bbox[0]) / PX).astype(int), 0, TILE - 1)
            rows = np.clip(((bbox[3] - y[idx]) / PX).astype(int), 0, TILE - 1)
            for band, layers in region["bands"].items():
                mask = None
                for kind, base, layer, cql in layers:
                    m = ff.fetch_mask(kind, base, layer, cql, bbox)
                    if m is not None:
                        mask = m if mask is None else (mask | m)
                if mask is None:
                    continue
                (in_high if band == "high" else in_low)[idx] |= mask[rows, cols]
            print(f"  {name} tile {ix},{iy}: {len(idx):,} postcodes", flush=True)
            time.sleep(0.15)


def vector_scotland(pc, x, y, in_high, in_low):
    from pyproj import Transformer
    region = ff.REGIONS["scotland"]
    idx_all = np.nonzero((pc["country"] == "Scotland").values)[0]
    tree = shapely.STRtree(shapely.points(x[idx_all], y[idx_all]))
    t4326 = Transformer.from_crs(4326, 27700, always_xy=True)
    for band, layers in region["bands"].items():
        target = in_high if band == "high" else in_low
        for svc, lid in layers:
            offset, total = 0, 0
            while True:
                q = dict(where="1=1", outFields="", returnGeometry="true",
                         outSR=27700, maxAllowableOffset=100, f="geojson",
                         resultOffset=offset, resultRecordCount=1000)
                url = (f"{ff.SEPA}/{svc}/FeatureServer/{lid}/query?"
                       + urllib.parse.urlencode(q))
                data = None
                for attempt in range(4):
                    try:
                        with urllib.request.urlopen(url, timeout=300) as r:
                            data = json.load(r)
                        break
                    except Exception as e:                # noqa: BLE001
                        print(f"    retry {attempt + 1} {svc}: {e}", flush=True)
                        time.sleep(10)
                if data is None or "features" not in data:
                    raise SystemExit(f"{svc}: no answer at offset {offset} - "
                                     "refusing to write a partial Scotland")
                feats = data["features"]
                if not feats:
                    break
                geoms = shapely.from_geojson(json.dumps(
                    {"type": "GeometryCollection",
                     "geometries": [f["geometry"] for f in feats if f.get("geometry")]}))
                geoms = np.array(shapely.get_parts(geoms))
                if len(geoms):
                    # f=geojson may come back lon/lat regardless of outSR
                    if abs(shapely.get_x(shapely.centroid(geoms[0]))) <= 180:
                        geoms = shapely.transform(
                            geoms, lambda xy: np.column_stack(
                                t4326.transform(xy[:, 0], xy[:, 1])))
                    geoms = shapely.make_valid(geoms)
                    pairs = tree.query(geoms, predicate="intersects")
                    if pairs.shape[1]:
                        target[idx_all[np.unique(pairs[1])]] = True
                total += len(feats)
                offset += len(feats)
                if len(feats) < 1000:
                    break
            print(f"  scotland {svc}: {total} features", flush=True)


def main():
    if not os.path.exists(CENTROIDS):
        raise SystemExit(f"{CENTROIDS} missing - run scripts/fetch_onspd.py first")
    pc = pd.read_csv(CENTROIDS)
    countries = ["England"] if CLIMATE else ["England", "Wales", "Scotland"]
    pc = pc[pc["country"].isin(countries)].reset_index(drop=True)
    # The postcode AREA is the leading letters of the outward code: EC for
    # EC1A, SW for SW1A, E for E1W. Derived here from the district rather
    # than read from the file, because the first cut of this script (and
    # fetch_onspd.py before 2026-09-06) took "all the letters" and gave the
    # 59 central-London districts with a letter suffix areas of their own
    # ("ECA"), which then never matched as a parent: those 59 districts
    # fell to the national median in the measured build.
    pc["area"] = pc["district"].map(area_of)
    print(("CLIMATE-CHANGE edition (England only) -> " + OUT) if CLIMATE
          else "present-day edition -> " + OUT, flush=True)
    print(f"unit postcodes: {len(pc):,}", flush=True)
    x = pc["easting"].values.astype(float)
    y = pc["northing"].values.astype(float)
    in_high = np.zeros(len(pc), dtype=bool)
    in_low = np.zeros(len(pc), dtype=bool)

    if not CLIMATE:
        raster_region("wales", pc, x, y, in_high, in_low)
        vector_scotland(pc, x, y, in_high, in_low)
    code = rofrs_england(pc, x, y, in_high, in_low)
    if ff.FAILED:
        raise SystemExit(f"{len(ff.FAILED)} tiles failed - refusing to write "
                         "a partial file")
    # The per-postcode bands, kept for diagnosis (which postcodes fell in
    # "Unavailable", which sit on a stroke). Not model input.
    os.makedirs(os.path.join(DATA, "cache"), exist_ok=True)
    pd.DataFrame({"postcode": pc["postcode"], "band": code}).to_csv(
        os.path.join(DATA, "cache", f"rofrs_bands{'_cc' if CLIMATE else ''}.csv"),
        index=False)
    pc["in_high"] = in_high
    pc["in_low"] = in_low | in_high

    names = load_districts()["name"].tolist()
    grain = "sector" if any(" " in n for n in names) else "district"
    # A unit with two live postcodes can only be 0, 1/2 or 1. 412 sectors
    # have fewer than 20 postcodes (0.27% of households) and 76 districts
    # do (0.04%); unshrunk, 359 of those sectors landed on exactly 0 or 1
    # and PH44 (one postcode) went from f_high 0.20 to 1.00 and +143 on
    # its premium. So each unit's share is the beta-binomial posterior
    # mean with its PARENT's share as the prior and a prior weight of
    # K_PRIOR postcodes (~300 addresses): a sector shrinks toward its
    # district, a district toward its postcode area. With hundreds of
    # postcodes the prior is a rounding error; with two, the unit takes
    # its parent's value. A parent with no postcodes falls through to
    # the national median inside scores_real._load_fraction_csv.
    # The prior is itself shrunk one level up: a sector in a district
    # with one postcode (PH44 4 in PH44) otherwise inherits a prior that
    # is as thin as it is, and 0/1 comes back through the back door.
    parent_of = {"sector": "district", "district": "area"}[grain]
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
    pd.DataFrame(rows, columns=["name", "f_high", "f_low"]).to_csv(
        OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT}: {len(rows)} {grain}s ({thin} with fewer than "
          f"{K_PRIOR} postcodes, shrunk toward their {parent_of}; {missing} "
          f"left to the median fallback); postcodes in high "
          f"{pc['in_high'].mean():.3%}, low {pc['in_low'].mean():.3%}")


if __name__ == "__main__":
    main()
