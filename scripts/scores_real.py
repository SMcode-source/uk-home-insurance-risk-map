"""Real-data peril scores.

Subsidence: BGS 625k bedrock geology (OGL) classified for shrink-swell
susceptibility per formation, area-weighted onto each postcode district.
The formation ranking follows the BGS shrink-swell (GeoSure) literature:
Palaeogene/Cretaceous/Jurassic over-consolidated clays rank highest.

Weather: Met Office Climate Data Portal grids interpolated to district
centroids (inverse-distance weighting, k=4):
  - winter mean wind speed, 5km (UKCP18 baseline)
  - annual wind-driven rain index, SW-facing walls, 5km (UKCP18 baseline)
  - annual count of >=10mm rain days 1991-2020 (HadUK-Grid obs)
  - annual precipitation 1991-2020, 12km (HadUK-Grid obs)
"""

import csv
import os

import numpy as np
import geopandas as gpd
import shapely
from scipy.spatial import cKDTree

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# ---- shrink-swell susceptibility by formation (keyword -> score) ----
# Matched against lex_d (lithostratigraphy) first, then rcs_d (lithology).
LEX_SUSCEP = [
    ("LONDON CLAY", 1.00),
    ("THAMES GROUP", 1.00),
    ("GAULT", 0.90),
    ("WEALD CLAY", 0.90),
    ("OXFORD CLAY", 0.90),
    ("KIMMERIDGE CLAY", 0.90),
    ("AMPTHILL CLAY", 0.90),
    ("ANCHOLME GROUP", 0.85),
    ("BARTON GROUP", 0.85),
    ("BRACKLESHAM", 0.80),
    ("LAMBETH GROUP", 0.75),
    ("WEALDEN GROUP", 0.75),
    ("HASTINGS", 0.60),
    ("LIAS GROUP", 0.55),
    ("MERCIA MUDSTONE", 0.45),
    ("OSGODBY", 0.55),
    ("CORALLIAN", 0.40),
    ("GREAT OOLITE", 0.30),
]
RCS_SUSCEP = [
    ("CLAY", 0.70),
    ("MUDSTONE", 0.40),
    ("SILTSTONE", 0.25),
    ("MUD", 0.40),
    ("ARGILLACEOUS", 0.35),
]
DEFAULT_SUSCEP = 0.08

# Pre-Mesozoic mudstones are indurated (low plasticity): GeoSure rates
# them low regardless of lithology name, so the RCS keyword fallback is
# scaled down for old rocks.
YOUNG_PERIODS = {"TRIASSIC", "JURASSIC", "CRETACEOUS", "PALAEOGENE",
                 "PALEOGENE", "NEOGENE", "TERTIARY", "QUATERNARY"}
OLD_AGE_FACTOR = 0.3


def classify_susceptibility(lex_d, rcs_d, max_period=None):
    lex_d = (lex_d or "").upper()
    rcs_d = (rcs_d or "").upper()
    for key, score in LEX_SUSCEP:
        if key in lex_d:
            return score
    for key, score in RCS_SUSCEP:
        if key in rcs_d:
            if (max_period or "").strip().upper() not in YOUNG_PERIODS:
                score *= OLD_AGE_FACTOR
            return score
    return DEFAULT_SUSCEP


