"""Postcode sector and district polygons for the UK, built bottom-up.

WHAT IS WRONG WITH THE GEOMETRY WE PUBLISH TODAY. Districts come from
missinglink/uk-postcode-polygons (#1) - a third-party set the data table
itself describes as "OS/Wikipedia-derived", GB only. Sectors come from
derive_sectors.py, which Voronoi-partitions Code-Point Open centroids
and CLIPS THEM TO THOSE DISTRICT POLYGONS. So the two grains are not
independent: every district boundary error is inherited exactly by the
sectors inside it, and the sector layer cannot be more accurate than the
district layer it was cut out of.

Building bottom-up inverts that dependency and fixes both grains at
once:

    1.8 M unit postcodes  ->  Voronoi  ->  dissolve by sector digit
                                       ->  dissolve by district

A district is then, by construction, exactly the union of its sectors,
and both are derived from the same authoritative centroids rather than
from a third-party outline. Postcode codes make this sound: "BT1 1" is
by definition inside "BT1", so the dissolve is a pure grouping with no
geometric decision in it.

WHY VORONOI IS THE RIGHT SHAPE. Royal Mail does not publish postcode
boundaries - they do not exist as polygons, only as sets of delivery
points. Every published "postcode boundary" is somebody's interpolation
of those points, and nearest-centroid (Voronoi) is the standard one:
each piece of ground is assigned to the postcode whose delivery points
are closest. It is an inference, not a measurement, and it is weakest
where delivery points are sparse - upland Scotland, mid-Wales - which is
also where households are fewest and the model cares least.

COASTLINE. Raw Voronoi cells run to infinity, and coastal ones run out
to sea, so a coastal sector would claim tens of km2 of water and its
per-hectare quantities would be wrong. Cells are therefore clipped to
the ONS full-resolution UK coastline (BFC, December 2025). Only sectors
whose envelope actually meets the coast are intersected - inland sectors
pass through untouched, which is what makes a full-resolution clip
affordable over 10,645 sectors rather than the "tens of minutes"
fetch_countries.py records for the same boundary against 2,736.

NORTHERN IRELAND. This is what lets NI exist at all: it adds 80
districts and 247 sectors that no GB-only source could supply. See
fetch_onspd.py for the Irish Grid trap that has to be avoided to get
their coordinates right.

Output: data/sectors_uk.gpkg    (sector, district, area, country, n_units)
        data/districts_uk.gpkg  (name, area, country, n_units, n_sectors)
        data/districts_uk.geojson  (EPSG:4326, drop-in for load_districts)

Usage:
  build_postcode_polygons.py
  build_postcode_polygons.py --no-clip     # skip the coastline (faster, for
                                           # checking the Voronoi alone)
"""

import argparse
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
COAST = os.path.join(CACHE, "uk_coastline_bfc.geojson")
LAND_WKB = os.path.join(CACHE, "uk_land.wkb")
OUT_SEC = os.path.join(DATA, "sectors_uk.gpkg")
OUT_DIS = os.path.join(DATA, "districts_uk.gpkg")
OUT_DIS_JSON = os.path.join(DATA, "districts_uk.geojson")

SERVICE = ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/"
           "services/Countries_December_2025_Boundaries_UK_BFC"
           "/FeatureServer/0/query")

# GDAL refuses oversized GeoJSON features unless told not to; the
# full-resolution England polygon is well over the default limit.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

# Voronoi cells are unbounded at the hull. extend_to gives GEOS a box to
# close them against; the coastline clip then does the real work. Well
# outside the UK so no cell is truncated by the box itself.
VORONOI_BOX = (-400_000, -200_000, 1_000_000, 1_500_000)


def land_polygon():
    """The UK land mass as one geometry, cached in binary.

    The GeoJSON is 118 MB and takes ~32 s to parse before a union that
    costs more again, every run. The result is a fixed 4.5 M-coordinate
    polygon, so it is cached as WKB and read back in about a second.
    """
    import shapely

    if os.path.exists(LAND_WKB):
        with open(LAND_WKB, "rb") as fh:
            print("  coastline: cached (wkb)", flush=True)
            return shapely.from_wkb(fh.read())
    coast = fetch_coastline()
    land = shapely.make_valid(shapely.unary_union(coast.geometry.values))
    with open(LAND_WKB, "wb") as fh:
        fh.write(shapely.to_wkb(land))
    print(f"  coastline: {shapely.get_num_coordinates(land):,} coordinates "
          f"(full resolution)", flush=True)
    return land


