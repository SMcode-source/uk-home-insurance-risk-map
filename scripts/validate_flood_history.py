"""Observed river/sea flooding by RoFRS band: the anchor for RS_FREQ_TOP.

The EA's Recorded Flood Outlines (OGL, England, events since 1946) are
overlaid on the unit-postcode centroids the model's flood fractions are
read at. For each postcode, distinct flood EVENTS (distinct start dates:
one flood is often several outlines) are counted in a window, and each
band's rate is household-weighted events per home-year, the same basis
as the fractions since 2026-09-28.

Only ratios between bands are used. The recorded rates sit far below the
band definitions (Medium, 1-3.3% a year by definition, records about
0.3%), because not every flood is recorded and an outline is not a
flooded home; the ratio assumes recording completeness does not depend
on the band. Records are river and sea only (flood_src main river,
ordinary watercourse or sea; cause not surface water or groundwater).

    python scripts/validate_flood_history.py

Needs data/cache/flood_postcode_flags.csv (fetch_flood_postcodes.py) and
fetches the outlines (~84 MB zip) into data/cache on first run.
"""
import os
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_flood_postcodes as fp  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
RFO_ZIP = os.path.join(CACHE, "Recorded_Flood_Outlines.gpkg.zip")
RFO_URL = ("https://environment.data.gov.uk/api/file/download?fileDataSetId="
           "ed73f2e8-a3c2-44db-952d-6e359c7c3987"
           "&fileName=Recorded_Flood_Outlines.gpkg.zip")
FLAGS = os.path.join(CACHE, "flood_postcode_flags.csv")
RS_SRC = {"main river", "ordinary watercourse", "sea"}
SW_GW = {"local drainage/surface water", "groundwater/high water table"}
WINDOWS = [(1990, 2025), (2000, 2025), (2007, 2025)]
N_BOOT = 1000


def outlines():
    import pyogrio
    if not os.path.exists(RFO_ZIP):
        print(f"  downloading {RFO_URL}", flush=True)
        req = urllib.request.Request(
            RFO_URL, headers={"User-Agent": "Mozilla/5.0 (uk-risk-map)"})
        with urllib.request.urlopen(req, timeout=600) as r, \
                open(RFO_ZIP + ".part", "wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk)
        os.replace(RFO_ZIP + ".part", RFO_ZIP)
    gpkg = os.path.join(CACHE, "Recorded_Flood_Outlines.gpkg")
    if not os.path.exists(gpkg):
        with zipfile.ZipFile(RFO_ZIP) as z:
            z.extract("Recorded_Flood_Outlines.gpkg", CACHE)
    rfo = pyogrio.read_dataframe(gpkg)
    rfo["date"] = pd.to_datetime(rfo.start_date, errors="coerce").dt.normalize()
    keep = rfo.flood_src.isin(RS_SRC) & ~rfo.flood_caus.isin(SW_GW)
    print(f"  {len(rfo):,} outlines, {int(keep.sum()):,} river/sea", flush=True)
    return rfo[keep].reset_index(drop=True)


def postcodes():
    flags = pd.read_csv(FLAGS)
    cen = pd.read_csv(os.path.join(DATA, "postcode_centroids.csv"),
                      usecols=["postcode", "district", "easting", "northing"])
    pc = flags[flags.country == "England"].merge(cen, on="postcode")
    pc = pc.dropna(subset=["easting", "northing"]).reset_index(drop=True)
    pc["hh"] = fp.postcode_households(pc["postcode"])
    pc["band"] = np.select([pc.in_top > 0, pc.in_high > 0, pc.in_low > 0],
                           ["High", "Medium", "Low"], "None")
    return pc


def band_rates(hits, W):
    """Household-weighted events per home, by band."""
    return hits.groupby("band").hh.sum().reindex(W.index, fill_value=0) / W


def main():
    import geopandas as gpd
    import shapely
    pc = postcodes()
    rfo = outlines()
    bad = ~shapely.is_valid(rfo.geometry.values)
    rfo.loc[bad, "geometry"] = shapely.make_valid(rfo.geometry.values[bad])
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(pc.easting, pc.northing),
                           crs=27700)
    j = gpd.sjoin(pts, rfo[["geometry"]], predicate="within")
    hits = pd.DataFrame({"i": j.index.values,
                         "date": rfo.date.values[j.index_right.values]})
    hits = hits.drop_duplicates()              # one event per postcode per date
    hits["band"] = pc.band.values[hits.i]
    hits["hh"] = pc.hh.values[hits.i]
    hits["district"] = pc.district.values[hits.i]
    W = pc.groupby("band").hh.sum()
    print("\nhouseholds by band:", W.round(0).astype(int).to_dict())

    rng = np.random.default_rng(1)
    pc_w = pc.groupby(["district", "band"]).hh.sum().unstack(fill_value=0)
    print("\nwindow      High/yr  Medium/yr  Low/yr   H/M   M/L   "
          "H/M 90% (events)  H/M 90% (districts)")
    for y0, y1 in WINDOWS:
        h = hits[hits.date.dt.year.between(y0, y1)]
        r = band_rates(h, W) / (y1 - y0 + 1)
        hm, ml = r["High"] / r["Medium"], r["Medium"] / r["Low"]
        by_date = [g for _, g in h.groupby("date")]
        ev = []
        for _ in range(N_BOOT):
            q = band_rates(pd.concat([by_date[k] for k in
                                      rng.integers(0, len(by_date), len(by_date))]), W)
            ev.append(q["High"] / q["Medium"])
        e_d = (h.groupby(["district", "band"]).hh.sum().unstack(fill_value=0)
               .reindex(index=pc_w.index, columns=pc_w.columns, fill_value=0))
        di = []
        for _ in range(N_BOOT):
            k = rng.integers(0, len(pc_w), len(pc_w))
            q = e_d.iloc[k].sum() / pc_w.iloc[k].sum()
            di.append(q["High"] / q["Medium"])
        p = lambda a: "%.2f-%.2f" % tuple(np.percentile(a, [5, 95]))
        print(f"{y0}-{y1}  {100 * r['High']:.3f}%   {100 * r['Medium']:.3f}%   "
              f"{100 * r['Low']:.3f}%  {hm:.2f}  {ml:.2f}   {p(ev):>14}   {p(di):>14}"
              f"   ({len(by_date)} events)")


if __name__ == "__main__":
    main()
