"""Derive postcode-SECTOR polygons for GB — the geography nobody publishes.

Only Scotland has official sector boundaries; England & Wales publish
lookups, not polygons (DATA_SOURCES.md dead-ends). But a sector is by
definition a district plus one inward digit ("YO25 6" ⊂ YO25), so
sectors NEST inside districts — and that turns the problem into 2,736
small independent ones:

  for each modelled district:
    take its own unit-postcode centroids (Code-Point Open, #23),
    Voronoi-partition them, clip to the district polygon,
    dissolve the cells by sector digit.

The result is exactly a partition of each district (the validation
asserts it), using only open data. This is the TRACER for sector-level
modelling: it proves the geometry exists and measures its size. It does
NOT feed the model — re-rasterising every hazard over ~11k sectors is a
separate, larger decision.

Checkpointed per district batch (this machine sleeps mid-run) — rerun
to resume, delete data/cache/sectors.checkpoint.pkl to restart.

Output: data/sectors_gb.gpkg (EPSG:27700; sector, district, n_units).
"""

import os
import pickle
import sys
import zipfile
from collections import defaultdict

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import load_districts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CPO = os.path.join(ROOT, "data", "cache", "codepoint_open.zip")
CHECKPOINT = os.path.join(ROOT, "data", "cache", "sectors.checkpoint.pkl")
OUT = os.path.join(ROOT, "data", "sectors_gb.gpkg")

# How much of a district's area its sector union may miss before the
# run refuses. Clipped Voronoi cells partition the polygon exactly, so
# anything beyond float slack means the method broke.
MAX_AREA_MISS = 1e-6


def load_points():
    """outward district -> list of (sector_digit, x, y) from Code-Point.

    Headerless CSVs (DATA_SOURCES #23): column 0 = padded postcode,
    1 = quality (90 means no coordinates - drop), 2 = easting,
    3 = northing. Inward code is always the last three characters of the
    de-padded postcode; the sector digit is its first character.
    """
    by_district = defaultdict(list)
    n_total = n_dropped = 0
    with zipfile.ZipFile(CPO) as zf:
        for name in sorted(zf.namelist()):
            if not (name.startswith("Data/CSV/") and name.endswith(".csv")):
                continue
            with zf.open(name) as fh:
                for raw in fh:
                    parts = raw.decode("ascii", "replace").split(",")
                    n_total += 1
                    if len(parts) < 4:
                        n_dropped += 1
                        continue
                    if parts[1].strip('"') == "90":
                        n_dropped += 1          # positional-only: no coords
                        continue
                    pc = parts[0].strip('"').replace(" ", "")
                    if len(pc) < 5:
                        n_dropped += 1
                        continue
                    outward, inward = pc[:-3], pc[-3:]
                    try:
                        x, y = float(parts[2]), float(parts[3])
                    except ValueError:
                        n_dropped += 1
                        continue
                    by_district[outward].append((inward[0], x, y))
    print(f"{n_total:,} postcodes, {n_dropped:,} dropped "
          f"(quality 90 / malformed), {len(by_district):,} districts",
          flush=True)
    return by_district


def sectors_for_district(geom, entries):
    """[(sector_digit, n_units, polygon)] partitioning `geom`.

    Voronoi over the district's own centroids, clipped to the district,
    dissolved by digit. Duplicate coordinates (vertical streets, PO box
    banks) collapse to one seed - the digit that appears most at that
    coordinate wins the cell.
    """
    # dedupe seeds; majority digit per coordinate
    at = defaultdict(list)
    for digit, x, y in entries:
        at[(x, y)].append(digit)
    coords = list(at)
    digits = [max(set(ds), key=ds.count) for ds in at.values()]
    counts = defaultdict(int)
    for digit, _x, _y in entries:
        counts[digit] += 1

    if len({d for d in digits}) == 1:
        # single sector: its polygon IS the district - no Voronoi needed
        return [(digits[0], sum(counts.values()), geom)]

    seeds = shapely.points([c[0] for c in coords], [c[1] for c in coords])
    cells = shapely.voronoi_polygons(
        shapely.multipoints(seeds), extend_to=geom, ordered=True)
    merged = defaultdict(list)
    for digit, cell in zip(digits, shapely.get_parts(cells)):
        merged[digit].append(cell)
    out = []
    for digit, cell_list in sorted(merged.items()):
        poly = shapely.intersection(shapely.union_all(cell_list), geom)
        if not shapely.is_empty(poly):
            out.append((digit, counts[digit], shapely.make_valid(poly)))
    return out


def main():
    import geopandas as gpd

    districts = load_districts().to_crs(27700)
    by_district = load_points()

    done = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "rb") as fh:
            done = pickle.load(fh)
        print(f"resuming: {len(done)} districts in checkpoint", flush=True)

    misses = []
    todo = [t for t in districts.itertuples() if t.name not in done]
    for i, t in enumerate(todo):
        entries = by_district.get(t.name)
        if not entries:
            done[t.name] = []          # modelled district with no live
            misses.append(t.name)      # postcodes (rare; report it)
            continue
        rows = sectors_for_district(t.geometry, entries)
        union = shapely.union_all([g for _d, _n, g in rows])
        miss = 1 - union.area / t.geometry.area if t.geometry.area else 0
        if miss > MAX_AREA_MISS:
            raise SystemExit(
                f"{t.name}: sector union misses {miss:.2e} of the district "
                f"- the partition broke, refusing to continue")
        done[t.name] = [(d, n, shapely.to_wkb(g)) for d, n, g in rows]
        if (i + 1) % 200 == 0:
            with open(CHECKPOINT, "wb") as fh:
                pickle.dump(done, fh)
            print(f"  {len(done)}/{len(districts)} districts", flush=True)

    with open(CHECKPOINT, "wb") as fh:
        pickle.dump(done, fh)
    if misses:
        print(f"{len(misses)} modelled districts have no Code-Point "
              f"postcodes: {misses[:10]}", flush=True)

    names, sectors, units, geoms = [], [], [], []
    for district, rows in sorted(done.items()):
        for digit, n, wkb in rows:
            names.append(district)
            sectors.append(f"{district} {digit}")
            units.append(n)
            geoms.append(shapely.from_wkb(wkb))
    gdf = gpd.GeoDataFrame(
        {"sector": sectors, "district": names, "n_units": units},
        geometry=geoms, crs=27700)
    gdf.to_file(OUT, driver="GPKG")
    print(f"wrote {OUT}: {len(gdf):,} sectors over "
          f"{gdf['district'].nunique():,} districts "
          f"({os.path.getsize(OUT) / 1e6:.0f} MB)", flush=True)
    print(f"sectors per district: min {gdf.groupby('district').size().min()}"
          f" median {int(gdf.groupby('district').size().median())}"
          f" max {gdf.groupby('district').size().max()}", flush=True)


if __name__ == "__main__":
    main()
