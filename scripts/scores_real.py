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


# ------------------------------------------- superficial (drift) deposits
# Superficial deposits overlie the bedrock and, where clay-rich, govern the
# soil domestic foundations actually bear on. The 625k superficial
# vocabulary is small and fully enumerable - 14 lex_d values over
# 132,391 km2, about 58% of GB - so every deposit is classified explicitly
# rather than keyword-matched with a catch-all. An unrecognised value is a
# fetch or schema change and should be noticed, not silently defaulted.
#
# Values are on the same 0-1 shrink-swell scale as the bedrock table.
SUP_SUSCEP = {
    "LACUSTRINE DEPOSITS (UNDIFFERENTIATED)": 0.75,   # soft plastic lake clay
    "CLAY-WITH-FLINTS": 0.70,       # the "clay over chalk" case exactly
    "BRICKEARTH": 0.60,             # clayey silt, shrink-swell and collapse
    "LANDSLIP": 0.55,               # remoulded, and landslips happen in clay
    "ALLUVIUM": 0.50,               # rock_d "CLAY, SILT AND SAND"; variable
    "TILL": 0.45,                   # clay matrix but over-consolidated
    "RAISED MARINE DEPOSITS (UNDIFFERENTIATED)": 0.30,
    "CRAG GROUP": 0.10,             # sandy shelly marine, East Anglia
    "GLACIAL SAND AND GRAVEL": 0.05,
    "RIVER TERRACE DEPOSITS (UNDIFFERENTIATED)": 0.05,
    "SAND AND GRAVEL OF UNCERTAIN AGE AND ORIGIN": 0.05,
    "BLOWN SAND": 0.05,
}
# Deposits deliberately left out of the cover fraction entirely, so the
# ground beneath them falls back to bedrock rather than being scored.
SUP_EXCLUDED = {
    # Peat subsides, badly - but by consolidation and oxidation, not
    # shrink-swell. Pricing it inside this peril would conflate two
    # mechanisms under one calibration. 15,728 km2, 11.9% of cover.
    "PEAT",
    # Not a deposit, an absence of survey. Scoring it would invent data.
    "DRIFT GEOLOGY NOT MAPPED [FOR DIGITAL MAP USE ONLY]",
}

# How much weight superficial cover may take from bedrock where it is
# present. NOT 1.0, and the reason is the whole difficulty: 625k publishes
# no THICKNESS, so a 0.5 m gravel skin and a 20 m clay sequence look
# identical here. Half-weight says "where drift covers the ground it
# probably governs, but we cannot show it does" - it shifts relativities
# without letting an unmeasured layer override mapped bedrock.
SUP_WEIGHT = 0.5


def superficial_from_bgs(districts_bng: gpd.GeoDataFrame):
    """Area-weighted superficial susceptibility and cover per district.

    Returns (score, cover_fraction, dominant_deposit). `cover_fraction`
    counts only CLASSIFIED deposits - peat and unmapped drift are excluded,
    so those areas fall through to bedrock instead of being scored.

    Missing layer -> zero cover, which makes combine_subsidence() a no-op
    and leaves the bedrock score exactly as it was.
    """
    n = len(districts_bng)
    path = os.path.join(DATA, "bgs_625k_superficial.geojson")
    if not os.path.exists(path):
        print("  bgs_625k_superficial.geojson missing -> bedrock only "
              "(run scripts/fetch_bgs.py --superficial)")
        return np.zeros(n), np.zeros(n), np.array([""] * n, dtype=object)

    geo = gpd.read_file(path)
    geo = geo.set_crs(4326, allow_override=True).to_crs(27700)
    geo["geometry"] = shapely.make_valid(geo.geometry.values)

    names = np.array([(v or "").strip().upper() for v in geo["lex_d"].values])
    unknown = sorted({v for v in names
                      if v and v not in SUP_SUSCEP and v not in SUP_EXCLUDED})
    if unknown:
        raise SystemExit(
            f"unclassified superficial deposits: {unknown}\n"
            "SUP_SUSCEP enumerates the whole 625k vocabulary on purpose - a "
            "new value means the layer changed, so classify it rather than "
            "letting it default silently.")
    keep = np.array([bool(v) and v in SUP_SUSCEP for v in names])
    susc = np.array([SUP_SUSCEP.get(v, 0.0) for v in names])

    dist_geoms = districts_bng.geometry.values
    tree = shapely.STRtree(geo.geometry.values[keep])
    pairs = tree.query(dist_geoms, predicate="intersects")
    idx = np.nonzero(keep)[0][pairs[1]]

    inter = shapely.intersection(dist_geoms[pairs[0]],
                                 geo.geometry.values[idx])
    w = shapely.area(inter)
    s = susc[idx]

    dist_area = np.maximum(shapely.area(dist_geoms), 1.0)
    wsum = np.bincount(pairs[0], weights=w, minlength=n)
    ssum = np.bincount(pairs[0], weights=w * s, minlength=n)
    score = np.zeros(n)
    ok = wsum > 0
    score[ok] = ssum[ok] / wsum[ok]
    # cover cannot exceed the district: 625k polygons overlap slightly at
    # shared boundaries after make_valid, which would otherwise push a
    # fully-drift-covered district just above 1.0
    cover = np.clip(wsum / dist_area, 0.0, 1.0)

    dom = np.array([""] * n, dtype=object)
    dom_w = np.zeros(n)
    lex = names[idx]
    for i in np.argsort(w):
        d = pairs[0][i]
        if w[i] >= dom_w[d]:
            dom_w[d] = w[i]
            dom[d] = lex[i].title()
    dom[dom_w == 0] = "none mapped"

    print(f"  superficial: {int((cover > 0.01).sum())}/{n} districts with "
          f"mapped drift; cover {cover.mean():.1%} mean, "
          f"susceptibility {score[ok].min():.2f}..{score[ok].max():.2f}")
    return score, cover, dom


