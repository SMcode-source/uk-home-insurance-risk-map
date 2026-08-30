#!/usr/bin/env python
"""Vector tiles, popup shards and a name index for the two map grains.

Both maps fetch the whole country as one GeoJSON today - 0.9 MB gzipped
for districts, 2.6 MB for sectors - at every zoom, whether you are
looking at the whole island or at one street. Tiles invert that: you
pay for what is on screen. Measured on the district asset that ships
today, same geometry and same numbers, delivery the only difference:

    whole UK (z5)        900 KB  ->  394 KB
    a London borough     900 KB  ->   84 KB
    street level         900 KB  ->   33 KB

and on sectors, against 2.6 MB: 1.05 MB, 231 KB, 98 KB.

Three things make that work, and each of them is load-bearing.

  * Only the columns that COLOUR the map travel in the tile - 20 of the
    62. The other 42 are read by the popup alone, which renders one unit
    at a time, and ship as one small file per postcode area (median
    4 KB for districts, 13 KB for sectors) fetched when a popup opens.
    Attributes are the BIGGER half of this payload, and a tile repeats
    them at every zoom: carrying all 62 costs 701 KB for the opening
    view instead of 394 KB, which is barely better than sending the
    whole country.

  * MAX_SIZE. GDAL caps a tile at 500 kB by default and, when one runs
    over, silently re-encodes it AT LOWER RESOLUTION. The national view
    degrades and nothing in a diff ever shows it.

  * The name/bbox index. Search, the ?d= deep link and the Ctrl+arrow
    walk all scan every loaded feature today. Under tiles "every loaded
    feature" means the viewport's, so all three would quietly stop
    working outside it. The index is the whole country, always present,
    and costs 41 KB gzipped for districts and 147 KB for sectors.

The tile/popup column split is read out of map/template.html itself,
so the tiles and the page they feed cannot drift apart.
"""

import json
import os
import sys
import time

import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_map import (ROOT, ROUND_DP, columns_read_by_template, read,
                       tile_columns)

OUT = os.path.join(ROOT, "map")

# GDAL's default is 500000, and going over it costs resolution rather
# than raising. 2 MB clears every tile in both grains; the check below
# fails the build if that ever stops being true.
MAX_TILE_BYTES = 2_000_000

# Zoom 4 covers the whole island in a handful of tiles. The top is 12
# for both grains: MapLibre overzooms vector data geometrically, so a
# z12 tile still draws crisp boundaries at z16 - the only thing frozen
# past the top zoom is how hard the geometry was simplified to reach it.
MINZOOM, MAXZOOM = 4, 12

GRAINS = [
    dict(grain="districts", source="data/districts_risk.geojson"),
    dict(grain="sectors", source="data/sectors_risk.geojson"),
]


def shard_key(name):
    """Postcode area of a unit name: 'YO25' and 'YO25 6' -> 'YO'.

    Taken from the name rather than the `area` column, which lives in
    the popup-only half and so is not carried in the tile - the browser
    has to derive the same key from the name it does have.
    """
    i = 0
    while i < len(name) and name[i].isalpha():
        i += 1
    return name[:i]


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))
    return os.path.getsize(path)


def build(grain, source, tile_cols, all_cols):
    src = os.path.join(ROOT, source)
    t0 = time.time()
    gdf = gpd.read_file(src)
    missing = set(all_cols) - set(gdf.columns)
    if missing:
        raise SystemExit(f"{source} lacks {sorted(missing)}, which the map "
                         f"template reads")
    # Round to exactly what web_asset writes. build_map.py cuts the
    # colour breaks over the ROUNDED values, so a tile carrying full
    # precision could put a unit the other side of a break from the one
    # the legend claims - the same trap, one layer down.
    for c in gdf.columns:
        if c != "geometry" and gdf[c].dtype.kind == "f":
            gdf[c] = gdf[c].round(ROUND_DP)

    print(f"{grain}: {len(gdf):,} units, {len(all_cols)} columns "
          f"({len(tile_cols)} tiled, {len(all_cols) - len(tile_cols)} in "
          f"popup shards), read in {time.time() - t0:.0f}s", flush=True)

    # --- tiles -----------------------------------------------------
    pm = os.path.join(OUT, "tiles", f"{grain}.pmtiles")
    os.makedirs(os.path.dirname(pm), exist_ok=True)
    if os.path.exists(pm):
        os.remove(pm)
    t0 = time.time()
    pyogrio.write_dataframe(
        gdf[sorted(tile_cols) + ["geometry"]], pm, driver="PMTiles",
        NAME=grain, MINZOOM=str(MINZOOM), MAXZOOM=str(MAXZOOM),
        MAX_SIZE=str(MAX_TILE_BYTES))
    print(f"  tiles/{grain}.pmtiles {os.path.getsize(pm) / 1e6:.1f} MB "
          f"z{MINZOOM}-{MAXZOOM} in {time.time() - t0:.0f}s", flush=True)

    props = gdf.drop(columns="geometry").to_dict("records")

    # --- popup shards, one file per postcode area ------------------
    popup_cols = sorted(all_cols - tile_cols)
    shards = {}
    for p in props:
        shards.setdefault(shard_key(p["name"]), {})[p["name"]] = \
            {k: p[k] for k in popup_cols}
    sizes = [write_json(os.path.join(OUT, "units", grain, f"{k}.json"), v)
             for k, v in sorted(shards.items())]
    sizes.sort()
    print(f"  units/{grain}/ {len(sizes)} area files, "
          f"median {sizes[len(sizes) // 2] / 1e3:.0f} KB, "
          f"max {sizes[-1] / 1e3:.0f} KB (uncompressed)", flush=True)

    # --- name + bbox index -----------------------------------------
    # 4 dp is ~11 m of longitude, far finer than a fitBounds needs.
    idx = []
    for name, geom in zip(gdf["name"], gdf.geometry):
        x0, y0, x1, y1 = shapely.bounds(geom).tolist()
        idx.append([name, round(x0, 4), round(y0, 4),
                    round(x1, 4), round(y1, 4)])
    idx.sort()
    n = write_json(os.path.join(OUT, f"{grain}_index.json"), idx)
    print(f"  {grain}_index.json {n / 1e3:.0f} KB, {len(idx):,} names",
          flush=True)
    return pm


def check_tile_sizes(path):
    """No tile may have been re-encoded at reduced resolution."""
    from pmtiles.reader import MmapSource, all_tiles
    with open(path, "rb") as f:
        worst = n = 0
        for _, data in all_tiles(MmapSource(f)):
            worst = max(worst, len(data))
            n += 1
    if worst > MAX_TILE_BYTES:
        raise SystemExit(f"{path}: a tile is {worst:,} bytes, over the "
                         f"{MAX_TILE_BYTES:,} cap - GDAL will have dropped "
                         f"resolution to fit it")
    print(f"  {n:,} tiles, largest {worst / 1e3:.0f} KB, under the "
          f"{MAX_TILE_BYTES / 1e6:.0f} MB cap", flush=True)


def main():
    template = read("map", "template.html")
    all_cols = columns_read_by_template(template)
    tile_cols = tile_columns(template)
    for g in GRAINS:
        pm = build(g["grain"], g["source"], tile_cols, all_cols)
        check_tile_sizes(pm)


if __name__ == "__main__":
    main()