def subsidence_from_bgs(districts_bng: gpd.GeoDataFrame):
    """Area-weighted susceptibility + dominant clay formation per district.

    districts_bng: GeoDataFrame in EPSG:27700.
    Returns (score array in [0,1], dominant formation name array).
    """
    geo = gpd.read_file(os.path.join(DATA, "bgs_625k_bedrock.geojson"))
    geo = geo.set_crs(4326, allow_override=True).to_crs(27700)
    geo["geometry"] = shapely.make_valid(geo.geometry.values)
    geo["suscep"] = [classify_susceptibility(a, b, p)
                     for a, b, p in zip(geo["lex_d"], geo["rcs_d"],
                                        geo["max_period"])]

    dist_geoms = districts_bng.geometry.values
    tree = shapely.STRtree(geo.geometry.values)
    pairs = tree.query(dist_geoms, predicate="intersects")  # (2, n_pairs)

    inter = shapely.intersection(dist_geoms[pairs[0]],
                                 geo.geometry.values[pairs[1]])
    w = shapely.area(inter)
    s = geo["suscep"].values[pairs[1]]
    lex = geo["lex_d"].values[pairs[1]]

    n = len(districts_bng)
    score = np.zeros(n)
    dom = np.array([""] * n, dtype=object)
    wsum = np.bincount(pairs[0], weights=w, minlength=n)
    ssum = np.bincount(pairs[0], weights=w * s, minlength=n)
    ok = wsum > 0
    score[ok] = ssum[ok] / wsum[ok]

    # dominant (largest clay-weighted area) formation, for the popup
    clay_w = w * (s >= 0.4)
    order = np.argsort(clay_w)
    dom_w = np.zeros(n)
    for i in order:
        d = pairs[0][i]
        if clay_w[i] >= dom_w[d]:
            dom_w[d] = clay_w[i]
            dom[d] = lex[i]
    dom[dom_w == 0] = "none (low-plasticity bedrock)"

    # fall back to nearest polygon for slivers with no intersection
    if (~ok).any():
        near = tree.query_nearest(dist_geoms[~ok])
        score[~ok] = geo["suscep"].values[near[1]]
    return score, dom


# ---------------------------------------------------------------- weather


