"""Assign each postcode district to a country (England / Wales / Scotland).

Several of the hazard datasets are England-only - the EA's surface-water
depth bands, its NCERM coastal erosion mapping, and its climate-change
flood extents all stop at the border, while NRW and SEPA cover Wales and
Scotland with different products or none at all.

Without a country mask that asymmetry is silently wrong in a way that
looks plausible:

  * a Welsh district has real surface water (from NRW) but zero EA depth,
    which reads as "none of its flooding exceeds 0.2 m" - the shallowest
    possible severity;
  * Dundee's present-day flood fraction is 70% and its EA climate-change
    fraction is 0%, which reads as a 70-point *fall* in flood risk under
    climate change;
  * border districts that clip a few hundred metres into England pick up a
    sliver of English data and look like real observations.

Postcode areas do not solve it - SY and CH genuinely straddle the border -
so this takes the actual boundary. Each district is assigned the country
holding the majority of its area, and the share is kept so partial cases
stay visible.

Source: ONS Open Geography Portal, Countries (December 2021) GB BFC,
Open Government Licence.

Output: data/country.csv  (name, country, share)

Usage:
    python scripts/fetch_countries.py
"""

import csv
import json
import os
import sys
import urllib.parse
import urllib.request

import geopandas as gpd
import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import load_districts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
OUT = os.path.join(DATA, "country.csv")

# BGC = generalised, clipped to coastline. The BFC (full-resolution)
# edition of the same boundary is 133 MB and its single England feature
# exceeds GDAL's default GeoJSON object-size limit, which is a needless
# fight for a question answered at kilometre scale.
SERVICE = ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/"
           "services/Countries_December_2025_Boundaries_UK_BGC"
           "/FeatureServer/0/query")

# A previously cached full-resolution download is still usable, but GDAL
# refuses oversized GeoJSON features unless told otherwise.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")


# The ONS "BFC" boundary is full-resolution coastline - 133 MB, and
# intersecting it against 2,700 districts takes tens of minutes. Deciding
# which country a district sits in does not need metre-accurate coastline,
# so it is simplified once and the simplified version cached. 200 m is far
# below the scale of a postcode district and well below the width of any
# land border.
SIMPLIFY_M = 200.0


