"""The model's first external validation: flood ORDERING outside England.

LIMITATIONS §2 has said since it was written that no peril's ordering
has ever been checked against anything not derived from the model's own
inputs. The 2026-09-03 availability sweep found two open products that
can do that for flood, and only for flood, and only outside England:

  SEPA  NFRA Flood Risk Grid - 26,614 polygon cells, `aad_score_res`
        band 1..7 (residential annual-average-damage score).
  NRW   National Flood Risk Assessment for Wales - per-community
        polygons with people at low/medium/high risk, one layer each
        for rivers, sea and surface water.

Both are CONSEQUENCE products with frequency already inside them, so
they cannot be severity multipliers (that would double-count the ABI
calibration). What they can be is an independent ranking. This script
allocates each onto districts by geometric area share, then reports the
Spearman rank correlation with the model's `el_fl` and its components,
per country. It writes data/flood_validation.csv and changes nothing
the model reads.

Fetches are cached under data/cache/. Run from a laptop:

    .venv/Scripts/python.exe -u scripts/validate_flood_ordering.py
"""
import json
import os
import time
import urllib.parse
import urllib.request

import geopandas as gpd
import numpy as np
import shapely
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
os.makedirs(CACHE, exist_ok=True)

SEPA = ("https://map.sepa.org.uk/server/rest/services/Open/"
        "NFRA_Flood_Risk_Grid_Latest/MapServer/0/query")
NRW = "https://datamap.gov.wales/geoserver/ows"
NRW_LAYERS = {"river": "RIVER_PEOPLE", "sea": "SEA_PEOPLE",
              "sw": "SURFACE_WATER_PEOPLE"}
PAGE = 2000
MODEL_COLS = ("el_fl", "fl_score", "f_high", "sw_high")


def http_json(url, tries=4, timeout=300):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:                       # noqa: BLE001
            print(f"    retry {i + 1}: {e}", flush=True)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"gave up on {url[:90]}")


def cached(name, fetch):
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        print(f"  {name}: cached", flush=True)
        return gpd.read_file(path)
    feats = fetch()
    gdf = gpd.GeoDataFrame.from_features(feats)
    gdf = gdf[~gdf.geometry.isna()].copy()
    gdf = gdf.set_crs(27700, allow_override=True)
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    gdf.to_file(path, driver="GeoJSON")
    return gdf


def fetch_sepa():
    feats, offset = [], 0
    while True:
        q = dict(where="1=1", outFields="grid_id,aad_score_res",
                 returnGeometry="true", outSR=27700, f="geojson",
                 resultOffset=offset, resultRecordCount=PAGE)
        d = http_json(SEPA + "?" + urllib.parse.urlencode(q))
        if "error" in d:
            raise RuntimeError(d["error"])
        got = d.get("features", [])
        feats.extend(got)
        print(f"    sepa: {len(feats)} cells", flush=True)
        more = d.get("properties", {}).get("exceededTransferLimit", False)
        if not got or (len(got) < PAGE and not more):
            break
        offset += len(got)
    return feats


def fetch_nrw(layer):
    # One request, not pages: this GeoServer answers startIndex with a
    # 400 (paging wants a sortBy it does not advertise), and the largest
    # layer is 2,207 communities, so ask for everything and refuse a
    # reply that hits the ceiling rather than silently keep a subset.
    cap = 10000
    q = dict(service="WFS", version="2.0.0", request="GetFeature",
             typeNames=f"inspire-nrw:NRW_NATIONAL_FLOOD_RISK_{layer}",
             outputFormat="application/json", count=cap)
    d = http_json(NRW + "?" + urllib.parse.urlencode(q))
    got = d.get("features", [])
    print(f"    nrw {layer}: {len(got)} communities", flush=True)
    if len(got) >= cap:
        raise RuntimeError(f"{layer}: reply hit the {cap} feature ceiling")
    return got


def area_share_matrix(src, dst):
    """Rows = src polygons, cols = dst districts: area(src n dst)."""
    tree = shapely.STRtree(dst.geometry.values)
    s_idx, d_idx = tree.query(src.geometry.values, predicate="intersects")
    inter = shapely.area(shapely.intersection(src.geometry.values[s_idx],
                                              dst.geometry.values[d_idx]))
    m = np.zeros((len(src), len(dst)))
    np.add.at(m, (s_idx, d_idx), inter)
    return m