def fetch_coastline():
    import geopandas as gpd

    if os.path.exists(COAST):
        print(f"  coastline: cached ({os.path.getsize(COAST) / 1e6:.0f} MB)",
              flush=True)
        return gpd.read_file(COAST).to_crs(27700)
    q = dict(where="1=1", outFields="CTRY25NM", outSR=27700, f="geojson",
             returnGeometry="true")
    url = SERVICE + "?" + urllib.parse.urlencode(q)
    print("  fetching full-resolution UK coastline (~130 MB)...", flush=True)
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "uk-risk-map/1.0"})
    part = COAST + ".partial"
    with urllib.request.urlopen(req, timeout=900) as r, open(part, "wb") as fh:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            fh.write(b)
    os.replace(part, COAST)
    print(f"  done in {time.time() - t0:.0f}s "
          f"({os.path.getsize(COAST) / 1e6:.0f} MB)", flush=True)
    return gpd.read_file(COAST).to_crs(27700)


def load_centroids():
    import pandas as pd

    if not os.path.exists(CENTROIDS):
        raise SystemExit(
            f"{CENTROIDS} missing - run scripts/fetch_onspd.py first.")
    df = pd.read_csv(CENTROIDS)
    print(f"  {len(df):,} postcodes  "
          f"({df['district'].nunique():,} districts, "
          f"{df['sector'].nunique():,} sectors, "
          f"{df['country'].nunique()} countries)", flush=True)
    return df


def dissolve_by(geoms, keys):
    """unary_union of geoms grouped by keys. Returns (labels, unions)."""
    import shapely

    order = np.argsort(keys, kind="stable")
    ks = np.asarray(keys)[order]
    gs = np.asarray(geoms, dtype=object)[order]
    # boundaries between runs of equal key
    cuts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1], True])
    labels, unions = [], []
    n = len(cuts) - 1
    for i in range(n):
        a, b = cuts[i], cuts[i + 1]
        labels.append(ks[a])
        unions.append(shapely.unary_union(gs[a:b]))
        if (i + 1) % 2000 == 0:
            print(f"     dissolved {i + 1:,}/{n:,}", flush=True)
    return labels, unions


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-clip", action="store_true",
                    help="skip the coastline clip")
    args = ap.parse_args()

    import geopandas as gpd
    import pandas as pd
    import shapely

    t0 = time.time()
    df = load_centroids()

    # COINCIDENT POSTCODES. Voronoi cannot divide ground between two
    # points in the same place, and GEOS refuses outright ("Multiple
    # input coordinates in cell") rather than guessing. Excluding large
    # users already removed the pathological clusters - the worst
    # remaining is 90 postcodes, against 1,162 with them in - but a
    # residual 8,280 coordinates still carry more than one postcode,
    # typically flats in one block sharing a delivery point.
    #
    # First-wins is the honest resolution: those postcodes genuinely
    # occupy the same ground and there is no evidence available to split
    # it. Only the GEOMETRY is deduplicated; n_units below is counted
    # from the full set, so a block of flats still carries its true
    # weight even though it contributes one cell.
    n_all = len(df)
    _, keep = np.unique(df[["easting", "northing"]].to_numpy(), axis=0,
                        return_index=True)
    dfu = df.iloc[np.sort(keep)].reset_index(drop=True)
    dropped = set(df["sector"]) - set(dfu["sector"])
    print(f"  {n_all - len(dfu):,} coincident postcodes merged for geometry "
          f"({len(dfu):,} distinct locations)", flush=True)
    if dropped:
        # A sector every one of whose postcodes shares a location with
        # some other sector has no ground of its own to draw.
        print(f"  {len(dropped)} sectors have no distinct location and get "
              f"no polygon: {sorted(dropped)[:6]}"
              f"{' ...' if len(dropped) > 6 else ''}", flush=True)

    print("  building Voronoi over every distinct location...", flush=True)
    t = time.time()
    pts = shapely.points(dfu["easting"].to_numpy(), dfu["northing"].to_numpy())
    cells = shapely.get_parts(shapely.voronoi_polygons(
        shapely.multipoints(pts), extend_to=shapely.box(*VORONOI_BOX),
        ordered=True))
    if len(cells) != len(dfu):
        raise SystemExit(
            f"Voronoi returned {len(cells):,} cells for {len(dfu):,} points. "
            f"ordered=True should make these equal; without that guarantee "
            f"cells cannot be matched back to postcodes. Nothing written.")
    print(f"     {len(cells):,} cells in {time.time() - t:.0f}s", flush=True)

    print("  dissolving cells into sectors...", flush=True)
    t = time.time()
    sec_keys, sec_geoms = dissolve_by(cells, dfu["sector"].to_numpy())
    print(f"     {len(sec_keys):,} sectors in {time.time() - t:.0f}s",
          flush=True)

    sec = gpd.GeoDataFrame(
        {"sector": sec_keys}, geometry=list(sec_geoms), crs=27700)
    meta = (df.groupby("sector")
              .agg(district=("district", "first"), area=("area", "first"),
                   country=("country", "first"), n_units=("postcode", "size"))
              .reset_index())
    sec = sec.merge(meta, on="sector", how="left")

    if not args.no_clip:
        land = land_polygon()
        # WHY NOT JUST INTERSECT EVERYTHING. Measured: one intersection
        # against the 4.47 M-coordinate full-resolution coastline costs
        # 690 ms, so clipping all 9,834 sectors takes 113 minutes.
        # Simplifying the coastline to 10 m would cut that to 12 min, but
        # this rebuild exists to make the geometry MORE accurate and the
        # coastline is the one boundary where full resolution shows.
        #
        # The saving is that most sectors are nowhere near the sea. An
        # STRtree over the coastline does NOT find them - the boundary of
        # Great Britain is a single ring whose bounding box covers the
        # whole island, so every mainland sector "hits" it and nothing is
        # filtered. That was the first attempt and it clipped nothing in
        # 46 minutes.
        #
        # shapely.prepare() is the right tool: it builds an internal
        # segment index once, after which contains_properly() answers
        # "wholly inland?" in microseconds. Inland sectors are then
        # returned untouched and only the coastal minority pays the
        # 690 ms.
        print("  clipping coastal sectors to the coastline...", flush=True)
        t = time.time()
        shapely.prepare(land)
        geoms = sec.geometry.values
        out, touched = [], 0
        for i, g in enumerate(geoms):
            if shapely.contains_properly(land, g):
                out.append(g)                       # wholly inland
            else:
                out.append(shapely.intersection(g, land))
                touched += 1
            if (i + 1) % 2000 == 0:
                print(f"     {i + 1:,}/{len(geoms):,} "
                      f"({touched:,} clipped so far)", flush=True)
        sec["geometry"] = out
        print(f"     {touched:,} of {len(geoms):,} sectors met the coast, "
              f"{time.time() - t:.0f}s", flush=True)

    sec["geometry"] = shapely.make_valid(sec.geometry.values)
    sec = sec[~shapely.is_empty(sec.geometry.values)].reset_index(drop=True)

    print("  dissolving sectors into districts...", flush=True)
    dis_keys, dis_geoms = dissolve_by(sec.geometry.values,
                                      sec["district"].to_numpy())
    dis = gpd.GeoDataFrame(
        {"name": dis_keys}, geometry=list(dis_geoms), crs=27700)
    dmeta = (sec.groupby("district")
                .agg(area=("area", "first"), country=("country", "first"),
                     n_units=("n_units", "sum"), n_sectors=("sector", "size"))
                .reset_index().rename(columns={"district": "name"}))
    dis = dis.merge(dmeta, on="name", how="left")

    validate(sec, dis, clipped=not args.no_clip)

    sec.to_file(OUT_SEC, driver="GPKG")
    dis.to_file(OUT_DIS, driver="GPKG")
    dis.to_crs(4326).to_file(OUT_DIS_JSON, driver="GeoJSON")
    print(f"  wrote {OUT_SEC}")
    print(f"  wrote {OUT_DIS}")
    print(f"  wrote {OUT_DIS_JSON}")
    print(f"  total {time.time() - t0:.0f}s")


