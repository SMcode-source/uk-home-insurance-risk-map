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


def erosion_from_ncerm(names):
    """Per-district coastal-erosion exposure (EA NCERM 2024; England).

    Returns (score, dict of fractions). The fractions are the share of
    district area projected to be lost to erosion by each epoch/scenario -
    see fetch_erosion.py, which allocates each frontage's length x
    recession rather than trusting the polygon area.

    The headline score uses the SMP (adopted Shoreline Management Plan)
    2105 scenario: that is what is expected to happen given the defences
    that are actually planned. The NFI (no further intervention) columns
    are carried alongside as the unmanaged worst case.

    Districts with no NCERM coverage - inland, and all of Wales, Scotland
    and Northern Ireland - are zero, not missing: they genuinely have no
    coastal erosion exposure in this dataset.
    """
    path = os.path.join(DATA, "erosion.csv")
    # Must stay in step with LAYERS in fetch_erosion.py. The *_lo / *_hi
    # columns are the 0th and 95th-percentile climate allowances on the
    # 2105 epoch; the unsuffixed ones are the 70th (central) case.
    cols = ["er_smp55", "er_smp105", "er_nfi55", "er_nfi105",
            "er_smp105_lo", "er_smp105_hi", "er_nfi105_lo", "er_nfi105_hi",
            "er_gi"]
    if not os.path.exists(path):
        print("  erosion.csv missing -> zero erosion exposure "
              "(run scripts/fetch_erosion.py)")
        z = np.zeros(len(names))
        return z, {c: z.copy() for c in cols}

    table = {}
    with open(path, newline="") as fh:
        rdr = csv.DictReader(fh)
        missing = [c for c in cols if c not in (rdr.fieldnames or [])]
        if missing:
            print(f"  erosion.csv predates {missing} -> zero "
                  "(rerun scripts/fetch_erosion.py to add them)")
        for row in rdr:
            table[row["name"]] = [float(row.get(c) or 0.0) for c in cols]
    arr = np.array([table.get(n, [0.0] * len(cols)) for n in names])
    out = {c: arr[:, i] for i, c in enumerate(cols)}

    coastal = int((out["er_nfi105"] > 0).sum())
    ref = max(np.percentile(out["er_smp105"], 99.5), 1e-9)
    score = np.clip(np.sqrt(out["er_smp105"] / ref), 0, 1)
    print(f"  erosion: {coastal}/{len(names)} districts with NCERM exposure; "
          f"SMP-2105 max {out['er_smp105'].max():.3%} of district area")
    return score, out