def spearman(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 8:
        return float("nan"), int(ok.sum())
    return float(stats.spearmanr(a[ok], b[ok]).statistic), int(ok.sum())


def main():
    gdf = gpd.read_file(os.path.join(DATA, "districts_risk.geojson"))
    gdf = gdf.to_crs(27700)
    gdf["d_area"] = gdf.geometry.area
    out = gdf[["name", "country", "households", *MODEL_COLS]].copy()

    # ---- Scotland: SEPA AAD band, area-weighted ----------------------
    scot = gdf[gdf["country"] == "Scotland"].reset_index(drop=True)
    is_scot = (out["country"] == "Scotland").values
    sepa = cached("sepa_nfra_grid.geojson", fetch_sepa)
    band = sepa["aad_score_res"].astype(float).values
    m = area_share_matrix(sepa, scot)                # cell x district
    scot_area = scot["d_area"].values
    cover = m.sum(axis=0) / scot_area
    out.loc[is_scot, "ext_aad_idx"] = (m * band[:, None]).sum(axis=0) / scot_area
    out.loc[is_scot, "ext_aad_high"] = \
        (m * (band >= 5)[:, None]).sum(axis=0) / scot_area
    print(f"  SEPA cells cover "
          f"{100 * np.average(cover, weights=scot_area):.1f}% of Scottish "
          f"district area", flush=True)

    # ---- Wales: NRW people at risk, allocated by community area share --
    wales = gdf[gdf["country"] == "Wales"].reset_index(drop=True)
    is_wales = (out["country"] == "Wales").values
    hh = np.maximum(wales["households"].values.astype(float), 1.0)
    tot_mh = np.zeros(len(wales))
    tot_h = np.zeros(len(wales))
    for key, layer in NRW_LAYERS.items():
        nrw = cached(f"nrw_nfra_{key}.geojson", lambda: fetch_nrw(layer))
        med = nrw["number_of_people_at_medium_risk"].astype(float).values
        hi = nrw["number_of_people_at_high_risk"].astype(float).values
        m = area_share_matrix(nrw, wales)
        share = m / np.maximum(nrw.geometry.area.values, 1.0)[:, None]
        mh = (share * (med + hi)[:, None]).sum(axis=0)
        h = (share * hi[:, None]).sum(axis=0)
        out.loc[is_wales, f"ext_{key}_mh_per_hh"] = mh / hh
        tot_mh += mh
        tot_h += h
    out.loc[is_wales, "ext_people_mh_per_hh"] = tot_mh / hh
    out.loc[is_wales, "ext_people_h_per_hh"] = tot_h / hh

    # ---- the comparison --------------------------------------------
    print("\n  Spearman rank correlation, external measure vs model")
    print(f"  {'country':<9}{'external':<24}{'model':<10}{'rho':>7}{'n':>6}")
    for country, ext_cols in (
            ("Scotland", ["ext_aad_idx", "ext_aad_high"]),
            ("Wales", ["ext_people_mh_per_hh", "ext_people_h_per_hh",
                       "ext_river_mh_per_hh", "ext_sea_mh_per_hh",
                       "ext_sw_mh_per_hh"])):
        sub = out[out["country"] == country]
        for ec in ext_cols:
            for mc in MODEL_COLS:
                rho, n = spearman(sub[ec].values.astype(float),
                                  sub[mc].values.astype(float))
                print(f"  {country:<9}{ec:<24}{mc:<10}{rho:>7.3f}{n:>6}")

    for country, ec in (("Scotland", "ext_aad_idx"),
                        ("Wales", "ext_people_mh_per_hh")):
        sub = out[out["country"] == country].copy()
        sub["r_ext"] = sub[ec].rank()
        sub["r_mod"] = sub["el_fl"].rank()
        sub["gap"] = sub["r_ext"] - sub["r_mod"]
        order = sub["gap"].abs().sort_values(ascending=False).index
        print(f"\n  {country}: largest rank disagreements "
              f"(external rank - model rank, of {len(sub)})")
        for _, r in sub.reindex(order).head(6).iterrows():
            print(f"    {r['name']:<7} ext {r[ec]:.4g} (r{int(r['r_ext'])})  "
                  f"el_fl {r['el_fl']:.1f} (r{int(r['r_mod'])})")

    path = os.path.join(DATA, "flood_validation.csv")
    out[is_scot | is_wales].to_csv(path, index=False)
    print(f"\n  wrote {path}")


if __name__ == "__main__":
    main()