def subsidence_score(districts_bng: gpd.GeoDataFrame):
    """The subsidence susceptibility the model actually prices.

    THE single entry point - build_model, sensitivity and dependence_check
    all call this rather than assembling bedrock + superficial themselves.
    They used to call subsidence_from_bgs() directly, which was fine while
    bedrock was the whole story; the moment superficial arrived, three
    copies of the same three steps meant the sensitivity and dependence
    runs could silently model a different subsidence surface from the one
    published. One path, no drift.

    Returns (score, bedrock_formation, superficial_cover, superficial_name).
    """
    bedrock, geol = subsidence_from_bgs(districts_bng)
    sup, cover, sup_geol = superficial_from_bgs(districts_bng)
    return combine_subsidence(bedrock, sup, cover), geol, cover, sup_geol


def combine_subsidence(bedrock, sup_score, sup_cover):
    """Blend the superficial modifier into the bedrock susceptibility.

        sub = (1 - W*cover)*bedrock + W*cover*superficial

    so drift pulls the score towards its own susceptibility in proportion
    to how much of the district it covers, capped at SUP_WEIGHT. It cuts
    both ways by design: clay-with-flints over chalk raises a district that
    bedrock alone reads as benign, and glacial sand over London Clay lowers
    one that bedrock alone reads as severe - a granular skin genuinely does
    buffer the seasonal moisture change that drives shrink-swell.

    Only relativities move. calibrate_frequency() pins the national level
    to the ABI subsidence payout afterwards, so this cannot change the
    calibrated loss cost, only which districts carry it.
    """
    k = SUP_WEIGHT * np.clip(sup_cover, 0.0, 1.0)
    return np.clip((1.0 - k) * bedrock + k * sup_score, 0.0, 1.0)


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
    Blends Met Office climatologies with an extreme-gust component
    (1-in-50-year gust, Gumbel-fitted annual maxima). Since 2026-08-10
    gusts.csv holds MIDAS station extremes (gusts_from_midas.py); before
    that, ERA5 grid points (fetch_gusts.py, still the no-CEDA fallback).
    Either way it is scattered (x, y, rp50) points and IDW below.
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


def frost_from_metoffice(targets_bng):
    """Annual air-frost days per district (HadUK-Grid obs 1991-2020,
    fetch_metoffice.py `frost` layer) - the freeze-exposure driver for
    escape of water. Returns the raw day count, NOT a stretched score:
    the EoW marginal wants a physical relativity (a district with twice
    the frost days has twice the freeze exposure), and only ~15% of the
    peril varies with it, so a [0,1] stretch would overstate the spread.
    Deliberately separate from weather_from_metoffice: wx_score feeds
    the calibrated storm peril and must not move when EoW arrives.
    """
    pts, vals = _load_grid("frost")
    frost = _idw(pts, vals, targets_bng)
    print(f"  frost: {len(vals)} grid pts -> "
          f"district range {frost.min():.1f}..{frost.max():.1f} days")
    return frost


