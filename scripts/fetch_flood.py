"""Compute per-district flood-risk area fractions from national open data.

  England  : EA NaFRA2 "Rivers and Sea defended flood risk extents -
             present day" (OGL), rasterised via WMS at 100 m —
             high = rivers 1in100 / sea 1in200 defended,
             low envelope = rivers+sea 1in1000 defended.
  Wales    : NRW Flood Risk Assessment Wales (FRAW, OGL) rivers + sea,
             rasterised via WMS at 100 m with CQL risk filters —
             high = risk High+Medium (~1in100 or worse),
             low envelope = all risk bands (~1in1000).
  Scotland : SEPA flood maps (OGL) via FeatureServer vector queries
             (the map services have a 1:85k minScale so WMS-style export
             renders nothing at 100 m) — high = river+coastal medium
             likelihood (1in200), low envelope = low likelihood (1in1000).

Northern Ireland has no anonymous national service (boundaries are
GB-only, so this is moot).

Usage: fetch_flood.py [region ...]   e.g. `fetch_flood.py wales scotland`
       re-runs only those regions and merges with the existing CSV.

Output: data/flood_fractions.csv  (name, f_high, f_low) where f_* is the
fraction of district area inside the extent (f_low includes f_high).
"""

import csv
import io
import json
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

PX = 100.0          # metres per pixel (raster regions)
TILE = 1000         # pixels per tile (100 km)
OUT = os.path.join("data", "flood_fractions.csv")

EA = ("https://environment.data.gov.uk/spatialdata/"
      "rivers-and-sea-defended-and-undefended-flood-risk-extents-present-day/wms")
NRW = "https://datamap.gov.wales/geoserver/ows"
SEPA = "https://map.sepa.org.uk/server/rest/services/Open"

FRAW_R = "inspire-nrw:NRW_FLOOD_RISK_FROM_RIVERS"
FRAW_S = "inspire-nrw:NRW_FLOOD_RISK_FROM_SEA"
CQL_HIGH = "risk IN ('High','Medium')"

REGIONS = {
    "england": dict(
        mode="raster", bbox=(82000, 5000, 660000, 660000),
        bands=dict(
            high=[("wms13", EA, "Rivers_1in100_Sea_1in200_defended_extents", None)],
            low=[("wms13", EA, "Rivers_1in1000_Sea_1in1000_defended_extents", None)],
        ),
    ),
    "wales": dict(
        mode="raster", bbox=(170000, 160000, 360000, 400000),
        bands=dict(
            high=[("wms11", NRW, FRAW_R, CQL_HIGH), ("wms11", NRW, FRAW_S, CQL_HIGH)],
            low=[("wms11", NRW, FRAW_R, None), ("wms11", NRW, FRAW_S, None)],
        ),
    ),
    "scotland": dict(
        mode="vector",
        bands=dict(
            high=[("River_Flooding_Medium_Likelihood", 1),
                  ("Coastal_Flooding_Medium_Likelihood", 7)],
            low=[("River_Flooding_Low_Likelihood", 2),
                 ("Coastal_Flooding_Low_Likelihood", 8)],
        ),
    ),
}


# ------------------------------------------------------------- raster path


def tile_url(kind, base, layer, cql, bbox):
    minx, miny, maxx, maxy = bbox
    if kind == "wms13":
        q = dict(service="WMS", version="1.3.0", request="GetMap", layers=layer,
                 crs="EPSG:27700", bbox=f"{minx},{miny},{maxx},{maxy}",
                 width=TILE, height=TILE, format="image/png", transparent="true")
    else:  # wms11 (GeoServer)
        q = dict(service="WMS", version="1.1.1", request="GetMap", layers=layer,
                 styles="", srs="EPSG:27700", bbox=f"{minx},{miny},{maxx},{maxy}",
                 width=TILE, height=TILE, format="image/png", transparent="true")
        if cql:
            q["cql_filter"] = cql
    return base + "?" + urllib.parse.urlencode(q)


# Tiles that could not be fetched at all. A skipped tile is silently
# missing area - the CSV still looks complete - so this is checked before
# anything is written.
FAILED = []


def fetch_mask(kind, base, layer, cql, bbox):
    """Return boolean (TILE, TILE) array of painted pixels, or None.

    Backoff is exponential and generous: a transient DNS or connection
    drop otherwise costs a tile permanently, and three attempts five
    seconds apart is not enough to ride one out.
    """
    url = tile_url(kind, base, layer, cql, bbox)
    delay = 5
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                raw = r.read()
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            return np.asarray(img)[:, :, 3] > 16
        except Exception as e:
            print(f"    retry {attempt + 1}/6 {layer} in {delay}s: {e}",
                  flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 120)
    print(f"    !! GIVING UP on tile {bbox} layer {layer}", flush=True)
    FAILED.append((layer, bbox))
    return None


def run_raster(region, gdf, tree, frac):
    minx, miny, maxx, maxy = region["bbox"]
    area = shapely.area(gdf.geometry.values)
    nx = int(np.ceil((maxx - minx) / (TILE * PX)))
    ny = int(np.ceil((maxy - miny) / (TILE * PX)))
    for ix in range(nx):
        for iy in range(ny):
            x0, y0 = minx + ix * TILE * PX, miny + iy * TILE * PX
            bbox = (x0, y0, x0 + TILE * PX, y0 + TILE * PX)
            if len(tree.query(shapely.box(*bbox))) == 0:
                continue
            for band, layers in region["bands"].items():
                mask = None
                for kind, base, layer, cql in layers:
                    m = fetch_mask(kind, base, layer, cql, bbox)
                    if m is not None:
                        mask = m if mask is None else (mask | m)
                if mask is None or not mask.any():
                    continue
                rows, cols = np.nonzero(mask)
                pts = shapely.points(bbox[0] + (cols + 0.5) * PX,
                                     bbox[3] - (rows + 0.5) * PX)
                pairs = tree.query(pts, predicate="intersects")
                px_area = np.bincount(pairs[1], minlength=len(area)) * PX * PX
                frac[band] += px_area / area
            time.sleep(0.15)
        print(f"  col {ix + 1}/{nx} done", flush=True)


