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
             6.5 m from its four legend colours and sampled at the
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
             f_top = High alone (>= 3.3%), since exp/rofrs-split: until
             then High and Medium were one band priced at 1.5%, below
             High's own floor, and 52% of the English postcodes in
             f_high are High.
  Wales    : NRW FRAW rivers + sea polygons (WFS), point-in-polygon,
             since exp/wales-vector: f_high = High + Medium, f_low = any
             band. Until then these were the 100 m WMS masks of
             fetch_flood.REGIONS, which inflated the >=1% zone (see
             FRAW_LAYERS). f_top = FRAW High (>= 1 in 30, the EA's own
             threshold for High), since exp/rofrs-split.
  Scotland : SEPA river + coastal likelihood polygons, point-in-polygon.

Scotland does not supply f_top from its own data: SEPA's High
likelihood is 1 in 10, not 1 in 30, so read as the top band it would
put only the >= 10% homes there. A Scottish zone postcode carries
ENGLAND's share of zone postcodes that are High (TOP_SHARE_ENGLAND,
measured by the same run) as a fractional in_top: it keeps the blended
zone rate, and no geography is invented. Wales does supply it, from the
polygons: FRAW High is 0.556 of the Welsh zone postcodes against 0.524
for England. The 100 m masks the polygons replaced had said 0.757, and
this split was first measured carrying England's share into Wales for
exactly that reason.

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
denominator, plus f_top (always <= f_high):

    data/flood_fractions.csv   name, f_high, f_low, f_top

--climate: England only, the EA's climate-change edition of the same
risk product (`rofrs_cc01_4band`, same legend, same scale cap), sampled
at the same English postcodes and shrunk with England-only priors, to
data/flood_fractions_cc.csv. The present-day and climate fractions
must share a denominator: flood_future() substitutes one for the other,
and an area-share future against a postcode-share present would report
Hull's flood risk FALLING under climate change.

Every fetch also writes its per-postcode flags to
data/cache/flood_postcode_flags[_cc].csv. --flags-from PATH aggregates
such a file instead of fetching, which is how both grains are built from
one fetch: run once on either checkout, then --flags-from on the other.
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
# decodes, and the same 2048 px tiles (at 6.5 m a pixel: RS_PX below).
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
# 6.5 m, not the 13 m of the surface-water product, since exp/rofrs-split.
# The service paints every band's polygons at any scale, but at 13 m the
# High polygons come out FAT: re-reading ~3,400 postcodes in four 4 km
# boxes (York, Staines, Thorne, Hatfield), the High share of the >=1% zone
# was 0.571 at 2 m, 0.573 at 4 m, 0.574 at 6.5 m and 0.613 at 13 m - so
# 13 m moved ~10% of Medium homes into High while High and Medium were
# one priced band and nobody could see it. Converged by 6.5 m; 2 m would
# cost 42x the tiles for nothing. 851 tiles hold English postcodes here,
# against 239 at 13 m. Nationally the re-read moved the English zone +1.1%
# and the envelope +5.4% against 13 m. Checked against the EA's own
# residential counts per constituency (KSI, not validation - same raster)
# High reads 1.21x the EA's High (1.30x at 13 m), Medium 0.99x, the zone
# 1.10x: the High share of the zone is 0.524 of postcodes against 0.473 of
# the EA's properties. That residual is not resolution (converged above);
# postcodes are not addresses, and it is left measured, not corrected.
RS_PX, RS_TILE = 6.5, 2048
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


def classify_rofrs(a, rows, cols, windows=RS_WINDOWS):
    """Band codes (RS_NAMES) at pixels (rows, cols) of an RGBA tile, and
    whether each was read directly rather than settled by its neighbours.

    Only the requested pixels are settled: the model needs the band at
    each postcode's pixel, and settling a whole 2048-px tile costs ten
    times the fetch. `windows` widens the search for sparse layers (the
    depth layers' small deep polygons are mostly stroke)."""
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
    for win in windows:
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
                         f"within {windows[-1] // 2} of them - the style "
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


