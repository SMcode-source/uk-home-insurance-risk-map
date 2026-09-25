"""Per-district SURFACE WATER flood-risk area fractions (open data).

  England  : EA NaFRA2 Risk of Flooding from Surface Water (rofsw) WMS.
             The layer only renders at scales finer than 1:50,000, so
             tiles are fetched at 13 m/px and the three category colours
             are decoded per pixel (High 1in30 / Medium 1in100 / Low
             1in1000). sw_high = High+Medium (>=1% AEP), sw_low = any.
  Wales    : NRW FRAW surface water & small watercourses (WMS, 100 m,
             CQL risk filter). sw_high = High+Medium, sw_low = all.
  Scotland : SEPA surface water medium (1in200) / low (1in1000)
             likelihood MapServers at 20 m/px. Their sublayers are
             default-hidden, so exports pass layers=show:<id>.

Usage: fetch_surface_water.py [region ...]   (default: all three)

There is NO partial merge. The number written for a unit is a sum over
every region that paints it, the regions overlap at the borders, and a
sum cannot be un-summed - so re-running one region against an existing
file is refused rather than guessed at. Fetch all three, or --out to a
fresh file. See _refuse_partial_merge for what each guess cost.

Output: data/sw_fractions.csv (name, sw_high, sw_low), area fractions,
sw_low includes sw_high.

SUPERSEDED for the model's surface-water fractions on 2026-09-06 by
fetch_sw_postcodes.py, which samples the SAME masks (masks_for_tile,
REGIONS) at every unit-postcode centroid and writes the share of
postcodes instead of the share of area. This module stays as the mask
source and as the AREA-share measurement the depth conditional needs
(data/sw_fractions_area.csv); running it directly would overwrite the
committed postcode-share file with area shares - copy the output to
sw_fractions_area.csv instead.
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

OUT = os.path.join("data", "sw_fractions.csv")

# A pixel's alpha is how much of it the layer COVERS, not a yes/no: rofsw
# is drawn from 2 m flow paths, so a 13 m pixel with one thin path through
# it comes back faint. Measured 2026-09-25 (alpha census, every layer read
# here): EA present, climate and depth layers carry 255 alpha levels; NRW
# carries 16 (4x4 supersampling) on a 40%-opacity style, so a fully
# covered NRW pixel is alpha 102 and quarter cover renders as 26; SEPA's
# export is binary. A postcode counts as inside the extent when its pixel
# is at least SW_COVERAGE_MIN covered, on each source's own scale.
#
# 0.25 is FITTED, and against an external count: the EA's own residential
# properties at risk (KSI packs, scripts/validate_flood_england.py) over
# 94 constituencies in ten 26 km tiles. Chosen on half of them (md5 split),
# the held-out half scores 1.17x the EA's >=1% share and 1.02x its
# any-band share (Spearman +0.94 / +0.97). The rule it replaced, alpha > 16
# (6% cover on the EA scale, 16% on NRW's), read 1.45x / 1.43x. Treating
# alpha as a probability instead (no constant) reads 0.76x / 0.71x: the EA
# counts a property at risk more generously than centroid-in-extent does.
SW_COVERAGE_MIN = 0.25
FULL_ALPHA = {"ea_color": 255, "wms_cql": 102, "sepa": 255}


def covered(alpha, full):
    """Pixels at least SW_COVERAGE_MIN covered; half a level of rounding slack."""
    return alpha >= SW_COVERAGE_MIN * full - 0.5

EA_SW = ("https://environment.data.gov.uk/spatialdata/"
         "nafra2-risk-of-flooding-from-surface-water/wms")
# The EA's climate-change edition of the same product: same service family,
# same legend, same 1:50,000 scale cap, so the two are directly comparable.
# --climate swaps to it (England only; NRW and SEPA publish no equivalent).
EA_SW_CC = ("https://environment.data.gov.uk/spatialdata/"
            "nafra2-risk-of-flooding-from-surface-water-climate-change/wms")
EA_SW_LAYER = "rofsw"
NRW = "https://datamap.gov.wales/geoserver/ows"
SEPA = "https://map.sepa.org.uk/server/rest/services/Open"
FRAW_SW = "inspire-nrw:NRW_FLOOD_RISK_FROM_SURFACE_WATER_SMALL_WATERCOURSES"

# EA rofsw legend colours (antialiasing -> nearest anchor)
EA_ANCHORS = np.array([[85, 91, 157],     # High  (1in30)
                       [154, 159, 222],   # Medium (1in100)
                       [195, 224, 255]])  # Low   (1in1000)

REGIONS = {
    "england": dict(
        kind="ea_color", px=13.0, tile=2048,
        bbox=(82000, 5000, 660000, 660000),
    ),
    "wales": dict(
        kind="wms_cql", px=20.0, tile=1000,
        bbox=(170000, 160000, 360000, 400000),
        layer=FRAW_SW, cql_high="risk IN ('High','Medium')",
    ),
    "scotland": dict(
        kind="sepa", px=20.0, tile=2000,
        bbox=(5000, 530000, 470000, 1220000),
        high=("Surface_Water_and_Small_Watercourses_Flooding_Medium_Likelihood", 4),
        low=("Surface_Water_and_Small_Watercourses_Flooding_Low_Likelihood", 5),
    ),
}


# Tiles that could not be fetched at all. A dropped tile is silently
# missing area - the CSV still looks complete - so the count is checked
# before anything is written.
FAILED = []


def http_image(url):
    """Fetch one tile, or None after exhausting retries.

    Backoff is exponential and generous: a transient DNS or connection
    failure (this machine sleeps, and the EA service drops connections)
    otherwise costs a tile permanently, and three quick attempts five
    seconds apart is not enough to ride out either.
    """
    delay = 5
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGBA")
        except Exception as e:
            print(f"    retry {attempt + 1}/6 in {delay}s: {e}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 120)
    print(f"    !! GIVING UP on {url[:120]}", flush=True)
    FAILED.append(url)
    return None


def masks_for_tile(region, bbox):
    """Return dict band -> boolean mask (tile, tile), or None."""
    kind, tile = region["kind"], region["tile"]
    minx, miny, maxx, maxy = bbox
    bstr = f"{minx},{miny},{maxx},{maxy}"

    if kind == "ea_color":
        q = dict(service="WMS", version="1.3.0", request="GetMap",
                 layers=EA_SW_LAYER, crs="EPSG:27700", bbox=bstr,
                 width=tile, height=tile, format="image/png",
                 transparent="true")
        img = http_image(region.get("service", EA_SW) + "?"
                         + urllib.parse.urlencode(q))
        if img is None:
            return None
        a = np.asarray(img)
        painted = covered(a[:, :, 3], FULL_ALPHA["ea_color"])
        if not painted.any():
            return {}
        rgb = a[:, :, :3].astype(np.int32)
        d = ((rgb[:, :, None, :] - EA_ANCHORS[None, None, :, :]) ** 2).sum(-1)
        nearest = d.argmin(-1)
        return {"high": painted & (nearest <= 1), "low": painted}

    if kind == "wms_cql":
        out = {}
        for band, cql in [("high", region["cql_high"]), ("low", None)]:
            q = dict(service="WMS", version="1.1.1", request="GetMap",
                     layers=region["layer"], styles="", srs="EPSG:27700",
                     bbox=bstr, width=tile, height=tile,
                     format="image/png", transparent="true")
            if cql:
                q["cql_filter"] = cql
            img = http_image(NRW + "?" + urllib.parse.urlencode(q))
            if img is None:
                return None
            out[band] = covered(np.asarray(img)[:, :, 3], FULL_ALPHA["wms_cql"])
        return out

    # sepa
    out = {}
    for band in ["high", "low"]:
        svc, lid = region[band]
        q = dict(bbox=bstr, bboxSR=27700, imageSR=27700,
                 size=f"{tile},{tile}", format="png", transparent="true",
                 f="image", layers=f"show:{lid}")
        img = http_image(f"{SEPA}/{svc}/MapServer/export?"
                         + urllib.parse.urlencode(q))
        if img is None:
            return None
        out[band] = covered(np.asarray(img)[:, :, 3], FULL_ALPHA["sepa"])
    return out


def _refuse_partial_merge(selected, out):
    """A per-unit sum cannot be un-summed, so a partial re-run cannot merge.

    The value written for a unit is the sum of every region that paints
    it, and the regions OVERLAP at the borders: TD12 straddles the Tweed,
    so it carries an EA contribution and a SEPA one; SY10 and SY15 carry
    an EA contribution although `data/country.csv` calls them Wales.

    Both ways of merging a partial re-run are therefore wrong, and both
    were measured on 2026-09-12:

      - seed every unit from the old file and add the new value on top,
        and the re-run region is counted twice. 77% of district values
        rose, mean sw_low 0.156 -> 0.285.
      - keep the old value only for units the re-run cannot measure,
        keyed on country.csv, and the border breaks the key both ways.
        England-labelled TD12 lost its Scottish half (0.11754 ->
        0.05845) and CH4 its Welsh part; Wales- and Scotland-labelled
        border units kept an old value that was ENTIRELY English and
        then had England added again, so 22 districts and 32 sectors
        came back exactly doubled (SY10 0.05269 -> 0.10538).

    There is no third way while one number per unit is all that is
    stored. So refuse, and say what to do instead.
    """
    raise SystemExit(
        f"refusing to merge {selected} into the existing {out}.\n"
        f"The value in that file is a SUM over regions, and the regions\n"
        f"overlap at the borders, so the contribution of {selected} cannot\n"
        f"be removed from it before the new one is added. Either fetch\n"
        f"every region (pass no region argument), or pass --out to write a\n"
        f"fresh file, or pass --no-merge to accept zeros outside "
        f"{selected}.")


def main():
    global OUT, EA_SW_LAYER
    args = sys.argv[1:]
    if "--out" in args:
        i = args.index("--out")
        OUT = args[i + 1]
        args = args[:i] + args[i + 2:]
    if "--climate" in args:
        # England only: the climate-change edition exists for the EA layer,
        # not for NRW or SEPA, so restrict rather than silently mixing a
        # future England with a present-day Wales and Scotland.
        EA_SW_LAYER = "rofsw_cc01"
        REGIONS["england"]["service"] = EA_SW_CC
        if OUT == os.path.join("data", "sw_fractions.csv"):
            OUT = os.path.join("data", "sw_fractions_cc.csv")
        args = ["england", "--no-merge"]
        print(f"CLIMATE-CHANGE edition (England) -> {OUT}", flush=True)
    # The climate edition has ONE source, so there is nothing to merge with:
    # the non-England rows of a climate file are the handful of border units
    # the EA layer paints across the line (6 Scottish and 16 Welsh districts),
    # and they come from this fetch, not from a previous one.
    no_merge = "--no-merge" in args
    selected = [a for a in args if a in REGIONS] or list(REGIONS)
    print(f"regions: {selected} -> {OUT}", flush=True)

    if not no_merge and os.path.exists(OUT) and len(selected) < len(REGIONS):
        _refuse_partial_merge(selected, OUT)

    print("loading districts...", flush=True)
    gdf = load_districts().to_crs(27700)
    names = gdf["name"].values
    tree = shapely.STRtree(gdf.geometry.values)
    n = len(gdf)
    area = shapely.area(gdf.geometry.values)
    frac = {"high": np.zeros(n), "low": np.zeros(n)}

    for rname in selected:
        region = REGIONS[rname]
        px, tile = region["px"], region["tile"]
        minx, miny, maxx, maxy = region["bbox"]
        nx = int(np.ceil((maxx - minx) / (tile * px)))
        ny = int(np.ceil((maxy - miny) / (tile * px)))
        print(f"{rname}: {nx}x{ny} tiles at {px}m/px", flush=True)
        for ix in range(nx):
            for iy in range(ny):
                x0, y0 = minx + ix * tile * px, miny + iy * tile * px
                bbox = (x0, y0, x0 + tile * px, y0 + tile * px)
                if len(tree.query(shapely.box(*bbox))) == 0:
                    continue
                masks = masks_for_tile(region, bbox)
                if not masks:
                    continue
                for band, mask in masks.items():
                    if not mask.any():
                        continue
                    rows, cols = np.nonzero(mask)
                    pts = shapely.points(bbox[0] + (cols + 0.5) * px,
                                         bbox[3] - (rows + 0.5) * px)
                    pairs = tree.query(pts, predicate="intersects")
                    frac[band] += (np.bincount(pairs[1], minlength=n)
                                   * px * px) / area
                time.sleep(0.1)
            print(f"  col {ix + 1}/{nx}", flush=True)

    sw_high = np.clip(frac["high"], 0, 1)
    sw_low = np.clip(np.maximum(frac["low"], frac["high"]), 0, 1)

    # A dropped tile leaves a hole that looks like "no surface water here",
    # and nothing downstream can tell the difference. Write to .partial
    # instead so an incomplete fetch cannot quietly become model input.
    if FAILED:
        OUT = OUT + ".partial"
        print(f"\n  !! {len(FAILED)} tile(s) could not be fetched. The result "
              f"is INCOMPLETE - missing tiles read as 'no surface water', "
              f"which is indistinguishable from real data downstream.\n"
              f"  !! writing {OUT} instead; rerun before using it.",
              flush=True)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "sw_high", "sw_low"])
        for i in range(n):
            w.writerow([names[i], round(float(sw_high[i]), 5),
                        round(float(sw_low[i]), 5)])
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
