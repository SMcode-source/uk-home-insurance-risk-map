"""Subsidence geology read at the unit POSTCODES, not area-weighted.

subsidence_from_bgs() / superficial_from_bgs() weight each BGS 625k
polygon by the AREA it shares with the district. A district whose clay
lies under fields and whose houses stand on gravel terraces reads as
clay; the reverse reads as benign. This script classifies the SAME
layers with the SAME susceptibility tables (scores_real.LEX_SUSCEP,
RCS_SUSCEP, SUP_SUSCEP, SUP_EXCLUDED) at every live small-user
unit-postcode centroid (ONSPD, data/postcode_centroids.csv) and
aggregates by where the homes are:

    bedrock    mean bedrock susceptibility over the unit's postcodes
    sup_cover  share of the unit's postcodes on a CLASSIFIED superficial
               deposit (peat and unmapped drift excluded, as before)
    sup_score  mean superficial susceptibility over those postcodes
    geol       bedrock formation under the most postcodes among clay
               formations (susceptibility >= 0.4), for the popup
    sup_geol   superficial deposit under the most postcodes

Thin units are shrunk toward their parent with the beta-binomial /
weighted-mean prior of fetch_flood_postcodes.py (K_PRIOR postcodes;
sector -> district -> postcode area, hierarchical). The grain written
is the one load_districts() returns on this checkout. Output:

    data/subsidence_postcodes.csv
        name, n_pc, bedrock, sup_score, sup_cover, geol, sup_geol

scores_real.subsidence_score() reads it when present and keeps the
area-weighted reading for any unit it does not carry, so every caller
(build_model, sensitivity, dependence_check, seed_sweep) sees one
subsidence surface. combine_subsidence() and the ABI calibration are
untouched: only which units carry the clay moves. Needs the two BGS
GeoJSONs (fetch_bgs.py) and the ONSPD centroids (fetch_onspd.py).
"""
import os
import re
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scores_real as sr                          # noqa: E402
from build_model import load_districts           # noqa: E402

DATA = "data"
CENTROIDS = os.path.join(DATA, "postcode_centroids.csv")
OUT = os.path.join(DATA, "subsidence_postcodes.csv")
K_PRIOR = 20
AREA_RE = re.compile(r"[A-Z]+")


def area_of(name):
    return AREA_RE.match(name).group(0)


def polygon_at_points(geo, pts):
    """Index of the polygon containing each point; nearest for the rest."""
    tree = shapely.STRtree(geo.geometry.values)
    pairs = tree.query(pts, predicate="intersects")
    hit = np.full(len(pts), -1)
    # a point on a shared boundary intersects two polygons; keep the first
    seen = np.zeros(len(pts), dtype=bool)
    for p, g in zip(pairs[0], pairs[1]):
        if not seen[p]:
            hit[p] = g
            seen[p] = True
    miss = np.nonzero(hit < 0)[0]
    if len(miss):
        near = tree.query_nearest(pts[miss], all_matches=False)
        hit[miss] = near[1]
    return hit, len(miss)