# The service drops polygons from a render depending on where the request
# box falls, not only on its pixel size. Measured at TN23 9 (Ashford), 35
# postcodes all inside one High polygon, 6.5 m a pixel: with the box's
# west edge at 15 positions the polygon drew at some and vanished at the
# rest, at every box size tried (3.3, 6.7 and 13.3 km); the box's north-
# south position made no difference, and the vanished polygon never
# re-appeared as some other band. The single-grid reads had lost it (6.5 m
# tiles) or kept it (13 m tiles) by luck of the grid. So England is read
# on RS_PASSES tile grids, each shifted by a third of a tile, and combined
# by combine_passes.
#
# Most disagreement between passes is NOT a dropout. Of the 5,504 English
# postcodes banded by some passes but not all (present day, 2026-09-27),
# 81% sat on a polygon outline in the passes that banded them and took
# their neighbourhood's band - a pixel either side of an edge, which moves
# with the grid's sub-pixel phase - and they were scattered: only 452 had
# a postcode with the same pattern within 150 m. Taking any pass's band
# (a union) would have buffered every polygon, as the Welsh masks did,
# adding 956 postcodes to the >=1% zone; a majority of the passes adds 79.
# A dropout is different: a whole polygon vanishes, taking its neighbours
# with it. So a band fewer than half the passes drew is kept only where it
# is one of at least RS_RESCUE_N postcodes with the same pattern, each
# within RS_RESCUE_M of the next. Present day, that is exactly TN23 9's 34
# postcodes at 100 or 150 m and any RS_RESCUE_N from 5 to 17 (at 250 m
# and fewer than 8, a 7-postcode N17 9 group joins); the climate layer
# drew TN23 9 in every pass, and the rule keeps two clusters of exactly
# 5 (TR21 0, E14 9), which RS_RESCUE_N of 6 would drop. A 6-postcode dropout two passes drew
# (SW11 7) the majority keeps on its own. Clusters found by one pass, 1,
# and by two, 1: Chao's f1^2 / (2 f2) puts the dropouts every pass missed
# at 0.5 of a cluster, so a fourth pass would buy nothing.
RS_PASSES = ((0.0, 0.0), (1 / 3, 1 / 3), (2 / 3, 2 / 3))
RS_RESCUE_M, RS_RESCUE_N = 150.0, 5