# ------------------------------------------------------------- vector path


def run_vector(region, gdf, tree, frac):
    from pyproj import Transformer
    dist_geoms = gdf.geometry.values
    area = shapely.area(dist_geoms)
    t4326 = Transformer.from_crs(4326, 27700, always_xy=True)

    for band, layers in region["bands"].items():
        for svc, lid in layers:
            offset, total = 0, 0
            while True:
                q = dict(where="1=1", outFields="", returnGeometry="true",
                         outSR=27700, maxAllowableOffset=100, f="geojson",
                         resultOffset=offset, resultRecordCount=1000)
                url = f"{SEPA}/{svc}/FeatureServer/{lid}/query?" + urllib.parse.urlencode(q)
                data = None
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(url, timeout=300) as r:
                            data = json.load(r)
                        break
                    except Exception as e:
                        print(f"    retry {attempt + 1} {svc}: {e}", flush=True)
                        time.sleep(5)
                if data is None or "features" not in data:
                    print(f"    ABORT {svc} at offset {offset}", flush=True)
                    break
                feats = data["features"]
                if not feats:
                    break
                geoms = shapely.from_geojson(
                    json.dumps({"type": "GeometryCollection",
                                "geometries": [f["geometry"] for f in feats
                                               if f.get("geometry")]}))
                geoms = np.array(shapely.get_parts(geoms))
                if len(geoms):
                    # f=geojson may come back as lon/lat regardless of outSR
                    gx, gy = shapely.get_x(shapely.centroid(geoms[0])), 0
                    if abs(gx) <= 180:
                        geoms = shapely.transform(
                            geoms, lambda xy: np.column_stack(
                                t4326.transform(xy[:, 0], xy[:, 1])))
                    geoms = shapely.make_valid(geoms)
                    pairs = tree.query(geoms, predicate="intersects")
                    if pairs.shape[1]:
                        inter = shapely.intersection(geoms[pairs[0]],
                                                     dist_geoms[pairs[1]])
                        frac[band] += np.bincount(
                            pairs[1], weights=shapely.area(inter),
                            minlength=len(area)) / area
                total += len(feats)
                offset += len(feats)
                if len(feats) < 1000:
                    break
            print(f"  {svc}: {total} features", flush=True)


# ------------------------------------------------------------------- main


def main():
    global OUT
    args = sys.argv[1:]
    if "--climate" in args:
        # The EA publishes a climate-change edition of this exact product:
        # same service, same layer names with a _CCP1 suffix, and no scale
        # cap, so it can be fetched at the same 100 m/px. Using the matched
        # pair matters - comparing against a differently derived product
        # would confound the method change with the climate change.
        # England only; NRW and SEPA publish no equivalent.
        for band in REGIONS["england"]["bands"].values():
            for i, (mode, url, layer, cql) in enumerate(band):
                band[i] = (mode,
                           url.replace("-present-day/", "-climate-change/"),
                           layer + "_CCP1", cql)
        OUT = os.path.join("data", "flood_fractions_cc.csv")
        args = [a for a in args if a != "--climate"] or ["england"]
        print(f"CLIMATE-CHANGE edition (England) -> {OUT}", flush=True)
    selected = [a for a in args if a in REGIONS] or list(REGIONS)
    print(f"regions: {selected}", flush=True)

    print("loading districts...", flush=True)
    gdf = load_districts().to_crs(27700)
    names = gdf["name"].values
    tree = shapely.STRtree(gdf.geometry.values)
    n = len(gdf)
    frac = {"high": np.zeros(n), "low": np.zeros(n)}

    # keep contributions of regions NOT being re-run
    if os.path.exists(OUT) and len(selected) < len(REGIONS):
        old = {}
        with open(OUT, newline="") as fh:
            for row in csv.DictReader(fh):
                old[row["name"]] = (float(row["f_high"]), float(row["f_low"]))
        frac["high"] += np.array([old.get(nm, (0, 0))[0] for nm in names])
        frac["low"] += np.array([old.get(nm, (0, 0))[1] for nm in names])
        print("merged existing CSV", flush=True)

    for name in selected:
        region = REGIONS[name]
        print(f"{name} ({region['mode']})...", flush=True)
        if region["mode"] == "raster":
            run_raster(region, gdf, tree, frac)
        else:
            run_vector(region, gdf, tree, frac)

    f_high = np.clip(frac["high"], 0, 1)
    f_low = np.clip(np.maximum(frac["low"], frac["high"]), 0, 1)

    # A dropped tile leaves a hole that reads as "no flood zone here", and
    # nothing downstream can tell that apart from real data. Write to
    # .partial so an incomplete fetch cannot quietly become model input.
    if FAILED:
        OUT = OUT + ".partial"
        print(f"\n  !! {len(FAILED)} tile(s) could not be fetched. The result "
              f"is INCOMPLETE - missing tiles read as 'no flood risk'.\n"
              f"  !! writing {OUT} instead; rerun before using it.",
              flush=True)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "f_high", "f_low"])
        for i in range(n):
            w.writerow([names[i], round(float(f_high[i]), 5),
                        round(float(f_low[i]), 5)])
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