def _load_grid(name):
    xs, ys, vs = [], [], []
    with open(os.path.join(DATA, "metoffice", f"{name}.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            xs.append(float(row["x"]))
            ys.append(float(row["y"]))
            vs.append(float(row["value"]))
    xs, ys = np.array(xs), np.array(ys)
    if np.abs(xs).max() <= 180:      # centroid layers arrive as WGS84 lon/lat
        from pyproj import Transformer
        t = Transformer.from_crs(4326, 27700, always_xy=True)
        xs, ys = t.transform(xs, ys)
    return np.column_stack([xs, ys]), np.array(vs)


def _idw(pts, vals, targets, k=4):
    tree = cKDTree(pts)
    dist, idx = tree.query(targets, k=k)
    wgt = 1.0 / np.maximum(dist, 1.0) ** 2
    return (vals[idx] * wgt).sum(axis=1) / wgt.sum(axis=1)


def _stretch(v, lo_pct=5, hi_pct=95):
    lo, hi = np.percentile(v, [lo_pct, hi_pct])
    return np.clip((v - lo) / (hi - lo), 0, 1)


MIN_GUST_POINTS = 60   # below this the grid can't cover GB -> fall back


def _load_gusts():
    """Returns (points, p98, rp50) or None if absent/incomplete."""
    path = os.path.join(DATA, "gusts.csv")
    if not os.path.exists(path):
        return None
    xs, ys, p98, rp50 = [], [], [], []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            xs.append(float(row["x"]))
            ys.append(float(row["y"]))
            p98.append(float(row["gust_p98"]))
            rp50.append(float(row["gust_rp50"]))
    if len(xs) < MIN_GUST_POINTS:
        return None
    return np.column_stack([xs, ys]), np.array(p98), np.array(rp50)


def weather_from_metoffice(targets_bng):
    """targets_bng: (n, 2) array of district centroids in EPSG:27700.

    Returns (score in [0,1], dict of raw interpolated variables).
    Blends Met Office climatologies with an ERA5 extreme-gust component
    (1-in-50-year gust, Gumbel-fitted annual maxima — see fetch_gusts.py).
    """
    raw = {}
    for name in ["wind", "wdr", "rain10", "precip"]:
        pts, vals = _load_grid(name)
        raw[name] = _idw(pts, vals, targets_bng)
        print(f"  {name}: {len(vals)} grid pts -> "
              f"district range {raw[name].min():.1f}..{raw[name].max():.1f}")
    gusts = _load_gusts()
    if gusts is not None:
        gpts, p98, rp50 = gusts
        raw["gust_rp50"] = _idw(gpts, rp50, targets_bng)
        print(f"  gust_rp50: {len(rp50)} grid pts -> district range "
              f"{raw['gust_rp50'].min():.0f}..{raw['gust_rp50'].max():.0f} km/h")
        score = (0.30 * _stretch(raw["wind"])
                 + 0.25 * _stretch(raw["wdr"])
                 + 0.20 * _stretch(raw["gust_rp50"])
                 + 0.15 * _stretch(raw["rain10"])
                 + 0.10 * _stretch(raw["precip"]))
    else:
        print("  gust_rp50: gusts.csv missing/incomplete (rate-limited "
              "fetch?) -> 4-component blend; rerun fetch_gusts.py then "
              "build_model.py to upgrade")
        raw["gust_rp50"] = np.full(len(targets_bng), np.nan)
        score = (0.35 * _stretch(raw["wind"])
                 + 0.30 * _stretch(raw["wdr"])
                 + 0.20 * _stretch(raw["rain10"])
                 + 0.15 * _stretch(raw["precip"]))
    return np.clip(score, 0, 1), raw


# ----------------------------------------------------------------- flood


def _load_fraction_csv(fname, cols, names):
    table = {}
    with open(os.path.join(DATA, fname), newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = tuple(float(row[c]) for c in cols)
    arrs = []
    for i in range(len(cols)):
        a = np.array([table.get(n, (np.nan,) * len(cols))[i] for n in names])
        miss = np.isnan(a)
        if miss.any():
            print(f"  {fname}:{cols[i]}: {miss.sum()} districts missing "
                  "-> national-median fallback")
            a[miss] = np.nanmedian(a)
        arrs.append(a)
    return arrs


def flood_from_agencies(names):
    """Per-district flood-zone area fractions (EA / NRW / SEPA; see
    fetch_flood.py and fetch_surface_water.py).

    Returns (score, f_high, f_low, sw_high, sw_low):
      f_high : fraction in the ~1in100 river / 1in200 sea zone
      f_low  : fraction in the river/sea 1in1000 envelope (incl. f_high)
      sw_high: fraction in the surface-water >=1% AEP zone
      sw_low : fraction in the surface-water 1in1000 envelope
    """
    f_high, f_low = _load_fraction_csv(
        "flood_fractions.csv", ["f_high", "f_low"], names)
    sw_high, sw_low = _load_fraction_csv(
        "sw_fractions.csv", ["sw_high", "sw_low"], names)

    # surface water weighted lower: shallower water, cheaper claims
    idx = (0.75 * f_high + 0.25 * f_low) \
        + 0.6 * (0.75 * sw_high + 0.25 * sw_low)
    ref = max(np.percentile(idx, 95), 1e-6)
    score = np.clip(np.sqrt(idx / ref), 0, 1)
    return score, f_high, f_low, sw_high, sw_low


GW_BACKGROUND = 0.02   # non-England fallback (see fetch_groundwater.py)


def groundwater_from_ea(names):
    """Per-district groundwater flood-risk fraction (EA postcode search
    tool data; England only — elsewhere a nominal background).

    Returns (score in [0,1], gw_frac) where gw_frac is the share of unit
    postcodes inside a groundwater flood alert target area.
    """
    table = {}
    with open(os.path.join(DATA, "gw_fractions.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = float(row["gw_frac"])
    gw_frac = np.array([table.get(n, GW_BACKGROUND) for n in names])
    covered = sum(1 for n in names if n in table)
    print(f"  groundwater: {covered}/{len(names)} districts from EA data, "
          f"rest at {GW_BACKGROUND} background")
    ref = max(np.percentile(gw_frac, 97), 1e-6)
    score = np.clip(np.sqrt(gw_frac / ref), 0, 1)
    return score, gw_frac
