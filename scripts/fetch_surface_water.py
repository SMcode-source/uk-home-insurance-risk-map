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

Usage: fetch_surface_water.py [region ...]   (default: all; merges into
existing data/sw_fractions.csv for regions not re-run)

Output: data/sw_fractions.csv (name, sw_high, sw_low), area fractions,
sw_low includes sw_high.
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

EA_SW = ("https://environment.data.gov.uk/spatialdata/"
         "nafra2-risk-of-flooding-from-surface-water/wms")
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


def http_image(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGBA")
        except Exception as e:
            print(f"    retry {attempt + 1}: {e}", flush=True)
            time.sleep(5)
    return None


def masks_for_tile(region, bbox):
    """Return dict band -> boolean mask (tile, tile), or None."""
    kind, tile = region["kind"], region["tile"]
    minx, miny, maxx, maxy = bbox
    bstr = f"{minx},{miny},{maxx},{maxy}"

    if kind == "ea_color":
        q = dict(service="WMS", version="1.3.0", request="GetMap",
                 layers="rofsw", crs="EPSG:27700", bbox=bstr,
                 width=tile, height=tile, format="image/png",
                 transparent="true")
        img = http_image(EA_SW + "?" + urllib.parse.urlencode(q))
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
            out[band] = np.asarray(img)[:, :, 3] > 16
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
        out[band] = np.asarray(img)[:, :, 3] > 16
    return out


def main():
    global OUT
    args = sys.argv[1:]
    if "--out" in args:
        i = args.index("--out")
        OUT = args[i + 1]
        args = args[:i] + args[i + 2:]
    no_merge = "--no-merge" in args
    selected = [a for a in args if a in REGIONS] or list(REGIONS)
    print(f"regions: {selected} -> {OUT}", flush=True)

    print("loading districts...", flush=True)
    gdf = load_districts().to_crs(27700)
    names = gdf["name"].values
    tree = shapely.STRtree(gdf.geometry.values)
    n = len(gdf)
    area = shapely.area(gdf.geometry.values)
    frac = {"high": np.zeros(n), "low": np.zeros(n)}

    if not no_merge and os.path.exists(OUT) and len(selected) < len(REGIONS):
        with open(OUT, newline="") as fh:
            old = {r["name"]: (float(r["sw_high"]), float(r["sw_low"]))
                   for r in csv.DictReader(fh)}
        frac["high"] += np.array([old.get(nm, (0, 0))[0] for nm in names])
        frac["low"] += np.array([old.get(nm, (0, 0))[1] for nm in names])
        print("merged existing CSV", flush=True)

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
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "sw_high", "sw_low"])
        for i in range(n):
            w.writerow([names[i], round(float(sw_high[i]), 5),
                        round(float(sw_low[i]), 5)])
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