def main():
    if not os.path.exists(CENTROIDS):
        raise SystemExit(f"{CENTROIDS} missing - run scripts/fetch_onspd.py first")
    pc = pd.read_csv(CENTROIDS)
    pc = pc[pc["country"].isin(["England", "Wales", "Scotland"])].reset_index(drop=True)
    pc["area"] = pc["district"].map(area_of)
    pts = shapely.points(pc["easting"].values.astype(float),
                         pc["northing"].values.astype(float))
    print(f"GB unit postcodes: {len(pc):,}", flush=True)

    # ---- bedrock, exactly as subsidence_from_bgs classifies it
    geo = gpd.read_file(os.path.join(DATA, "bgs_625k_bedrock.geojson"))
    geo = geo.set_crs(4326, allow_override=True).to_crs(27700)
    geo["geometry"] = shapely.make_valid(geo.geometry.values)
    geo["suscep"] = [sr.classify_susceptibility(a, b, p)
                     for a, b, p in zip(geo["lex_d"], geo["rcs_d"], geo["max_period"])]
    hit, nmiss = polygon_at_points(geo, pts)
    pc["bedrock"] = geo["suscep"].values[hit]
    pc["lex"] = geo["lex_d"].values[hit]
    print(f"bedrock: {len(geo):,} polygons; {nmiss:,} postcodes outside every "
          f"polygon took the nearest", flush=True)

    # ---- superficial, exactly as superficial_from_bgs classifies it
    sup_path = os.path.join(DATA, "bgs_625k_superficial.geojson")
    sgeo = gpd.read_file(sup_path)
    sgeo = sgeo.set_crs(4326, allow_override=True).to_crs(27700)
    sgeo["geometry"] = shapely.make_valid(sgeo.geometry.values)
    names = np.array([(v or "").strip().upper() for v in sgeo["lex_d"].values])
    unknown = sorted({v for v in names
                      if v and v not in sr.SUP_SUSCEP and v not in sr.SUP_EXCLUDED})
    if unknown:
        raise SystemExit(f"unclassified superficial deposits: {unknown}")
    keep = np.array([bool(v) and v in sr.SUP_SUSCEP for v in names])
    sgeo = sgeo[keep].reset_index(drop=True)
    snames = names[keep]
    tree = shapely.STRtree(sgeo.geometry.values)
    pairs = tree.query(pts, predicate="intersects")
    covered = np.zeros(len(pc), dtype=bool)
    sup = np.zeros(len(pc))
    sup_lex = np.array([""] * len(pc), dtype=object)
    for p, g in zip(pairs[0], pairs[1]):
        if not covered[p]:
            covered[p] = True
            sup[p] = sr.SUP_SUSCEP[snames[g]]
            sup_lex[p] = snames[g].title()
    pc["covered"] = covered
    pc["sup"] = sup
    pc["sup_lex"] = sup_lex
    print(f"superficial: {int(covered.sum()):,} postcodes ({covered.mean():.1%}) on a "
          f"classified deposit", flush=True)

    # ---- aggregate to the checkout's grain, with the hierarchical prior
    units = load_districts()["name"].tolist()
    grain = "sector" if any(" " in n for n in units) else "district"

    def stats(g):
        return pd.DataFrame({
            "n": g.size(), "bed": g["bedrock"].sum(), "cov": g["covered"].sum(),
            "sup": g["sup"].sum()})           # sup is 0 where not covered

    own = stats(pc.groupby(grain))
    area = stats(pc.groupby("area"))
    area_mean = pd.DataFrame({"bed": area["bed"] / area["n"],
                              "cov": area["cov"] / area["n"],
                              "sup": area["sup"] / area["cov"].clip(lower=1)})
    if grain == "district":
        prior = area_mean
    else:
        dist = stats(pc.groupby("district"))
        pa = area_mean.reindex(dist.index.map(area_of)).set_index(dist.index)
        prior = pd.DataFrame({
            "bed": (dist["bed"] + K_PRIOR * pa["bed"]) / (dist["n"] + K_PRIOR),
            "cov": (dist["cov"] + K_PRIOR * pa["cov"]) / (dist["n"] + K_PRIOR),
            "sup": (dist["sup"] + K_PRIOR * pa["sup"]) / (dist["cov"] + K_PRIOR)})

    # dominant formations by postcode count (clay-weighted for bedrock)
    clay = pc[pc["bedrock"] >= 0.4]
    dom_geol = clay.groupby(grain)["lex"].agg(lambda s: s.value_counts().index[0])
    dom_sup = pc[pc["covered"]].groupby(grain)["sup_lex"].agg(
        lambda s: s.value_counts().index[0])

    rows, thin, missing = [], 0, 0
    for n in units:
        p = n.split(" ")[0] if grain == "sector" else area_of(n)
        if p not in prior.index:
            missing += 1
            continue
        pb, pcv, ps = prior.loc[p, ["bed", "cov", "sup"]]
        if n in own.index:
            cnt, bed, cov, sp = own.loc[n, ["n", "bed", "cov", "sup"]]
            if cnt < K_PRIOR:
                thin += 1
        else:
            cnt = bed = cov = sp = 0
            thin += 1
        bedrock = (bed + K_PRIOR * pb) / (cnt + K_PRIOR)
        cover = (cov + K_PRIOR * pcv) / (cnt + K_PRIOR)
        sup_score = (sp + K_PRIOR * ps) / (cov + K_PRIOR)
        rows.append((n, int(cnt), bedrock, sup_score, cover,
                     dom_geol.get(n, "none (low-plasticity bedrock)"),
                     dom_sup.get(n, "none mapped")))
    out = pd.DataFrame(rows, columns=["name", "n_pc", "bedrock", "sup_score",
                                      "sup_cover", "geol", "sup_geol"])
    out.to_csv(OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT}: {len(out)} {grain}s ({thin} with fewer than {K_PRIOR} "
          f"postcodes, shrunk toward their parent; {missing} left to the "
          f"area-weighted fallback); bedrock mean {out.bedrock.mean():.4f}, "
          f"cover mean {out.sup_cover.mean():.3f}", flush=True)


if __name__ == "__main__":
    main()