def fetch_countries():
    cache = os.path.join(CACHE, "gb_countries_simplified.geojson")
    if os.path.exists(cache):
        print("  countries: cached (simplified)", flush=True)
        return gpd.read_file(cache)

    raw = os.path.join(CACHE, "gb_countries.geojson")
    if os.path.exists(raw):
        print(f"  countries: simplifying cached full-resolution boundary "
              f"({os.path.getsize(raw) / 1e6:.0f} MB)...", flush=True)
        gdf = gpd.read_file(raw)
        if gdf.crs is None:
            gdf = gdf.set_crs(27700)
        gdf = gdf.to_crs(27700)
        gdf["geometry"] = shapely.make_valid(
            shapely.simplify(gdf.geometry.values, SIMPLIFY_M))
        gdf.to_file(cache, driver="GeoJSON")
        print(f"  -> {os.path.getsize(cache) / 1e6:.1f} MB", flush=True)
        return gdf

    q = dict(where="1=1", outFields="*", outSR=27700, f="geojson",
             returnGeometry="true")
    url = SERVICE + "?" + urllib.parse.urlencode(q)
    print(f"  fetching {url[:90]}...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "uk-risk-map"})
    with urllib.request.urlopen(req, timeout=300) as r:
        gj = json.loads(r.read().decode("utf-8", "replace"))
    gdf = gpd.GeoDataFrame.from_features(gj["features"])
    if gdf.empty:
        raise RuntimeError("countries service returned nothing")

    # Same CRS vigilance as elsewhere in this project: asking for 27700
    # does not guarantee getting it.
    xs = shapely.get_coordinates(gdf.geometry.values)[:, 0]
    lo, hi = float(np.nanmin(xs)), float(np.nanmax(xs))
    if -12.0 <= lo and hi <= 3.0:
        print(f"    coords look like lon/lat -> tagging 4326", flush=True)
        gdf = gdf.set_crs(4326).to_crs(27700)
    else:
        print(f"    coords look like BNG (x in [{lo:.0f}, {hi:.0f}])", flush=True)
        gdf = gdf.set_crs(27700, allow_override=True)
    gdf["geometry"] = shapely.make_valid(
        shapely.simplify(gdf.geometry.values, SIMPLIFY_M))
    os.makedirs(CACHE, exist_ok=True)
    gdf.to_file(cache, driver="GeoJSON")
    return gdf


def name_field(gdf):
    for c in gdf.columns:
        if c.upper().startswith("CTRY") and c.upper().endswith("NM"):
            return c
    for c in gdf.columns:
        if gdf[c].dtype == object and gdf[c].astype(str).str.contains(
                "England", case=False, na=False).any():
            return c
    raise RuntimeError(f"no country-name column in {list(gdf.columns)}")


def main():
    print("fetching GB country boundaries...", flush=True)
    ctry = fetch_countries()
    fld = name_field(ctry)
    print(f"  country name field: {fld} -> {sorted(ctry[fld].unique())}",
          flush=True)

    print("loading districts...", flush=True)
    d = load_districts().to_crs(27700)
    names = d["name"].values
    geoms = d.geometry.values
    area = shapely.area(geoms)

    countries = sorted(ctry[fld].unique())
    cgeom = {c: shapely.union_all(ctry.loc[ctry[fld] == c, "geometry"].values)
             for c in countries}

    # Most districts sit wholly inside one country, so decide those with a
    # cheap point-in-polygon and only pay for area intersection on the ones
    # that actually straddle a border. Doing it the other way round means
    # intersecting every district against a national polygon, which is what
    # made the first version take tens of minutes.
    share = np.zeros((len(d), len(countries)))
    pts = shapely.point_on_surface(geoms)
    inside = np.full(len(d), -1)
    for j, c in enumerate(countries):
        hit = shapely.STRtree([cgeom[c]]).query(pts, predicate="within")
        inside[hit[0]] = j

    straddlers = []
    for i in range(len(d)):
        touching = [j for j, c in enumerate(countries)
                    if shapely.intersects(geoms[i], cgeom[c])]
        if len(touching) == 1:
            share[i, touching[0]] = area[i]
        else:
            straddlers.append((i, touching))
    print(f"  {len(straddlers)} districts touch more than one country - "
          f"computing exact area shares for those", flush=True)
    for i, touching in straddlers:
        for j in touching:
            share[i, j] = shapely.area(
                shapely.intersection(geoms[i], cgeom[countries[j]]))

    best = share.argmax(axis=1)
    # fall back to the point test where a district somehow has no area
    # attributed (slivers, or a district entirely offshore of the boundary)
    empty = share.sum(axis=1) <= 0
    best[empty] = np.where(inside[empty] >= 0, inside[empty], best[empty])
    frac = share.max(axis=1) / np.maximum(area, 1e-9)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "country", "share"])
        for i in range(len(d)):
            w.writerow([names[i], countries[best[i]], round(float(frac[i]), 4)])
    print(f"wrote {OUT}", flush=True)

    for j, c in enumerate(countries):
        n = int((best == j).sum())
        print(f"  {c}: {n} districts")
    # districts that genuinely straddle are worth naming - they are the
    # ones where an England-only dataset gives a partial reading
    straddle = [(names[i], countries[best[i]], frac[i])
                for i in range(len(d)) if frac[i] < 0.95]
    straddle.sort(key=lambda t: t[2])
    print(f"  straddling the border (<95% in one country): {len(straddle)}")
    for nm, c, f in straddle[:12]:
        print(f"    {nm:6s} {c:9s} {100 * f:5.1f}%")


if __name__ == "__main__":
    main()