def rofrs_pass(pc, x, y, shift):
    """One read of every English postcode on a tile grid shifted by
    `shift` (fractions of a tile, east and north). Returns (code, direct,
    carried) arrays over pc; code -1 where not sampled."""
    T = RS_PX * RS_TILE
    minx = ENGLAND_BBOX[0] - shift[0] * T
    miny = ENGLAND_BBOX[1] - shift[1] * T
    nx = int(np.ceil((ENGLAND_BBOX[2] - minx) / T))
    ny = int(np.ceil((ENGLAND_BBOX[3] - miny) / T))
    code = np.full(len(pc), -1, dtype=np.int8)        # -1: not sampled
    direct = np.zeros(len(pc), dtype=bool)
    carried = np.zeros(len(pc), dtype=bool)     # climate gap -> present day
    eng = (pc["country"] == "England").values
    ix_all = np.clip(((x - minx) // T).astype(int), 0, nx - 1)
    iy_all = np.clip(((y - miny) // T).astype(int), 0, ny - 1)
    tiles = sorted(set(zip(ix_all[eng].tolist(), iy_all[eng].tolist())))
    print(f"england: {EA_RS_LAYER}, grid shifted {shift[0]:.2f},{shift[1]:.2f}: "
          f"{len(tiles)} tiles of {T / 1000:.1f} km hold postcodes "
          f"({RS_PX} m/px)", flush=True)
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
    return code, direct, carried


def dropout_clusters(codes, x, y):
    """Postcodes where fewer than half the passes drew a band but which lie
    in a cluster of at least RS_RESCUE_N such postcodes with the same
    presence pattern, each within RS_RESCUE_M of the next: a polygon that
    vanished from some renders, not an edge (see RS_PASSES)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    codes = np.asarray(codes)
    k = codes.shape[0]
    drew = codes > 0
    pattern = (drew * (1 << np.arange(k))[:, None]).sum(axis=0)
    minority = drew.any(axis=0) & (drew.sum(axis=0) < k // 2 + 1)
    out = np.zeros(codes.shape[1], dtype=bool)
    sel = np.nonzero(minority)[0]
    if len(sel) < RS_RESCUE_N:
        return out
    pairs = cKDTree(np.c_[x[sel], y[sel]]).query_pairs(
        RS_RESCUE_M, output_type="ndarray")
    pairs = pairs[pattern[sel[pairs[:, 0]]] == pattern[sel[pairs[:, 1]]]]
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                       shape=(len(sel), len(sel)))
    _, label = connected_components(graph, directed=False)
    out[sel] = np.bincount(label)[label] >= RS_RESCUE_N
    return out


def combine_passes(codes, rescue=None):
    """One band per postcode from several passes (rows = passes): the most
    common NON-ZERO band, ties going to the higher band, where more than
    half the passes drew one - or where `rescue` (dropout_clusters) says a
    minority band is a vanished polygon - and 0 otherwise. -1 (not
    sampled) anywhere stays -1; 5 (Unavailable) is a band like any other
    here, so the caller's guard still sees it."""
    codes = np.asarray(codes)
    out = np.zeros(codes.shape[1], dtype=np.int8)
    best = np.zeros(codes.shape[1], dtype=int)
    for c in (1, 2, 3, 4, 5):                    # ascending: ties go higher
        n = (codes == c).sum(axis=0)
        win = (n > 0) & (n >= best)
        out[win], best[win] = c, n[win]
    keep = (codes > 0).sum(axis=0) >= codes.shape[0] // 2 + 1
    if rescue is not None:
        keep |= rescue
    out[~keep] = 0
    out[(codes < 0).any(axis=0)] = -1
    return out


def rofrs_england(pc, x, y, in_high, in_low, passes=None):
    """Band codes for every English postcode: RS_PASSES shifted reads,
    combined by combine_passes. `passes` supplies already-read pass codes
    (rows) instead of fetching, as the reproduction script does."""
    eng = (pc["country"] == "England").values
    if passes is None:
        reads = [rofrs_pass(pc, x, y, sh) for sh in RS_PASSES]
        passes = np.array([r[0] for r in reads])
        direct = np.logical_and.reduce([r[1] for r in reads])
        carried = np.logical_or.reduce([r[2] for r in reads])
    else:
        passes = np.asarray(passes)
        direct = carried = None
    rescue = np.zeros(len(pc), dtype=bool)
    rescue[eng] = dropout_clusters(passes[:, eng], x[eng], y[eng])
    code = combine_passes(passes, rescue)
    in_high[eng] = np.isin(code[eng], (3, 4))
    in_low[eng] = np.isin(code[eng], (2, 3, 4))
    n = int(eng.sum())
    tally = ", ".join(f"{RS_NAMES[c]} {int((code[eng] == c).sum()) / n:.3%}"
                      for c in (4, 3, 2, 1, 0, 5))
    print(f"  english postcodes by band: {tally}", flush=True)
    sampled = (passes[:, eng] >= 0).all(axis=0)
    nz = (passes[:, eng] > 0).sum(axis=0)
    k = passes.shape[0]
    found = [int(((nz == j) & sampled).sum()) for j in range(1, k + 1)]
    print(f"  postcodes with a band in exactly 1..{k} of {k} passes: {found}; "
          f"a minority band kept as a dropout cluster: "
          f"{int(rescue[eng].sum())} postcodes", flush=True)
    if direct is not None:
        print(f"  read directly by colour in every pass: {direct[eng].mean():.2%}; "
              f"the rest sat on a polygon stroke in some pass and took its "
              f"neighbourhood's band there", flush=True)
    if CLIMATE and carried is not None:
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


# Every fetch leaves its per-postcode flags in the cache; --flags-from
# PATH aggregates a saved flags file instead of fetching (see main()).
FLAGS_OUT = os.path.join(DATA, "cache", "flood_postcode_flags"
                         + ("_cc" if CLIMATE else "") + ".csv")
FLAGS_FROM = None
if "--flags-from" in sys.argv[1:]:
    FLAGS_FROM = sys.argv[sys.argv.index("--flags-from") + 1]


# Wales is read from NRW's FRAW polygons themselves (WFS), point-in-polygon
# at the unit postcodes, since exp/wales-vector. Until then it was
# raster_region: WMS masks at 100 m a pixel, "flooded" wherever alpha > 16,
# and NRW draws at 40% opacity, so a pixel a sixth covered by any band's
# polygon counted - a buffer round every polygon. FRAW's High and Medium
# are thin slivers along channels and shores, so the buffer inflated the
# >=1% zone most: in a 4 km box round Grangetown, Cardiff, 46 postcodes
# were in it at 100 m and 3 are inside the polygons (the whole envelope,
# 812 vs 759, was nearly right). Re-reading the WMS at 10 m and 5 m did
# not converge (0.37x and 0.29x the 100 m zone in six 10 km boxes), so
# no pixel size fixes it; the polygons need no decoding at all.
FRAW_LAYERS = ("inspire-nrw:NRW_FLOOD_RISK_FROM_RIVERS",
               "inspire-nrw:NRW_FLOOD_RISK_FROM_SEA")
FRAW_BAND = {"High": 3, "Medium": 2, "Low": 1}   # High >= 1 in 30
# Read in bounding boxes, each fetched WHOLE, never in pages: this
# GeoServer pages only when sorted, and the only sort key both layers
# carry (mm_id) is not unique - paging on it read 105,431 distinct river
# features of 105,679, and 248 polygons would have been written as dry.
# A box that comes back at the cap, or errors, is split in four.
FRAW_TILE_M = 20_000
FRAW_CAP = 5_000


def _fraw_get(layer, bbox, count, hits=False):
    q = dict(service="WFS", version="2.0.0", request="GetFeature",
             typeNames=layer, outputFormat="application/json",
             srsName="EPSG:27700",
             bbox=",".join(f"{v:.0f}" for v in bbox) + ",EPSG:27700")
    if hits:
        q["resultType"] = "hits"
        q.pop("outputFormat")
    else:
        q["count"] = count
    return ff.NRW + "?" + urllib.parse.urlencode(q)


def fraw_matched(layer, bbox):
    """numberMatched for a layer in a box - the completeness reference."""
    for tries in range(4):
        try:
            with urllib.request.urlopen(_fraw_get(layer, bbox, 0, True),
                                        timeout=300) as r:
                m = re.search(rb'numberMatched="(\d+)"', r.read())
            if m:
                return int(m.group(1))
        except Exception as e:                            # noqa: BLE001
            print(f"    retry {tries + 1} {layer} hits: {e}", flush=True)
        time.sleep(10)
    raise SystemExit(f"{layer}: no feature count - refusing to write a "
                     "partial Wales")


def fraw_tile(layer, bbox, depth=0):
    """Every feature of a layer intersecting bbox, splitting the box in
    four when the reply is capped or the server errors."""
    import urllib.error
    tries = 0
    while True:
        try:
            with urllib.request.urlopen(_fraw_get(layer, bbox, FRAW_CAP),
                                        timeout=600) as r:
                feats = json.load(r)["features"]
            break
        except urllib.error.HTTPError as e:
            if e.code >= 500 and depth < 6:
                feats = None
                break
            err = e
        except Exception as e:                            # noqa: BLE001
            err = e
        tries += 1
        if tries >= 4:
            raise SystemExit(f"{layer}: no answer for {bbox} ({err}) - "
                             "refusing to write a partial Wales")
        print(f"    retry {tries} {layer}: {err}", flush=True)
        time.sleep(10)
    if feats is not None and len(feats) < FRAW_CAP:
        return feats
    if depth >= 6:
        raise SystemExit(f"{layer}: {bbox} still capped at depth {depth}")
    x0, y0, x1, y1 = bbox
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for q in ((x0, y0, xm, ym), (xm, y0, x1, ym),
              (x0, ym, xm, y1), (xm, ym, x1, y1)):
        out += fraw_tile(layer, q, depth + 1)
    return out


def vector_wales(pc, x, y, in_high, in_low):
    """FRAW rivers + sea at every Welsh postcode: in_high where a High or
    Medium polygon holds it (>= 1% rivers, >= 0.5% sea), in_low for any
    band. Returns the per-postcode FRAW band (FRAW_BAND, 0 = none, the
    higher of rivers and sea) for the diagnostic cache."""
    minx, miny, maxx, maxy = ff.REGIONS["wales"]["bbox"]
    idx_all = np.nonzero((pc["country"] == "Wales").values)[0]
    xs, ys = x[idx_all], y[idx_all]
    if not ((xs >= minx) & (xs < maxx) & (ys >= miny) & (ys < maxy)).all():
        raise SystemExit("a Welsh postcode lies outside the Wales box - "
                         "widen ff.REGIONS['wales']['bbox']")
    tree = shapely.STRtree(shapely.points(xs, ys))
    band = np.zeros(len(pc), dtype=np.int8)
    for layer in FRAW_LAYERS:
        matched = fraw_matched(layer, (minx, miny, maxx, maxy))
        ids = set()
        for tx in np.arange(minx, maxx, FRAW_TILE_M):
            for ty in np.arange(miny, maxy, FRAW_TILE_M):
                tb = (tx, ty, min(tx + FRAW_TILE_M, maxx),
                      min(ty + FRAW_TILE_M, maxy))
                sel = ((xs >= tb[0] - 1) & (xs < tb[2] + 1)
                       & (ys >= tb[1] - 1) & (ys < tb[3] + 1))
                feats = fraw_tile(layer, tb)
                # a polygon reaching into this box from a neighbour is
                # fetched again there; the id set counts it once
                ids.update(f["id"] for f in feats)
                if not sel.any():
                    continue
                risk = [f["properties"]["risk"] for f in feats]
                unknown = set(risk) - set(FRAW_BAND)
                if unknown:
                    raise SystemExit(f"{layer}: unknown risk values {unknown}")
                keep = [i for i, f in enumerate(feats) if f.get("geometry")]
                if not keep:
                    continue
                geoms = shapely.make_valid(shapely.from_geojson(
                    [json.dumps(feats[i]["geometry"]) for i in keep]))
                code = np.array([FRAW_BAND[risk[i]] for i in keep],
                                dtype=np.int8)
                gi, pi = tree.query(geoms, predicate="intersects")
                if len(pi):
                    np.maximum.at(band, idx_all[pi], code[gi])
                time.sleep(0.15)
        if len(ids) != matched:
            raise SystemExit(f"{layer}: read {len(ids)} distinct features "
                             f"of {matched} in the Wales box - refusing to "
                             "write a partial Wales")
        print(f"  wales {layer.split(':')[1]}: {matched} features", flush=True)
    in_high[idx_all] |= band[idx_all] >= 2
    in_low[idx_all] |= band[idx_all] >= 1
    w = band[idx_all]
    print("  wales postcodes by FRAW band: " + ", ".join(
        f"{k} {(w == v).mean():.3%}" for k, v in FRAW_BAND.items()), flush=True)
    return band


# SEPA serves its polygons generalised to `maxAllowableOffset` metres. This
# was 100 until 2026-09-25, which is fine for drawing a map and wrong for
# point-in-polygon at a postcode: against a 5 m reference, the coastal
# medium layer flagged 1,136 Scottish postcodes instead of 859 (+32%) and
# 85% of the true set was misplaced (HANDOFF "REVIEWED 2026-09-25").
# 5 m is under the 6.5 m pixel England's bands are read at;
# the 5-vs-1 m check is in the HANDOFF entry for this change.
SEPA_TOLERANCE_M = 5
SEPA_PAGE = 1000


def sepa_page(svc, lid, offset, rec):
    """One page of a SEPA layer, halving the page on a server error.

    Unsimplified coastal polygons are single features of tens of MB and
    SEPA answers a 1,000-feature page of them with HTTP 500; a smaller
    page is the only thing that helps, so a 500 halves the page at once
    and anything else is retried as before. Returns (data, rec)."""
    import urllib.error
    tries = 0
    while True:
        q = dict(where="1=1", outFields="", returnGeometry="true",
                 outSR=27700, maxAllowableOffset=SEPA_TOLERANCE_M,
                 f="geojson", resultOffset=offset, resultRecordCount=rec,
                 orderByFields="OBJECTID")
        url = (f"{ff.SEPA}/{svc}/FeatureServer/{lid}/query?"
               + urllib.parse.urlencode(q))
        try:
            with urllib.request.urlopen(url, timeout=600) as r:
                data = json.load(r)
            if "features" in data:
                return data, rec
            err = data.get("error", data)
        except urllib.error.HTTPError as e:
            err = e
            if e.code >= 500 and rec > 1:
                rec = max(1, rec // 2)
                print(f"    {svc}: HTTP {e.code} at offset {offset} - page "
                      f"-> {rec}", flush=True)
                continue
        except Exception as e:                            # noqa: BLE001
            err = e
        tries += 1
        if tries >= 4:
            raise SystemExit(f"{svc}: no answer at offset {offset} ({err}) - "
                             "refusing to write a partial Scotland")
        print(f"    retry {tries} {svc}: {err}", flush=True)
        time.sleep(10)


def vector_scotland(pc, x, y, in_high, in_low):
    from pyproj import Transformer
    region = ff.REGIONS["scotland"]
    idx_all = np.nonzero((pc["country"] == "Scotland").values)[0]
    tree = shapely.STRtree(shapely.points(x[idx_all], y[idx_all]))
    t4326 = Transformer.from_crs(4326, 27700, always_xy=True)
    for band, layers in region["bands"].items():
        target = in_high if band == "high" else in_low
        for svc, lid in layers:
            offset, total, rec = 0, 0, SEPA_PAGE
            while True:
                data, rec = sepa_page(svc, lid, offset, rec)
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
                # exceededTransferLimit is the authoritative "there is
                # more"; the page-size test alone would stop early once
                # sepa_page has shrunk the page.
                more = (data.get("exceededTransferLimit")
                        or data.get("properties", {}).get("exceededTransferLimit"))
                if not more and len(feats) < rec:
                    break
            print(f"  scotland {svc}: {total} features", flush=True)


def top_with_scotland(country, in_high, in_top):
    """Per-postcode top-band weight: 0/1 in England and Wales, where the
    maps supply the band, and in Scotland England's share of zone
    postcodes that are High, carried by each zone postcode (see the
    module docstring for why SEPA cannot supply it). Returns floats."""
    country = np.asarray(country)
    eng = country == "England"
    sco = country == "Scotland"
    share = in_top[eng].sum() / max(in_high[eng].sum(), 1)
    top = np.where(sco, 0, in_top).astype(float)
    top[sco] = share * in_high[sco]
    print(f"  TOP_SHARE_ENGLAND: {share:.4f} of English zone postcodes are "
          "High; carried by each Scottish zone postcode", flush=True)
    return top


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
    in_top = np.zeros(len(pc), dtype=bool)      # England code 4, FRAW High

    if FLAGS_FROM:
        # Aggregate an earlier fetch's per-postcode flags instead of
        # fetching: both grains then read ONE fetch, so a district and a
        # sector table built this way cannot disagree about a postcode.
        fl = pd.read_csv(FLAGS_FROM).set_index("postcode")
        miss = ~pc["postcode"].isin(fl.index)
        if miss.any():
            raise SystemExit(f"{int(miss.sum())} postcodes are not in "
                             f"{FLAGS_FROM} - it is from another ONSPD vintage")
        if "in_top" not in fl.columns:
            raise SystemExit(f"{FLAGS_FROM} has no in_top column - it "
                             "predates the High/Medium split; refetch")
        in_high = fl.loc[pc["postcode"], "in_high"].values.astype(bool)
        in_low = fl.loc[pc["postcode"], "in_low"].values.astype(bool)
        # float: a Scottish zone postcode carries TOP_SHARE_ENGLAND
        top = fl.loc[pc["postcode"], "in_top"].values.astype(float)
        print(f"flags from {FLAGS_FROM} - nothing fetched", flush=True)
    else:
        if not CLIMATE:
            wband = vector_wales(pc, x, y, in_high, in_low)
            # per-postcode FRAW band, diagnostic like rofrs_bands.csv
            os.makedirs(os.path.join(DATA, "cache"), exist_ok=True)
            wal = (pc["country"] == "Wales").values
            pd.DataFrame({"postcode": pc["postcode"][wal],
                          "band": wband[wal]}).to_csv(
                os.path.join(DATA, "cache", "fraw_bands.csv"), index=False)
            in_top[wal] = wband[wal] == FRAW_BAND["High"]
            vector_scotland(pc, x, y, in_high, in_low)
        code = rofrs_england(pc, x, y, in_high, in_low)
        if ff.FAILED:
            raise SystemExit(f"{len(ff.FAILED)} tiles failed - refusing to "
                             "write a partial file")
        eng = (pc["country"] == "England").values
        in_top[eng] = code[eng] == 4
        top = top_with_scotland(pc["country"].values, in_high, in_top)
        # The per-postcode bands, kept for diagnosis (which postcodes fell
        # in "Unavailable", which sit on a stroke). Not model input;
        # fetch_rs_depth_postcodes.py reads the same layer in its own
        # pass and reports its agreement with this file when present.
        os.makedirs(os.path.join(DATA, "cache"), exist_ok=True)
        pd.DataFrame({"postcode": pc["postcode"], "band": code}).to_csv(
            os.path.join(DATA, "cache",
                         f"rofrs_bands{'_cc' if CLIMATE else ''}.csv"),
            index=False)
    pc["in_high"] = in_high
    pc["in_low"] = in_low | in_high
    pc["in_top"] = np.minimum(top, pc["in_high"].values)
    if not FLAGS_FROM:
        os.makedirs(os.path.dirname(FLAGS_OUT), exist_ok=True)
        pc[["postcode", "country", "in_high", "in_low", "in_top"]].astype(
            {"in_high": int, "in_low": int}).to_csv(
            FLAGS_OUT, index=False, float_format="%.6g")
        print(f"wrote {FLAGS_OUT}", flush=True)

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
    # f_top shrinks exactly as f_high does, with the same weight toward
    # the same parents, so f_top <= f_high holds in every unit.
    parent_of = {"sector": "district", "district": "area"}[grain]
    own = pc.groupby(grain).agg(n=("in_high", "size"), h=("in_high", "sum"),
                                l=("in_low", "sum"), t=("in_top", "sum"))
    area = pc.groupby("area").agg(f_high=("in_high", "mean"),
                                  f_low=("in_low", "mean"),
                                  f_top=("in_top", "mean"))
    if grain == "district":
        prior = area
    else:
        dist = pc.groupby("district").agg(n=("in_high", "size"),
                                          h=("in_high", "sum"),
                                          l=("in_low", "sum"),
                                          t=("in_top", "sum"))
        pa = area.reindex(dist.index.map(area_of)).set_index(dist.index)
        prior = pd.DataFrame({
            "f_high": (dist["h"] + K_PRIOR * pa["f_high"]) / (dist["n"] + K_PRIOR),
            "f_low": (dist["l"] + K_PRIOR * pa["f_low"]) / (dist["n"] + K_PRIOR),
            "f_top": (dist["t"] + K_PRIOR * pa["f_top"]) / (dist["n"] + K_PRIOR)})
    rows, thin, missing = [], 0, 0
    for n in names:
        p = n.split(" ")[0] if grain == "sector" else area_of(n)
        if p not in prior.index:
            missing += 1
            continue
        ph, pl, pt = prior.loc[p, ["f_high", "f_low", "f_top"]]
        if n in own.index:
            cnt, h, l, t = own.loc[n, ["n", "h", "l", "t"]]
            if cnt < K_PRIOR:
                thin += 1
            fh = (h + K_PRIOR * ph) / (cnt + K_PRIOR)
            fl = (l + K_PRIOR * pl) / (cnt + K_PRIOR)
            ft = (t + K_PRIOR * pt) / (cnt + K_PRIOR)
        else:
            thin += 1
            fh, fl, ft = ph, pl, pt
        rows.append((n, fh, fl, ft))
    pd.DataFrame(rows, columns=["name", "f_high", "f_low", "f_top"]).to_csv(
        OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT}: {len(rows)} {grain}s ({thin} with fewer than "
          f"{K_PRIOR} postcodes, shrunk toward their {parent_of}; {missing} "
          f"left to the median fallback); postcodes in high "
          f"{pc['in_high'].mean():.3%}, low {pc['in_low'].mean():.3%}, "
          f"top {pc['in_top'].mean():.3%}")

if __name__ == "__main__":
    main()