def drought_from_haduk(names):
    """Per-district 1991-2020 drought climatology (HadUK-Grid 1 km daily
    via CEDA, reduced by make_smd_climatology.py): the mean annual peak
    of the within-year cumulative water deficit max(cumsum(PET-rain), 0),
    reset each 1 January. The subsidence frequency driver for the Gate 2
    SMD curve. Returns raw mm, NOT a stretched score, for the same
    reason as frost_from_metoffice above: the marginal wants a physical
    relativity, and its normalisation lives in main() with the exposure
    weights.

    Coverage is required EXACTLY, no fallback: the file is built from
    the very polygon set being scored, so a missing name means the file
    is at the wrong GRAIN (a district-keyed file under the sector build,
    or vice versa - the ct_bands failure mode, where "AB10" met "AB10 1"
    and every row silently missed). The only correct response is to
    refuse loudly.
    """
    table = {}
    with open(os.path.join(DATA, "smd_climatology.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["district"]] = float(row["cwd_yr_clim_mm"])
    missing = [n for n in names if n not in table]
    if missing:
        raise SystemExit(
            f"smd_climatology.csv: {len(missing)} of {len(names)} names "
            f"missing (e.g. {missing[:5]}) - wrong grain? The file must "
            "be built from the same polygon set it scores.")
    vals = np.array([table[n] for n in names], dtype=float)
    print(f"  drought: {len(names)} of {len(table)} rows used -> "
          f"climatology range {vals.min():.0f}..{vals.max():.0f} mm")
    return vals


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

    score = flood_score_from_fractions(f_high, f_low, sw_high, sw_low)
    return score, f_high, f_low, sw_high, sw_low


# 95th percentile of the present-day flood index, held so the climate run
# is scored on the same scale rather than re-anchoring to its own spread.
_FLOOD_REF = None


def flood_score_from_fractions(f_high, f_low, sw_high, sw_low, climate=False):
    """0-1 flood score from zone fractions.

    Surface water is weighted lower than fluvial/tidal: shallower water,
    cheaper claims. The score is anchored to the 95th percentile of the
    PRESENT-DAY index in both runs - re-anchoring the climate run to its
    own distribution would rescale the very increase being measured and
    report a smaller change than there is.
    """
    global _FLOOD_REF
    idx = (0.75 * f_high + 0.25 * f_low) \
        + 0.6 * (0.75 * sw_high + 0.25 * sw_low)
    if climate and _FLOOD_REF is not None:
        ref = _FLOOD_REF
    else:
        ref = max(np.percentile(idx, 95), 1e-6)
        if not climate:
            _FLOOD_REF = ref
    return np.clip(np.sqrt(idx / ref), 0, 1)


# ------------------------------------------------------------ coverage

# Several EA products stop at the English border. Deciding coverage from
# the data itself keeps going wrong in ways that look plausible - a Welsh
# district with no depth mapped reads as "nothing over 0.2 m", and Dundee's
# missing climate-change extent reads as a 70-point FALL in flood risk. So
# coverage comes from the actual boundary instead (see fetch_countries.py).
# A district must also be substantially inside England: the ~20 genuine
# straddlers (Portishead, Chester, Berwick, Welshpool...) get only partial
# English data, so they take the neutral fallback rather than a reading
# built from whichever half happens to be mapped.
ENGLAND_MIN_SHARE = 0.95


def load_country(names):
    """Country per district, or '' if country.csv is missing."""
    path = os.path.join(DATA, "country.csv")
    if not os.path.exists(path):
        return np.array([""] * len(names))
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = row["country"]
    return np.array([table.get(n, "") for n in names])


def england_mask(names):
    """Boolean mask: districts substantially inside England.

    Falls back to all-True with a warning if country.csv is missing, so the
    model still runs - but the England-only datasets will then be read as
    if they covered the whole of GB, which is exactly the error the file
    exists to prevent.
    """
    path = os.path.join(DATA, "country.csv")
    if not os.path.exists(path):
        print("  country.csv missing -> cannot tell England from Wales or "
              "Scotland; England-only layers will be misread "
              "(run scripts/fetch_countries.py)")
        return np.ones(len(names), dtype=bool)
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = (row["country"], float(row["share"]))
    mask = np.array([table.get(n, ("", 0.0))[0] == "England"
                     and table.get(n, ("", 0.0))[1] >= ENGLAND_MIN_SHARE
                     for n in names])
    return mask


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


# ------------------------------------------------------ surface-water depth


# Depth bands from the EA layers, as (csv key, lower edge, upper edge).
# The top band is open-ended; 1.8 m is a working upper bound for the mean
# depth of water in it.
DEPTH_BANDS = [("d02", 0.0, 0.2), ("d03", 0.2, 0.3), ("d06", 0.3, 0.6),
               ("d09", 0.6, 0.9), ("d12", 0.9, 1.2), (None, 1.2, 1.8)]

# Relative damage by depth band for a UK residential property (buildings +
# contents). The shape follows the standard UK depth-damage curves: damage
# climbs steeply through the first half-metre as water passes floor level
# and reaches sockets, then flattens once the ground floor is written off.
# These are RELATIVITIES only - the national average is renormalised to 1.0
# below, so the calibrated ABI severity level is untouched and only the
# spread between districts changes.
DEPTH_DAMAGE = [0.45, 0.75, 1.00, 1.35, 1.60, 1.95]


# Claim-frequency weights per likelihood band, matching marginal_params:
# a property in the >=1% AEP ("high") zone claims about five times as often
# as one in the rest of the 1-in-1000 envelope.
SW_FREQ_HIGH, SW_FREQ_LOW = 0.010, 0.002

# Exposure-weighted mean of the raw present-day multiplier. Held so the
# climate run can be expressed on the same scale instead of renormalising
# its own level away. Set by the first non-climate call.
_DEPTH_REF = None


def _band_shares(env, frac):
    """Occupancy of each depth band within an envelope.

    `frac` is the nested set of exceedance fractions (>0.2, >0.3, ... m),
    so successive differences give the band occupancies; the shallowest
    band is whatever the envelope holds beyond the 0.2 m mask.
    """
    edges = np.column_stack([env, frac])                   # (n, 6)
    edges = np.maximum.accumulate(edges[:, ::-1], axis=1)[:, ::-1]
    bands = edges[:, :-1] - edges[:, 1:]                   # (n, 5)
    return np.column_stack([bands, edges[:, -1]])          # (n, 6) incl. >1.2


def sw_depth_severity(names, sw_high, sw_low, households, climate=False):
    """Per-district relative severity multiplier for surface-water claims.

    Reads data/sw_depth.csv (see fetch_sw_depth.py): the fraction of each
    district exceeding 0.2/0.3/0.6/0.9/1.2 m of surface water. Conditional
    on being inside the flooded envelope, those nested fractions give the
    depth distribution, which is turned into an expected damage relativity.

    The depth distribution is computed SEPARATELY for the two likelihood
    bands and blended by how much each contributes to claim frequency.
    That matters because the two are not alike: the >=1% AEP zone is where
    most claims come from, and it is generally the deeper water, so mixing
    it into one envelope-wide average dilutes exactly the signal being
    measured. The residual 1-in-1000 fringe is shallower and claims five
    times less often, so it is weighted accordingly.

    England only - NRW and SEPA publish no equivalent depth product, so
    Welsh and Scottish districts (and any English district with no mapped
    surface water) fall back to 1.0, i.e. the flat severity used before.

    Returns (multiplier, mean_depth_m), both length-len(names).
    """
    fname = "sw_depth_cc.csv" if climate else "sw_depth.csv"
    path = os.path.join(DATA, fname)
    if climate and not os.path.exists(path):
        # Fall back to the present-day depth bands rather than to a flat
        # severity: the future extents are still wider, so this understates
        # the change rather than inventing one. Note it swaps the FILE, not
        # the climate flag - recursing with climate=False would renormalise
        # against the future's own mean and overwrite the present-day
        # reference, which is precisely what that reference exists to stop.
        print(f"  {fname} missing -> future severity reuses present-day "
              "depth (run fetch_sw_depth.py --climate)")
        path = os.path.join(DATA, "sw_depth.csv")
    if not os.path.exists(path):
        print("  sw_depth.csv missing -> flat surface-water severity "
              "(run scripts/fetch_sw_depth.py)")
        return np.ones(len(names)), np.full(len(names), np.nan)

    keys = [k for k, _, _ in DEPTH_BANDS if k]
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = ([float(row[f"{k}_high"]) for k in keys],
                                  [float(row[f"{k}_low"]) for k in keys])
    blank = ([0.0] * len(keys), [0.0] * len(keys))
    frac_hi = np.array([table.get(n, blank)[0] for n in names])
    frac_lo = np.array([table.get(n, blank)[1] for n in names])

    env_hi = np.asarray(sw_high, dtype=float)
    env_lo = np.asarray(sw_low, dtype=float)
    # the two bands are disjoint: the fringe is the envelope minus the
    # high-likelihood zone, in extent and in depth alike
    b_hi = _band_shares(env_hi, frac_hi)
    b_fringe = np.maximum(_band_shares(env_lo, frac_lo) - b_hi, 0.0)

    # weight by contribution to claim frequency, not by area
    w_hi = SW_FREQ_HIGH * b_hi.sum(axis=1)
    w_fr = SW_FREQ_LOW * b_fringe.sum(axis=1)
    denom = np.maximum(w_hi + w_fr, 1e-15)
    bands = (b_hi * (w_hi / denom / np.maximum(b_hi.sum(axis=1), 1e-15))[:, None]
             + b_fringe * (w_fr / denom
                           / np.maximum(b_fringe.sum(axis=1), 1e-15))[:, None])
    bands = np.nan_to_num(bands)

    # Coverage comes from the boundary, not from the numbers. Two silent
    # traps make that necessary:
    #
    # 1. fetch_sw_depth.py writes a row for EVERY district, zero-filled
    #    outside England. A Welsh district DOES have surface water (from
    #    NRW), so judging by the envelope alone reads "no depth mapped" as
    #    "none of it exceeds 0.2 m" - the shallowest possible severity,
    #    handed to all of Wales and Scotland.
    # 2. Border districts (Annan, Wrexham, Caldicot, Berwick...) clip into
    #    England far enough to pick up a sliver of EA depth while sw_low
    #    covers the whole district, so they look uniformly shallow.
    #
    # england_mask() settles both from the actual country boundary.
    tot = bands.sum(axis=1)
    have = (tot > 1e-9) & england_mask(names)
    share = np.zeros_like(bands)
    share[have] = bands[have] / tot[have][:, None]

    mult = np.ones(len(names))
    mult[have] = share[have] @ np.array(DEPTH_DAMAGE)

    mids = np.array([0.5 * (lo + hi) for _, lo, hi in DEPTH_BANDS])
    mean_depth = np.full(len(names), np.nan)
    mean_depth[have] = share[have] @ mids

    # Renormalise so the exposure-weighted national mean multiplier is 1.0:
    # this re-shapes severity across districts without moving the level the
    # ABI calibration has already fixed.
    #
    # The climate run must NOT renormalise to its own mean. Doing so would
    # divide out exactly what it is measuring - water getting deeper
    # everywhere - and leave only the relativities, reporting no severity
    # change at all. It is therefore normalised against the PRESENT-DAY
    # reference, so a uniformly deeper future comes out above 1.0.
    global _DEPTH_REF
    w = np.asarray(households, dtype=float)
    own_ref = float(np.average(mult[have], weights=w[have])) if have.any() else 1.0
    if climate and _DEPTH_REF is not None:
        ref = _DEPTH_REF
        print(f"  (climate depth normalised against the present-day "
              f"reference {ref:.4f}, not its own {own_ref:.4f})")
    else:
        ref = own_ref
        if not climate:
            _DEPTH_REF = own_ref
    mult = mult / max(ref, 1e-9)
    mult[~have] = 1.0

    print(f"  sw depth: {int(have.sum())}/{len(names)} districts with mapped "
          f"depth; multiplier {mult[have].min():.2f}..{mult[have].max():.2f} "
          f"(mean depth {np.nanmin(mean_depth):.2f}..{np.nanmax(mean_depth):.2f} m)")
    return mult, mean_depth


# ------------------------------------------------ climate-change scenario


def flood_future(names, f_high, f_low, sw_high, sw_low):
    """Swap in the EA's climate-change flood extents where they exist.

    The EA publishes a climate-change edition of the two products this
    model already uses - the rivers/sea defended extents and NaFRA2 RoFSW -
    under the same service family and the same layer names. Using that
    matched pair matters: the alternative NaFRA2 `rofrs_cc01_4band` product
    is derived differently from the present-day extents we hold, so a
    comparison against it would confound the method change with the
    climate change.

    England only. Wales and Scotland keep their present-day values, so the
    repricing must be reported over covered districts rather than
    nationally, where it would be diluted into meaninglessness.

    Returns (f_high, f_low, sw_high, sw_low, covered) or None if the
    climate files have not been fetched.
    """
    fl = os.path.join(DATA, "flood_fractions_cc.csv")
    sw = os.path.join(DATA, "sw_fractions_cc.csv")
    if not (os.path.exists(fl) and os.path.exists(sw)):
        print("  climate-change flood files missing -> no repricing view "
              "(run fetch_flood.py --climate and "
              "fetch_surface_water.py --climate)")
        return None

    def read(path, cols):
        t = {}
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                t[row["name"]] = tuple(float(row[c]) for c in cols)
        return t

    tfl = read(fl, ["f_high", "f_low"])
    tsw = read(sw, ["sw_high", "sw_low"])
    covered = england_mask(names)

    out = [np.array(f_high, dtype=float), np.array(f_low, dtype=float),
           np.array(sw_high, dtype=float), np.array(sw_low, dtype=float)]
    for i, n in enumerate(names):
        if not covered[i]:
            continue
        if n in tfl:
            out[0][i], out[1][i] = tfl[n]
        if n in tsw:
            out[2][i], out[3][i] = tsw[n]
    # Enforce the BAND nesting within the future: the 1-in-1000 envelope
    # contains the 1-in-100/200 zone, and the surface-water envelope
    # contains its >=1% AEP zone. Purely defensive against a rasterising
    # difference between the two layers - on the current data neither
    # clamp fires for a single district.
    #
    # It deliberately says NOTHING about present vs future, and must not be
    # "corrected" into np.maximum(future, present). The future is a separate
    # EA model run, not an uplift of the present one, and 52 of the 2,087
    # covered districts (2.5%) genuinely see the 1-in-100/200 band shrink,
    # worst -11.2pp. Clamping that away would silently rewrite them and
    # delete the finding README states under "Rivers/sea is not a strict
    # uplift" - while leaving the +37.7% national growth looking unchanged,
    # so nothing would appear to break.
    out[1] = np.maximum(out[1], out[0])
    out[3] = np.maximum(out[3], out[2])
    print(f"  climate-change flood: {int(covered.sum())} districts repriced "
          f"(England); f_high mean {np.mean(f_high):.5f} -> "
          f"{out[0].mean():.5f}")
    return out[0], out[1], out[2], out[3], covered


# --------------------------------------------------------- coastal erosion


EROSION_HORIZON_YEARS = 80.0     # 2025 -> 2105 epoch


# NCERM columns, England. Must stay in step with LAYERS in
# fetch_erosion.py. The *_lo / *_hi columns are the 0th and
# 95th-percentile climate allowances on the 2105 epoch; the unsuffixed
# ones are the 70th (central) case.
NCERM_COLS = ["er_smp55", "er_smp105", "er_nfi55", "er_nfi105",
              "er_smp105_lo", "er_smp105_hi", "er_nfi105_lo", "er_nfi105_hi",
              "er_gi"]

# Dynamic Coast columns, Scotland. Must stay in step with LAYERS in
# fetch_erosion_scotland.py. _hi is RCP8.5 at the 95th percentile, _lo is
# RCP2.6; there is no Scottish central case.
DC_COLS = ["er_dc50_hi", "er_dc100_hi", "er_dc50_lo", "er_dc100_lo"]


def erosion_from_ncerm(names):
    """Per-district coastal-erosion exposure (England + Scotland).

    Returns (score, dict of arrays). The fractions are the share of
    district area projected to be lost to erosion by each epoch/scenario.

    TWO SOURCES, AND THEY ARE NOT THE SAME MEASUREMENT.

    England takes EA NCERM 2024 (`er_smp*` / `er_nfi*` / `er_gi`), whose
    land lost comes from each frontage's length x recession rather than
    from the polygon area - see fetch_erosion.py for why the polygon is
    not trustworthy there.

    Scotland takes NatureScot's Dynamic Coast phase 2 (`er_dc*`), added
    2026-09-03, whose polygon IS the land lost - the strip between the
    2020 and projected MHWS lines, already limited by the UPSM
    susceptibility model and by a 25 m cap at known artificial defences.
    See fetch_erosion_scotland.py, and DATA_SOURCES #38(d) for the
    reversal that catches people out: trust NCERM's attribute and Dynamic
    Coast's geometry, never the other way round.

    `er_head` is what the model actually scores and prices from, and
    `er_basis` says per district which source it came from - because the
    two bases differ in ways no single column can express:

      * MANAGEMENT. NCERM publishes a pair, SMP (defences maintained as
        planned; the English headline) against NFI (no further
        intervention). Dynamic Coast publishes one management case, "do
        nothing" with existing defences standing. There is no Scottish
        NFI, so `er_nfi*` is genuinely absent in Scotland, not zero-risk.
      * CLIMATE. England prices the 70th-percentile allowance. Scotland's
        ladder is RCP2.6 and RCP8.5-95th with no central rung, so the
        headline takes RCP8.5-95th - the nearer of the two, and by how
        much is measurable on England's own columns (the 95th is 1.16x
        the 70th; the 0th is 0.53x of it).
      * HORIZON. NCERM's epoch is 2105 and Dynamic Coast's is 2100, both
        annualised over the single EROSION_HORIZON_YEARS. Dynamic Coast
        also baselines at 2020 rather than 2025, so Scotland's strip is
        spread over ~5 years more than it accrued in - a ~6% dilution of
        the Scottish annual rate, left in rather than corrected, because
        a second horizon constant would buy precision this peril (unpriced,
        GBP2.85 of EL) does not justify.

    Districts either source does not reach - inland England, all of Wales
    and Northern Ireland, inland Scotland - are zero, not missing: they
    genuinely have no projected coastal erosion.
    """
    n = len(names)
    cols = NCERM_COLS + DC_COLS
    out = {c: np.zeros(n) for c in cols}
    basis = np.array(["none"] * n, dtype=object)

    path = os.path.join(DATA, "erosion.csv")
    if not os.path.exists(path):
        print("  erosion.csv missing -> zero English erosion exposure "
              "(run scripts/fetch_erosion.py)")
    else:
        table = {}
        with open(path, newline="") as fh:
            rdr = csv.DictReader(fh)
            missing = [c for c in NCERM_COLS
                       if c not in (rdr.fieldnames or [])]
            if missing:
                print(f"  erosion.csv predates {missing} -> zero "
                      "(rerun scripts/fetch_erosion.py to add them)")
            for row in rdr:
                table[row["name"]] = [float(row.get(c) or 0.0)
                                      for c in NCERM_COLS]
        arr = np.array([table.get(nm, [0.0] * len(NCERM_COLS))
                        for nm in names])
        for i, c in enumerate(NCERM_COLS):
            out[c] = arr[:, i]
        basis[(out["er_nfi105"] > 0) | (out["er_smp105"] > 0)] = "ncerm"

    scot_path = os.path.join(DATA, "erosion_scotland.csv")
    if not os.path.exists(scot_path):
        print("  erosion_scotland.csv missing -> zero Scottish erosion "
              "exposure (run scripts/fetch_erosion_scotland.py)")
    else:
        table = {}
        with open(scot_path, newline="") as fh:
            rdr = csv.DictReader(fh)
            missing = [c for c in DC_COLS if c not in (rdr.fieldnames or [])]
            if missing:
                raise SystemExit(
                    f"erosion_scotland.csv is missing {missing} - rerun "
                    "scripts/fetch_erosion_scotland.py (DATA_SOURCES #38)")
            for row in rdr:
                table[row["name"]] = [float(row.get(c) or 0.0)
                                      for c in DC_COLS]
        arr = np.array([table.get(nm, [0.0] * len(DC_COLS)) for nm in names])
        for i, c in enumerate(DC_COLS):
            out[c] = arr[:, i]
        hit = out["er_dc100_hi"] > 0
        # A file that joins nothing is the sector-branch trap the theft
        # work paid for once already: a district-keyed CSV on a
        # sector-keyed frame silently zeroes a whole country.
        if table and not hit.any():
            raise SystemExit(
                f"erosion_scotland.csv has {len(table)} rows and matched "
                f"NONE of the {n} areas in this frame - wrong grain? "
                "Rerun scripts/fetch_erosion_scotland.py on this branch "
                "(DATA_SOURCES #38)")
        basis[hit] = "dynamiccoast"

    # The one column the model scores from. England's SMP-2105 and
    # Scotland's Dynamic Coast 2100 are different bases; er_basis is what
    # keeps that legible downstream instead of hiding it in one number.
    out["er_head"] = np.where(basis == "dynamiccoast",
                              out["er_dc100_hi"], out["er_smp105"])
    out["er_basis"] = basis

    ref = max(np.percentile(out["er_head"], 99.5), 1e-9)
    score = np.clip(np.sqrt(out["er_head"] / ref), 0, 1)
    n_e = int((basis == "ncerm").sum())
    n_s = int((basis == "dynamiccoast").sum())
    print(f"  erosion: {n_e} districts from NCERM (England), {n_s} from "
          f"Dynamic Coast (Scotland) of {n}")
    print(f"    headline max {out['er_head'].max():.3%} of district area; "
          f"England SMP-2105 max {out['er_smp105'].max():.3%}, "
          f"Scotland RCP8.5-2100 max {out['er_dc100_hi'].max():.3%}")
    return score, out


# Scotland's theft geography arrives in its own file, data/housebreaking.csv,
# because police.uk carries no Scottish forces: 32 council housebreaking
# counts from the statistics.gov.scot recorded-crime cube, apportioned onto
# postcode geography by household share (scripts/fetch_housebreaking.py,
# DATA_SOURCES.md #37). It replaced a single flat national rate on
# 2026-09-01 - the measurement is LIMITATIONS.md 7.


def theft_from_police(names, households):
    """Annual burglaries per household per district (police.uk archive;
    see fetch_burglary.py).

    Returns th_rate, the RAW annual burglary rate per household. Only the
    geography matters: calibrate_frequency pins the exposure-weighted
    national level to the ABI theft figures, so the burglary-to-claim
    propensity cancels and never needs to be known.

    Three corrections, documented in DATA_SOURCES.md #25 and #29:

    - police.uk "Burglary" includes commercial premises, so districts
      with almost no residents show rates no household experiences
      (EC3V: 116 burglaries over 72 households = 54%/yr - offices).
      The Phase 2 fix (2026-08-17): the denominator is households PLUS
      the district's VOA non-domestic premises count, which attributes
      each district only the residential share of its burglary points.
      One propensity still cancels in FREQ_SCALE; what this changes is
      WHERE the burglaries land, not how many claims they imply.

    - The household-weighted 99.9th-percentile cap STAYS, as a backstop
      for tiny-denominator districts the premises data cannot explain
      (a hamlet with three burglaries in one bad month). Where the cap
      was doing crude duty for commercial cores it should now bind
      rarely - the evidence run counts exactly that.

    - Scotland is OVERRIDDEN, not filled: police.uk has no Scottish
      forces, but British Transport Police leaks a handful of Scottish
      railway burglaries into the data, so "has data" cannot be the
      test. Scottish areas take their rate from housebreaking.csv -
      council counts apportioned to postcode geography - and
      Welsh/English areas keep their own. (VOA covers E&W only, so
      Scottish premises are 0 - irrelevant under the override.)
    """
    path = os.path.join(DATA, "burglary.csv")
    if not os.path.exists(path):
        raise SystemExit("data/burglary.csv missing - run "
                         "scripts/fetch_burglary.py first (needs the "
                         "police.uk archive, see DATA_SOURCES.md #25)")
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = (float(row["burglaries"]),
                                  float(row["months"]))
    missing = [n for n in names if n not in table]
    if missing:
        raise SystemExit(f"burglary.csv is missing {len(missing)} districts "
                         f"(first: {missing[:5]}) - stale file? Rerun "
                         "scripts/fetch_burglary.py")

    prem_path = os.path.join(DATA, "premises.csv")
    if not os.path.exists(prem_path):
        raise SystemExit("data/premises.csv missing - run "
                         "scripts/fetch_premises.py first "
                         "(DATA_SOURCES.md #29)")
    prem_table = {}
    with open(prem_path, newline="") as fh:
        for row in csv.DictReader(fh):
            prem_table[row["name"]] = float(row["premises"])
    prem = np.array([prem_table.get(n, 0.0) for n in names])

    hh = np.maximum(np.asarray(households, dtype=float), 1.0)
    annual = np.array([table[n][0] / table[n][1] * 12.0 for n in names])
    # residential share of the district's burglary points: a burglary
    # in a district that is half shops was, on average, half as likely
    # to have hit a home. Equivalent to annual*(hh/(hh+prem))/hh.
    rate = annual / (hh + prem)

    country = np.array(load_country(names))
    scot = country == "Scotland"

    # A premises.csv keyed on the wrong geography joins NOTHING, and
    # prem_table.get(n, 0.0) then silently restores the old
    # households-only denominator: the correction vanishes and the run
    # still succeeds, looking like "no impact". That is the households.csv
    # void-run trap, and it is why this is an assertion and not a warning.
    # VOA covers E&W only and Scotland is overridden just below, so the
    # test is E&W-only; both published grains score >= 99.9%.
    ew_names = [n for n, s in zip(names, scot) if not s]
    if ew_names:
        hit = sum(1 for n in ew_names if n in prem_table)
        if hit / len(ew_names) < 0.95:
            raise SystemExit(
                f"premises.csv covers only {hit}/{len(ew_names)} E&W areas "
                f"({hit / len(ew_names):.1%}) - wrong geography key, or a "
                "district-keyed file on the sector branch? Rerun "
                "scripts/fetch_premises.py (DATA_SOURCES.md #29)")

    if scot.any():
        hb_path = os.path.join(DATA, "housebreaking.csv")
        if not os.path.exists(hb_path):
            raise SystemExit("data/housebreaking.csv missing - run "
                             "scripts/fetch_housebreaking.py first "
                             "(DATA_SOURCES.md #37)")
        # hb_3yr, not hb_1yr: three years of council counts (2023-24 to
        # 2025-26) rather than one. A single year is noisy in the small
        # councils, and 2024-25 alone is now a year stale - the cube
        # publishes 2025-26. The three-year window is the priced variant.
        hb_table = {}
        with open(hb_path, newline="") as fh:
            for row in csv.DictReader(fh):
                hb_table[row["name"]] = float(row["hb_3yr"])
        scot_names = [n for n, s in zip(names, scot) if s]
        hb_missing = [n for n in scot_names if n not in hb_table]
        if hb_missing:
            raise SystemExit(
                f"housebreaking.csv covers only "
                f"{len(scot_names) - len(hb_missing)}/{len(scot_names)} "
                f"Scottish areas (first missing: {hb_missing[:5]}) - stale "
                "file, or a district-keyed file on the sector branch? Rerun "
                "scripts/fetch_housebreaking.py (DATA_SOURCES.md #37)")
        hb = np.array([hb_table.get(n, 0.0) for n in names])
        rate[scot] = hb[scot] / hh[scot]
        print(f"  theft: {int(scot.sum())} Scottish areas -> "
              f"{hb[scot].sum():,.0f} housebreakings/yr across 32 councils, "
              f"mean {np.average(rate[scot], weights=hh[scot]):.3%}/yr, "
              f"range {rate[scot].min():.3%}-{rate[scot].max():.3%}")

    ew_r, ew_w = rate[~scot], hh[~scot]
    o = np.argsort(ew_r, kind="stable")   # stable: ties keep file order,
    cw = np.cumsum(ew_w[o])               # so the cap is deterministic
    cap = float(ew_r[o][np.searchsorted(cw, 0.999 * cw[-1])])
    clipped = int((rate > cap).sum())
    rate = np.minimum(rate, cap)
    print(f"  theft: E&W mean {np.average(rate[~scot], weights=hh[~scot]):.3%}"
          f"/yr; cap {cap:.3%} (hh-weighted p99.9), "
          f"{clipped} commercial-core districts clipped")
    return rate


def fires_from_mhclg(names, households):
    """Annual attended dwelling fires per household per district
    (MHCLG/Home Office incident-level data at LSOA for England,
    council-level for Scotland, FRA-level for Wales - fetch_fires.py,
    DATA_SOURCES.md #27).

    Returns the RAW annual dwelling-fire rate per household. As with
    theft, only the geography matters: main() normalises to a
    relativity and pins the level to the fire anchor triangle, so the
    attended-fire-to-claim propensity cancels and never needs to be
    known.

    Districts absent from fires.csv burned zero times in the source
    window (a real possibility for the smallest rural districts over 8
    years) and get rate 0 - but a file missing MANY districts is stale,
    not sparse, and stops the run. Rates are capped at the
    household-weighted 99.9th percentile: unlike theft there is no
    commercial contamination (these are dwelling fires by definition),
    but tiny-denominator districts still spike on a handful of
    incidents, and the same deterministic cap the theft peril uses is
    the guard.
    """
    path = os.path.join(DATA, "fires.csv")
    if not os.path.exists(path):
        raise SystemExit("data/fires.csv missing - run "
                         "scripts/fetch_fires.py first "
                         "(see DATA_SOURCES.md #27)")
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = float(row["fires_yr"])
    missing = [n for n in names if n not in table]
    if len(missing) > 0.2 * len(names):
        raise SystemExit(f"fires.csv is missing {len(missing)} of "
                         f"{len(names)} districts (first: {missing[:5]}) - "
                         "stale file? Rerun scripts/fetch_fires.py")
    hh = np.maximum(np.asarray(households, dtype=float), 1.0)
    rate = np.array([table.get(n, 0.0) for n in names]) / hh

    o = np.argsort(rate, kind="stable")   # stable: ties keep file order,
    cw = np.cumsum(hh[o])                 # so the cap is deterministic
    cap = float(rate[o][np.searchsorted(cw, 0.999 * cw[-1])])
    clipped = int((rate > cap).sum())
    rate = np.minimum(rate, cap)
    print(f"  fire: GB mean {np.average(rate, weights=hh):.4%}/yr; "
          f"cap {cap:.4%} (hh-weighted p99.9), {clipped} districts "
          f"clipped, {len(missing)} zero-fire districts")
    return rate


def children_from_census(names, households):
    """Share of households with dependent children per district
    (Census 2021 TS003 at LSOA for England & Wales, Census 2022 UV113
    at Output Area for Scotland - fetch_children.py, DATA_SOURCES.md
    #28). Drives the child-attributable slice of the AD frequency.

    Returns the RAW share in [0, 1]; main() normalises to a relativity
    around the exposure-weighted mean. Unlike the incident-count perils
    there is no winsorisation cap: a share is bounded by construction
    and the census denominators are the same households the exposure
    uses, so tiny-denominator spikes cannot occur.

    Districts absent from children.csv get the NATIONAL share (neutral
    relativity) - the census is complete, so absences are geography
    drift, not zero-child districts - but a file missing MANY
    districts is stale and stops the run.
    """
    path = os.path.join(DATA, "children.csv")
    if not os.path.exists(path):
        raise SystemExit("data/children.csv missing - run "
                         "scripts/fetch_children.py first "
                         "(see DATA_SOURCES.md #28)")
    tot, dep = {}, {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            tot[row["name"]] = float(row["hh_total"])
            dep[row["name"]] = float(row["hh_depchild"])
    missing = [n for n in names if n not in tot or tot[n] <= 0]
    if len(missing) > 0.2 * len(names):
        raise SystemExit(f"children.csv is missing {len(missing)} of "
                         f"{len(names)} districts (first: {missing[:5]}) - "
                         "stale file? Rerun scripts/fetch_children.py")
    national = sum(dep.values()) / sum(tot.values())
    share = np.array([dep[n] / tot[n] if tot.get(n, 0) > 0 else national
                      for n in names])
    hh = np.asarray(households, dtype=float)
    print(f"  ad: GB child-share mean {np.average(share, weights=hh):.1%}; "
          f"range {share.min():.1%}-{share.max():.1%}, "
          f"{len(missing)} districts at national share")
    return share


def ct_value_from_bands(names):
    """Property-value relativity per district from the council-tax band
    mix (fetch_ct_bands.py, DATA_SOURCES.md #30). Scales the flat
    national severities of the attritional perils: a district whose
    stock sits in the upper bands holds more rebuild and contents
    value per household than a bottom-band district.

    The file already carries the hard part: band weights are each
    nation's own statutory charge ratios, normalised WITHIN nation
    before any district (some straddle the English-Welsh border)
    averages over its small areas - the three band regimes are
    incompatible and must never compare directly. Here the raw
    relativity is only loaded; main() renormalises it per peril with
    claim weights so every ABI severity level stays pinned.

    Districts absent from ct_bands.csv get 1.0 (neutral) - the VOA/NRS
    stock tables are complete, so absences are non-residential or
    geography-drift districts - but a file missing MANY districts is
    stale and stops the run.
    """
    path = os.path.join(DATA, "ct_bands.csv")
    if not os.path.exists(path):
        raise SystemExit("data/ct_bands.csv missing - run "
                         "scripts/fetch_ct_bands.py first "
                         "(see DATA_SOURCES.md #30)")
    table = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            table[row["name"]] = float(row["sev_rel"])
    missing = [n for n in names if n not in table]
    if len(missing) > 0.2 * len(names):
        raise SystemExit(f"ct_bands.csv is missing {len(missing)} of "
                         f"{len(names)} districts (first: {missing[:5]}) - "
                         "stale file? Rerun scripts/fetch_ct_bands.py")
    rel = np.array([table.get(n, 1.0) for n in names])
    print(f"  ct bands: value relativity range {rel.min():.2f}-"
          f"{rel.max():.2f}, {len(missing)} districts neutral")
    return rel