def validate(sec, dis, clipped=True):
    """Cheap invariants that would catch a silently wrong build."""
    import shapely

    print("  validating...", flush=True)
    sa = shapely.area(sec.geometry.values).sum() / 1e6
    da = shapely.area(dis.geometry.values).sum() / 1e6
    print(f"     sectors  {len(sec):,}  {sa:,.0f} km2")
    print(f"     districts{len(dis):>7,}  {da:,.0f} km2")

    # Districts are the union of their sectors, so the areas must match.
    # Anything else means the dissolve lost or double-counted geometry.
    if abs(sa - da) / max(sa, 1) > 0.001:
        raise SystemExit(
            f"district area {da:,.0f} km2 != sector area {sa:,.0f} km2. "
            f"The two grains have diverged; they are built from the same "
            f"cells so this cannot happen by rounding.")

    # UK land area is about 242,500 km2. A Voronoi that escaped to sea or
    # a clip that ate the country would both show up here. Unclipped
    # cells cover the whole extend_to box, so this only means anything
    # once the coastline has been applied.
    if clipped and not (200_000 < da < 260_000):
        raise SystemExit(
            f"total area {da:,.0f} km2 is not plausible for the UK "
            f"(~242,500 km2). Check the coastline clip.")
    if not clipped:
        print("     --no-clip: area check skipped (cells still run to sea)")

    by_ctry = dis.groupby("country").size().to_dict()
    for c in sorted(by_ctry, key=lambda k: -by_ctry[k]):
        print(f"     {c:<18}{by_ctry[c]:>6,} districts")
    if "Northern Ireland" not in by_ctry:
        raise SystemExit("no Northern Ireland districts - the whole point "
                         "of this rebuild is missing.")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
