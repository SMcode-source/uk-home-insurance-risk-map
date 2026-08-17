"""Build the UK postcode-district risk model for home insurance.

Pipeline:
  1. Load ~2,700 postcode-district polygons (one GeoJSON per postcode area).
  2. Score each district on five perils from REAL open data (see
     scores_real.py):
       - subsidence  : BGS 625k bedrock geology classified for shrink-swell
                       susceptibility, area-weighted per district, then
                       modified by the 625k SUPERFICIAL deposits that
                       overlie it (clay-with-flints and lacustrine clay
                       raise it, glacial sand and gravel lower it) at a
                       bounded weight, because 625k publishes no thickness.
                       Peat is excluded: it subsides by consolidation and
                       oxidation, not shrink-swell.
       - weather     : Met Office grids (winter wind, wind-driven rain
                       index, >=10mm rain days, annual precipitation)
                       interpolated to district centroids
       - flood       : EA / NRW / SEPA flood-zone extents rasterised to
                       per-district area fractions, with surface-water
                       severity conditioned on the EA depth bands
       - groundwater : EA groundwater flood alert areas
       - erosion     : EA NCERM coastal frontages (England) — reported
                       separately, see below
  3. Model per-district annual aggregate losses for each peril (compound
     frequency-severity marginals) and join them with a 5-dim C-vine copula
     (weather at the root; Gumbel pairs weather-flood, weather-groundwater,
     weather-subsidence and weather-erosion; Gaussian pairs given weather)
     — with 5-dim-Gaussian and independence runs for comparison.
  4. Band districts into 10 rating groups on the technical premium
     (expected loss + cost of capital on the 1-in-200 joint loss).
  5. Write districts_risk.geojson for the map front-end.

Coastal erosion is modelled in the vine but deliberately EXCLUDED from
`premium` and from the good-year/bad-year view. Gradual erosion is not
covered by standard UK household policies, so pricing it as an insured
loss would be wrong; and it is a chronic process rather than an event, so
it has no bad years. It is carried as `el_er` / `er_*` for the blight and
valuation exposure it genuinely represents.

The hazard inputs are real (BGS + Met Office + EA/NRW/SEPA, OGL); the
marginal loss frequencies/severities and the copula theta remain
assumptions — calibrate those to claims data for production use.
"""

import glob
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy import stats

from scores_real import (subsidence_score, weather_from_metoffice,
                         flood_from_agencies, groundwater_from_ea,
                         erosion_from_ncerm, sw_depth_severity, load_country,
                         theft_from_police, frost_from_metoffice,
                         fires_from_mhclg,
                         flood_future, flood_score_from_fractions,
                         EROSION_HORIZON_YEARS)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "districts_risk.geojson")

N_SIM = 20_000          # simulated years per district
# Districts per simulation batch. Each batch holds ~25 transient
# (BATCH x N_SIM) float64 arrays, so 250 needs ~1 GB and thrashes on a
# 8 GB machine; 80 keeps the working set to a few hundred MB and is
# markedly faster in wall-clock terms despite more batches.
BATCH = 80
RNG_SEED = 42
# Worker threads for the batch loop. Measured on a 10-core i7-1255U over
# 12 production-shaped batches: 1 thread 136.2s, 4 threads 39.8s (3.4x),
# 6 threads 30.7s (4.4x). Measure at REAL scale if you retune this - a
# 3-batch micro-benchmark showed no gain at all and was simply too small
# to fill the pool.
#
# Capped at 6 rather than the full core count because the loop is
# memory-bound and this is a laptop that has to stay usable; adaptive so a
# 4-vCPU GitHub Actions runner uses 4 rather than oversubscribing.
N_THREADS = (int(os.environ.get("UKRISK_THREADS", "0"))
             or min(6, os.cpu_count() or 1))

# Columns written to districts_risk.geojson, in order. Kept at module level
# so main() can check them BEFORE simulating: a missing column used to
# surface only at the final write, which on a 55-minute run means losing
# the whole thing to a typo.
OUTPUT_COLUMNS = [
    "name", "area", "country", "households",
    "sub_score", "wx_score", "fl_score", "gw_score",
    "geol", "sup_geol", "sup_frac",
    "wind_ms", "wdr_idx", "rain10_days", "precip_mm",
    "gust_rp50",
    "f_high", "f_low", "sw_high", "sw_low", "gw_frac",
    "sw_sev", "sw_depth_m", "th_rate", "frost_days", "eow_rate",
    "fire_rate",
    "er_score", "er_smp55", "er_smp105", "er_nfi55", "er_nfi105",
    "er_smp105_lo", "er_smp105_hi", "er_nfi105_lo", "er_nfi105_hi",
    "er_gi",
    "el_sub", "el_wx", "el_fl", "el_gw", "el_th", "el_eow", "el_fire",
    "el_er",
    "el_total", "el_total5", "var995_vine", "tvar99_vine",
    "tvar99_gauss",
    "tvar99_indep", "tvar99_vine5", "tvar99_indep5", "tvar99_euler",
    "capital",
    "el_total_cc", "capital_cc", "premium_cc", "cc_uplift_pct",
    "cc_covered",
    "uplift_pct", "tail_dep_wf", "tail_dep_ws",
    "tail_dep_wg", "tail_dep_we",
    "theta_wf", "theta_ws", "theta_wg", "theta_we",
    "premium", "group", "geometry",
]

# Everything above that is produced later. Split by WHO produces it, because
# that is what makes the contract checkable: the two halves fail in different
# places and only one of them can be caught before the run starts.
#
# Returned by simulate(). Several of these are not in OUTPUT_COLUMNS and are
# deliberately kept anyway - see the note on var995_* in simulate().
SIMULATED_COLUMNS = {
    "el_sub", "el_wx", "el_fl", "el_gw", "el_th", "el_eow", "el_fire",
    "el_er",
    "el_total",
    "el_total5",
    "var995_vine", "var995_gauss", "var995_indep", "tvar99_vine",
    "tvar99_gauss", "tvar99_indep", "tvar99_vine5", "tvar99_indep5",
    "tvar99_euler", "el_year", "uplift_pct",
    "tail_dep_wf", "tail_dep_ws", "tail_dep_wg", "tail_dep_we",
    "theta_wf", "theta_ws", "theta_wg", "theta_we",
}
# Computed by main() itself, after simulating: the premium arithmetic and
# the climate-change repricing.
MAIN_COLUMNS = {
    "capital", "premium", "group",
    "el_total_cc", "capital_cc", "premium_cc", "cc_uplift_pct", "cc_covered",
}
DERIVED_COLUMNS = SIMULATED_COLUMNS | MAIN_COLUMNS


def check_scored_columns(gdf):
    """Fail fast if scoring did not produce everything the output needs.

    Only covers the SCORED half. The derived half cannot be checked here -
    nothing has simulated yet - so it is guarded instead by
    test_simulate_returns_the_columns_the_map_and_site_read, which runs the
    real simulate() on a one-district frame in about a second. That matters:
    a mistyped derived column surfaces only at the final GeoJSON write,
    which now comes after BOTH the present-day and the climate simulation,
    so it costs the whole ~110-minute run rather than the 55 that motivated
    this guard originally.
    """
    need = [c for c in OUTPUT_COLUMNS if c not in DERIVED_COLUMNS]
    missing = [c for c in need if c not in gdf.columns]
    if missing:
        raise SystemExit(
            f"scoring produced no {missing}.\n"
            "OUTPUT_COLUMNS lists a column nothing writes - check that the "
            "matching fetch script has been run and that its reader in "
            "scores_real.py knows about the column.")
    print(f"  output contract: {len(need)} scored columns present, "
          f"{len(DERIVED_COLUMNS & set(OUTPUT_COLUMNS))} to come from the "
          f"simulation")


def check_simulated_columns(sim):
    """Fail as soon as the first simulation returns, not at the final write.

    Belt and braces behind the unit test: if the present-day run comes back
    short, stopping here costs 55 minutes instead of letting the climate run
    double it before the GeoJSON write notices.
    """
    missing = sorted(SIMULATED_COLUMNS - set(sim))
    if missing:
        raise SystemExit(
            f"simulate() returned no {missing}.\n"
            "SIMULATED_COLUMNS and simulate()'s `out` dict have drifted "
            "apart - add the column to both, or drop it from both.")

# ---------------------------------------------------------------- load


def load_districts() -> gpd.GeoDataFrame:
    """SECTOR-MODEL BRANCH: the geography atom is the postcode sector.

    Same signature and column contract as the district loader on main —
    `name` is the unit key (now e.g. "YO25 6", with a space), `area` the
    postcode area — so every consumer downstream is unchanged. The
    polygons are the derived sector partition (derive_sectors.py):
    10,398 sectors nested exactly inside the 2,736 districts, which is
    what makes sector results aggregable back to the published district
    model for validation. `district` and `n_units` ride along for that.
    """
    gdf = gpd.read_file(os.path.join(DATA, "sectors_gb.gpkg"))
    gdf = gdf.rename(columns={"sector": "name"})
    gdf["area"] = gdf["name"].str.extract(r"^([A-Z]{1,2})", expand=False)
    gdf = gdf.to_crs(4326)
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    return gdf[["name", "area", "district", "n_units", "geometry"]]


# ------------------------------------------------- marginal loss models
# Annual aggregate loss per policy, modelled as at-most-one claim per year
# (adequate at district level for banding): L = B(p) * LogNormal(mu, sigma).
# Inverse CDF of this mixed distribution:
#   F^-1(u) = 0                          for u <= 1 - p
#           = LN^-1((u - (1-p)) / p)     otherwise


def load_households(names):
    """Households per district (ONS/NRS census; see fetch_households.py).

    Districts with no figure - a handful of tiny or non-residential ones -
    get the 10th-percentile count rather than zero, so they still carry a
    little weight instead of vanishing from the portfolio.
    """
    import csv as _csv
    path = os.path.join(DATA, "households.csv")
    if not os.path.exists(path):
        print("  households.csv missing -> equal weighting "
              "(run scripts/fetch_households.py)")
        return np.ones(len(names))
    table = {}
    with open(path, newline="") as fh:
        for row in _csv.DictReader(fh):
            table[row["name"]] = float(row["households"])
    vals = np.array([table.get(n, np.nan) for n in names])
    miss = np.isnan(vals)
    if miss.any():
        vals[miss] = np.nanpercentile(vals, 10)
        print(f"  households: {miss.sum()} districts without a count "
              f"-> 10th-percentile fallback")
    vals = np.maximum(vals, 1.0)
    print(f"  exposure: {vals.sum():,.0f} households across {len(names)} "
          f"districts (max {vals.max():,.0f})")
    return vals


# ------------------------------------------- calibration to UK aggregates
# Published ABI figures for 2025 (see README "Calibration"): home insurers
# paid ~£3.4bn across ~560,000 claims; the ABI premium tracker covers
# ~15.5m policies. Severity means are ABI averages where published.
# ABI domestic figures for 2025, BY PERIL - this is what makes the level
# meaningful. Calibrating to the all-claims total would be wrong: the ABI's
# 560,000 home claims are mostly escape of water, theft, fire and accidental
# damage, none of which this model covers, so scaling four catastrophe
# perils up to that frequency inflates them several-fold.
POLICIES = 15_500_000                     # ABI premium tracker coverage
ABI = dict(
    storm_paid=244e6, sev_weather=2_450.0,          # storm damage to homes
    flood_paid=312e6, sev_flood=30_000.0,           # domestic flood claims
    subsidence_paid=307e6, sev_subsidence=17_820.0,  # domestic subsidence
    # Groundwater is not reported separately (it sits inside flood); modelled
    # as a small documented addition rather than calibrated.
    sev_groundwater=20_000.0,
    # Internal split of the flood severity: fluvial/tidal events cost more
    # than surface-water ones, and the frequency-weighted blend is what is
    # held to the published £30,000 average.
    sev_flood_fluvial=35_000.0, sev_surface_water=18_000.0,
    total_home_paid=3.4e9,                # all home claims, for context only
    # Theft. The ABI stopped publishing an annual theft-paid total; the
    # last public figure is ~£450m (2018, formerly on the ABI theft
    # page). Severity is the current published average (£3,800, 2025).
    # Mixing vintages puts the implied frequency (0.76%/policy) between
    # 2018's (~0.97%) and what today's would be if claims fell with
    # recorded burglary (~0.58%) - that envelope is the documented
    # uncertainty on the theft LEVEL. See DATA_SOURCES.md #25.
    theft_paid=450e6, sev_theft=3_800.0,
    # Escape of water. Like theft, the ABI publishes no annual per-peril
    # total any more; the standing figure is "£1.8m every day" (~£657m/yr,
    # quoted since ~2017). The triangle closes: EoW was 29.3% of 2025's
    # 560,000 home claims (~164,000), and 657m/164k = £4,005 average -
    # self-consistent, so the implied frequency is 1.06%/policy. Aviva's
    # 2025 book average (£8,595) shows the insurer-level spread; the
    # vintage mixing is the documented envelope on the EoW LEVEL, same
    # as theft. See DATA_SOURCES.md #26.
    eow_paid=657e6, sev_eow=4_000.0,
    # Fire. No public per-peril total exists at all any more (the 2025
    # full-year and Q1 2026 ABI releases were checked - fire appears
    # only as "lower fire and explosion payouts were the main driver of
    # the decline", never a number), so the level is a TRIANGLE with
    # each leg from a different source: frequency from Home Office
    # FIRE0201 - 31,001 attended GB dwelling fires in 2024/25 over the
    # tracker's 15.5m policies = 0.20%/policy, treating attended count
    # as claim-count proxy (unattended small claims vs uninsured/
    # below-excess attended fires roughly offset); severity from the
    # ABI-attributed "average payout for fire damage £10,200-£11,000"
    # (undated, ~2019 vintage, still cited 2023-25), indexed ~+27% for
    # claims inflation to £14,000. The implied £434m/yr is 12.8% of
    # 2025's £3.4bn home paid - inside the remainder envelope after
    # EoW, weather, subsidence and theft. See DATA_SOURCES.md #27.
    fire_paid=434e6, sev_fire=14_000.0,
    # Coastal erosion is a TOTAL loss of the property, not a repair, so its
    # severity is a sum insured rather than an average claim. There is no
    # ABI figure to calibrate against, because gradual erosion is excluded
    # from standard household cover - which is exactly why this peril is
    # reported separately from the insured premium throughout.
    sev_erosion=250_000.0,
)
# Target per-policy frequency for each modelled peril = paid / severity / policies
ABI_TARGET_FREQ = {
    "wx": ABI["storm_paid"] / ABI["sev_weather"] / POLICIES,
    "fl": ABI["flood_paid"] / ABI["sev_flood"] / POLICIES,
    "sub": ABI["subsidence_paid"] / ABI["sev_subsidence"] / POLICIES,
    "th": ABI["theft_paid"] / ABI["sev_theft"] / POLICIES,
    "eow": ABI["eow_paid"] / ABI["sev_eow"] / POLICIES,
    "fire": ABI["fire_paid"] / ABI["sev_fire"] / POLICIES,
}
ABI_LOSS_PER_POLICY = (ABI["storm_paid"] + ABI["flood_paid"]
                       + ABI["subsidence_paid"]
                       + ABI["theft_paid"] + ABI["eow_paid"]
                       + ABI["fire_paid"]) / POLICIES

# lognormal median that gives the target MEAN for a given sigma
_median_for_mean = lambda mean, sigma: mean / np.exp(sigma ** 2 / 2)

# One multiplier per peril, set by calibrate_frequency() before simulating.
FREQ_SCALE = {"sub": 1.0, "wx": 1.0, "fl": 1.0, "gw": 1.0, "th": 1.0,
              "eow": 1.0, "fire": 1.0}
GW_SHARE_OF_FLOOD = 0.10      # groundwater not published separately


def calibrate_frequency(gdf):
    """Scale each peril's claim frequency to its published ABI level.

    Only the LEVEL of each peril moves. The relative ranking of districts
    within a peril - which is what the hazard data determines, and the whole
    point of the model - is untouched.
    """
    global FREQ_SCALE
    FREQ_SCALE = {"sub": 1.0, "wx": 1.0, "fl": 1.0, "gw": 1.0, "th": 1.0,
                  "eow": 1.0, "fire": 1.0}
    m = marginal_params(_fields(gdf))
    # ABI totals are national, so the average must be exposure-weighted:
    # a district with 40,000 households counts 40,000 times more than one
    # with a single household.
    w = gdf["households"].values
    raw = {"sub": float(np.average(m["p_sub"], weights=w)),
           "wx": float(np.average(m["p_wx"], weights=w)),
           "fl": float(np.average(m["p_fl"], weights=w)),
           "gw": float(np.average(m["p_gw"], weights=w)),
           "th": float(np.average(m["p_th"], weights=w)),
           "eow": float(np.average(m["p_eow"], weights=w)),
           "fire": float(np.average(m["p_fire"], weights=w))}
    for k in ("sub", "wx", "fl", "th", "eow", "fire"):
        FREQ_SCALE[k] = ABI_TARGET_FREQ[k] / raw[k]
    # groundwater has no published total; peg it to a share of flood
    FREQ_SCALE["gw"] = (GW_SHARE_OF_FLOOD * ABI_TARGET_FREQ["fl"]) / raw["gw"]
    for k in ("wx", "fl", "sub", "th", "eow", "fire"):
        print(f"  {k:4} frequency {raw[k]:.3%} -> ABI {ABI_TARGET_FREQ[k]:.3%}"
              f"  (x{FREQ_SCALE[k]:.3f})")
    print(f"  gw   frequency pegged at {GW_SHARE_OF_FLOOD:.0%} of flood")
    return FREQ_SCALE


# How national each peril's bad years are (see year view in simulate()).
# The base ratios are physical - storms, droughts and aquifer recharge are
# large-scale, flooding is more localised - and the common multiplier is
# calibrated so a 1-in-100 year does not claim implausibly widely.
SPATIAL_BASE = {"w": 0.50, "f": 0.40, "s": 0.60, "g": 0.70}
SPATIAL_SCALE = 1.0
TAIL_FREQ_RATIO = 2.0        # 1-in-100 year claims ~2x the average year
# Theft's systemic loading is FIXED and deliberately NOT in SPATIAL_BASE:
# calibrate_spatial solves for how widely WEATHER claims cluster in a bad
# year (the TAIL_FREQ_RATIO target is a storm phenomenon), and letting the
# solver rescale theft would couple burglary to that target.
#
# The value is derived, not felt. At rare-event thresholds a factor
# loading has enormous leverage: under the factor model the national
# claim-count CV over systemic years is approximately
#   CV = sqrt(w) * phi(z_p) / p,   z_p = Phi^-1(1-p)
# and at p = 0.76% that is 2.75*sqrt(w). Recorded national burglary
# moves +-10-15% year to year around trend (ONS series), so targeting
# CV = 0.10 gives w = (0.10/2.75)^2 = 0.0013 - a 1-in-100 systemic
# year then claims ~1.3x the average year, which is what burglary
# waves actually look like. The first evidence run used w = 0.20 on
# "weakly systemic" intuition; that implied worst years claiming
# 8-14x the mean - a national crime wave no data shows - and charged
# +GBP 13/policy of phantom capital for it.
W_THEFT = 0.0013
# Escape of water's loading comes from the same derivation but a very
# different record. The freeze events are genuinely systemic: winter 2010
# put 103,000 burst-pipe claims (£680m) through in SIX WEEKS - a normal
# year's EoW paid on top of the base - so the worst year in the record
# cost ~2x the mean, and Q1 2018 (Beast from the East, £193m in the
# quarter) ~1.3x. Targeting the 1-in-100 year at 2x mean:
#   CV * z(0.99) = 1.0  ->  CV = 0.43
#   CV = sqrt(w) * phi(z_p)/p, and at p = 1.06% phi(z_p)/p = 2.65
#   -> sqrt(w) = 0.43/2.65 -> w = 0.026
# Twenty times theft's loading, still an order of magnitude below the
# weather perils' solved values - which is the right ordering: freeze
# years are real national events, but most EoW is uncorrelated plumbing
# failure. Unlike theft, EoW therefore SHOULD show up in capital.
W_EOW = 0.026
# The freeze-attributable share of a NORMAL year's EoW claims - the only
# slice that varies spatially (with air-frost days). 25% of EoW claims
# happen July-September (Aviva 2026) and the January peak is freeze-
# driven; ~15% is the defensible middle. The base is FLAT: plumbing and
# appliance failure has no open spatial predictor until Phase 2 gives
# dwelling age (EPC) and a commercial denominator (VOA).
EOW_FREEZE_SHARE = 0.15
# Fire's loading comes from the same derivation as theft's and EoW's,
# and lands even lower than theft. The FIRE0201 national series
# (1981/82-2025/26) shows a steady secular DECLINE of -2.5%/yr - a
# trend, not a shock - and once that is removed the year-on-year
# residuals over the consistent-methodology era (2010/11-2024/25 GB)
# have CV = 0.020, worst single year -3.7%. Even the 2022 heatwave
# summer barely registers at annual grain. Targeting that CV:
#   CV = sqrt(w) * phi(z_p)/p, and at p = 0.20% phi(z_p)/p = 3.17
#   -> sqrt(w) = 0.020/3.17 -> w = 0.000039
# Thirty-three times below theft's loading: fire is the closest thing
# in the book to a purely idiosyncratic peril, so it buys essentially
# NO systemic capital - it diversifies the cat tail instead. That is a
# finding the data forces, not a modelling shortcut.
W_FIRE = 0.000039


def calibrate_spatial(gdf, target_ratio=TAIL_FREQ_RATIO):
    """Pick the spatial loading multiplier analytically.

    Under the factor model a district claims when
        Phi(sqrt(w)*z + sqrt(1-w)*eps) > 1 - p,
    so conditional on the systemic factor being at z the claim probability
    is Phi((sqrt(w)*z - Phi^-1(1-p)) / sqrt(1-w)). Averaging over districts
    gives the national claim frequency in a year of severity z; we solve for
    the multiplier that puts the 1-in-100 year (z = Phi^-1(0.99)) at
    `target_ratio` times the mean year. No simulation needed.
    """
    global SPATIAL_SCALE
    m = marginal_params(_fields(gdf))
    # erosion is deliberately absent: the spatial loading calibration is
    # about how widely a bad YEAR claims, and erosion is chronic rather
    # than event-driven (see year_analysis).
    perils = [("s", m["p_sub"]), ("w", m["p_wx"]),
              ("f", m["p_fl"]), ("g", m["p_gw"])]
    expo = gdf["households"].values
    mean_freq = sum(float(np.average(p, weights=expo)) for _, p in perils)
    z99 = stats.norm.ppf(0.99)

    def tail_freq(lam):
        total = 0.0
        for key, p in perils:
            w = min(SPATIAL_BASE[key] * lam, 0.98)
            thr = stats.norm.ppf(np.clip(1 - p, 1e-12, 1 - 1e-12))
            total += float(np.average(stats.norm.cdf(
                (np.sqrt(w) * z99 - thr) / np.sqrt(1 - w)), weights=expo))
        return total

    lo, hi = 0.01, 1.0
    if tail_freq(hi) <= target_ratio * mean_freq:
        SPATIAL_SCALE = hi
    else:
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if tail_freq(mid) > target_ratio * mean_freq:
                hi = mid
            else:
                lo = mid
        SPATIAL_SCALE = 0.5 * (lo + hi)
    got = tail_freq(SPATIAL_SCALE) / mean_freq
    print(f"  spatial calibration: loading x{SPATIAL_SCALE:.3f} -> "
          f"1-in-100 year claims {got:.2f}x the mean year "
          f"({mean_freq:.2%} -> {got * mean_freq:.2%})")
    return SPATIAL_SCALE


def marginal_params(f):
    """Per-district claim frequency and severity for each peril.

    `f` is a mapping of same-shaped per-district arrays: sub, wx, f_high,
    f_low, sw_high, sw_low, gw_frac, sw_sev (depth severity multiplier)
    and er (erosion zone fraction). Passing a mapping rather than nine
    positional arguments keeps the three call sites legible.

    Relative frequencies come from the hazard scores; the overall LEVEL is
    set by FREQ_SCALE (calibrate_frequency). Severity medians are chosen so
    each lognormal's MEAN matches the published ABI average claim.
    """
    sub, wx = f["sub"], f["wx"]
    p_sub = 0.002 + 0.028 * sub ** 1.5
    p_wx = 0.010 + 0.090 * wx ** 1.2
    # river/sea flood frequency from actual zone fractions: ~1.5%/yr for a
    # property in the defended 1in100/200 zone, ~0.3%/yr in the rest of
    # the 1in1000 envelope, 0.05%/yr background
    p_rs = (0.0005 + 0.015 * f["f_high"]
            + 0.003 * np.maximum(f["f_low"] - f["f_high"], 0))
    # surface water: ~1%/yr in the >=1% AEP zone, shallower/cheaper events
    p_sw = (0.010 * f["sw_high"]
            + 0.002 * np.maximum(f["sw_low"] - f["sw_high"], 0))
    p_fl = p_rs + p_sw
    p_gw = 0.0003 + 0.008 * f["gw_frac"]
    # Coastal erosion. A property inside the strip projected to be lost by
    # the 2105 epoch is lost within that horizon, so the annual hazard is
    # the zone fraction spread over the horizon. Two assumptions worth
    # stating: households are taken as spread uniformly across the district
    # (coastal populations actually cluster towards the shore, so this if
    # anything understates), and the SMP scenario is used, i.e. defences
    # are assumed to be maintained as currently planned.
    p_er = f["er"] / EROSION_HORIZON_YEARS
    # Theft frequency is the district's burglary rate itself (police.uk,
    # see theft_from_police): the geography IS the relativity, no
    # transform. FREQ_SCALE["th"] then absorbs the burglary-to-claim
    # propensity, which is why that unpublished number never appears.
    p_th = f["th"]
    # Escape of water: eow_rate is precomputed in main() as anchor level
    # x frost relativity (flat base + freeze-sensitive slice), because
    # the relativity's normalisation needs households, which this
    # function never sees - a mean taken HERE would make the marginal
    # depend on the batch composition. It arrives as a RATE (~1%), like
    # th_rate, so calibration solves against real relativities rather
    # than the 0.5 clip below - a raw O(1) relativity would saturate the
    # clip during the calibration pass and come out 2x hot with the
    # geography flattened.
    p_eow = f["eow"]
    # Fire: fire_rate is precomputed in main() as anchor level x the
    # district's dwelling-fire relativity (MHCLG incident data), for
    # the same reason as eow_rate - the relativity's normalisation
    # needs households, and a per-chunk mean here would make the
    # marginal depend on batch composition. It arrives as a RATE
    # (~0.2%), so the 0.5 clip below never bites during calibration.
    p_fire = f["fire"]

    s_sub, s_wx, s_fl, s_gw, s_er = 0.90, 1.10, 0.90, 0.80, 0.35
    # Theft severity spread: most claims are a few thousand (forced entry
    # damage + electronics), a tail of jewellery/watch losses reaches
    # tens of thousands. sigma=1.0 puts ~5% of claims above 4x the mean,
    # in line with the shape the ABI's high-value-theft commentary
    # describes; the MEAN is pinned to the published average regardless.
    s_th = 1.00
    # EoW severity spread: the bulk is trace-and-access plus drying out
    # (low thousands), the tail is full ground-floor reinstatement after
    # an unattended leak. sigma=1.0 (same shape as theft); the MEAN is
    # pinned to the £4,000 the anchor triangle implies.
    s_eow = 1.00
    # Fire severity spread: the widest of the attritional perils. The
    # £14,000 mean mixes a majority of contained kitchen/appliance
    # fires (low thousands: smoke damage, one room) with a real tail
    # of whole-room and whole-house losses reaching six figures.
    # sigma=1.3 puts ~2% of claims above £100k - consistent with the
    # severe-fire share in Home Office damage-area data (FIRE0204:
    # most dwelling fires are confined to the item or room of origin,
    # a few percent spread further). The MEAN stays pinned to the
    # anchor regardless.
    s_fire = 1.30
    sev_sub = dict(mu=np.log(_median_for_mean(ABI["sev_subsidence"], s_sub)),
                   sigma=s_sub)
    sev_wx = dict(mu=np.log(_median_for_mean(ABI["sev_weather"], s_wx)),
                  sigma=s_wx)
    # flood severity: frequency-weighted blend of fluvial/tidal and the
    # shallower, cheaper surface-water events. The surface-water leg is
    # scaled by the district's depth severity multiplier (EA depth bands,
    # see sw_depth_severity) - deep water damages a house far more than a
    # few centimetres, and the multiplier is normalised to leave the
    # national average, and so the ABI calibration, unchanged.
    mu_rs = np.log(_median_for_mean(ABI["sev_flood_fluvial"], s_fl))
    mu_sw = np.log(_median_for_mean(
        ABI["sev_surface_water"] * f["sw_sev"], s_fl))
    mu_fl = (p_rs * mu_rs + p_sw * mu_sw) / np.maximum(p_fl, 1e-12)
    sev_fl = dict(mu=mu_fl, sigma=s_fl)
    sev_gw = dict(mu=np.log(_median_for_mean(ABI["sev_groundwater"], s_gw)),
                  sigma=s_gw)
    # erosion destroys the property outright, so severity is a sum insured
    # with little spread rather than a repair-cost distribution
    sev_er = dict(mu=np.log(_median_for_mean(ABI["sev_erosion"], s_er)),
                  sigma=s_er)
    sev_th = dict(mu=np.log(_median_for_mean(ABI["sev_theft"], s_th)),
                  sigma=s_th)
    sev_eow = dict(mu=np.log(_median_for_mean(ABI["sev_eow"], s_eow)),
                   sigma=s_eow)
    sev_fire = dict(mu=np.log(_median_for_mean(ABI["sev_fire"], s_fire)),
                    sigma=s_fire)

    k = FREQ_SCALE
    return dict(
        p_sub=p_sub * k["sub"], p_wx=p_wx * k["wx"], p_fl=p_fl * k["fl"],
        p_gw=p_gw * k["gw"], p_er=p_er,     # erosion is not ABI-calibrated
        p_th=np.minimum(p_th * k["th"], 0.5),
        p_eow=np.minimum(p_eow * k["eow"], 0.5),
        p_fire=np.minimum(p_fire * k["fire"], 0.5),
        sev_sub=sev_sub, sev_wx=sev_wx, sev_fl=sev_fl, sev_gw=sev_gw,
        sev_er=sev_er, sev_th=sev_th, sev_eow=sev_eow, sev_fire=sev_fire)


def _fields(src):
    """Pull the marginal_params inputs out of a GeoDataFrame/chunk."""
    return {k: src[v].values for k, v in
            [("sub", "sub_score"), ("wx", "wx_score"), ("f_high", "f_high"),
             ("f_low", "f_low"), ("sw_high", "sw_high"), ("sw_low", "sw_low"),
             ("gw_frac", "gw_frac"), ("sw_sev", "sw_sev"), ("er", "er_frac"),
             ("th", "th_rate"), ("eow", "eow_rate"),
             ("fire", "fire_rate")]}


def inv_mixed_cdf(u, p, mu, sigma):
    """Quantile of Bernoulli(p) * LogNormal(mu, sigma).

    mu may be a scalar or an array broadcastable to u's shape.
    """
    loss = np.zeros_like(u)
    hit = u > (1.0 - p)
    uu = (u[hit] - (1.0 - p[hit])) / p[hit]
    uu = np.clip(uu, 1e-12, 1 - 1e-12)
    mu_e = np.broadcast_to(mu, u.shape)[hit] if np.ndim(mu) else mu
    loss[hit] = np.exp(mu_e + sigma * stats.norm.ppf(uu))
    return loss


# ------------------------------------------------------- vine copula
# C-vine on (W=weather, F=flood, G=groundwater, S=subsidence,
# E=coastal erosion), root W:
#   tree 1:  c_WF Gumbel(theta_wf)   storm rain drives flood - strongest
#            c_WG Gumbel(theta_wg)   prolonged rain recharges aquifers
#            c_WS Gumbel(theta_ws)   shared climate-volatility driver
#            c_WE Gumbel(theta_we)   cliff and beach retreat happens in
#                                    storms, not on calm days
#   tree 2 (given W, second-level root F):
#            c_FG|W Gaussian(0.25)   wet winters: fluvial + groundwater
#            c_FS|W Gaussian(0.15)   weak residual dependence
#            c_FE|W Gaussian(0.35)   coastal flooding and erosion share the
#                                    same storm-surge events, so this is the
#                                    strongest of the tree-2 pairs
#   tree 3:  independence
# Gumbel pairs are upper-tail dependent: extreme years hit the perils
# together. Kendall tau = 1 - 1/theta; lambda_U = 2 - 2^(1/theta).

RHO_SF_GIVEN_W = 0.15
RHO_FG_GIVEN_W = 0.25
RHO_FE_GIVEN_W = 0.35


def theta_ws(sub, wx):
    return np.clip(1.25 + 1.25 * np.sqrt(sub * wx), 1.0, 2.5)


def theta_wf(wx, fl):
    return np.clip(1.40 + 1.60 * np.sqrt(wx * fl), 1.0, 3.0)


def theta_wg(wx, gw):
    # groundwater responds to cumulative winter rainfall
    return np.clip(1.30 + 1.10 * np.sqrt(wx * gw), 1.0, 2.4)


def theta_we(wx, er):
    # erosion is storm-driven: the retreat happens in a handful of surge
    # events, so the tail dependence with weather is meaningful
    return np.clip(1.35 + 1.30 * np.sqrt(wx * er), 1.0, 2.6)


def _h_gumbel_u_parts(u, th):
    """The part of h_gumbel that depends only on (u, th).

    Hoisted out of the bisection below, which calls h_gumbel 40 times with
    u and th held fixed - so clipping u, taking its log and raising it to
    both powers was being redone 40 times over. This is the model's hot
    loop (the erosion conditional made it three per batch), so it is worth
    the extra function.
    """
    u = np.clip(u, 1e-12, 1 - 1e-12)
    lu = -np.log(u)
    return u, lu ** th, lu ** (th - 1)


def _h_gumbel_v(v, u, lu_th, lu_pow, th):
    """h_gumbel given the precomputed u-side parts.

    The expression is written to match the original operation order
    EXACTLY - `... * lu_pow / u * ...`, not `... * (lu_pow / u) * ...`.
    Floating-point multiply and divide are not associative, so regrouping
    would shift the last bit, and a last bit here propagates through
    20,000 simulated years into premiums and rating deciles.
    """
    v = np.clip(v, 1e-12, 1 - 1e-12)
    lv = -np.log(v)
    s = lu_th + lv ** th
    return np.exp(-s ** (1 / th)) * lu_pow / u * s ** (1 / th - 1)


def h_gumbel(v, u, th):
    """h(v|u) = dC(u,v)/du for the Gumbel copula (conditional CDF of v)."""
    return _h_gumbel_v(v, *_h_gumbel_u_parts(u, th), th)


def hinv_gumbel(t, u, th, iters=40):
    """Invert h_gumbel in v by bisection (h is increasing in v)."""
    u_c, lu_th, lu_pow = _h_gumbel_u_parts(u, th)
    lo = np.full(np.broadcast_shapes(t.shape, u.shape), 1e-9)
    hi = np.full_like(lo, 1 - 1e-9)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        below = _h_gumbel_v(mid, u_c, lu_th, lu_pow, th) < t
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return 0.5 * (lo + hi)


def sample_gumbel(theta, base):
    """Marshall–Olkin sampling with common random numbers.

    base: dict of shape-(N,) draws — Theta~U(0,pi), W,E1,E2 ~ Exp(1).
    theta: shape (D, 1). Returns U1, U2 of shape (D, N).
    """
    alpha = 1.0 / theta
    th, w = base["Theta"], base["W"]
    # Chambers-Mallows-Stuck positive alpha-stable
    v = (np.sin(alpha * th) / np.sin(th) ** (1 / alpha)) * (
        np.sin((1 - alpha) * th) / w
    ) ** ((1 - alpha) / alpha)
    u1 = np.exp(-((base["E1"] / v) ** alpha))
    u2 = np.exp(-((base["E2"] / v) ** alpha))
    return u1, u2


def sample_vine(t_ws, t_wf, t_wg, t_we, base):
    """Sample (u_w, u_f, u_g, u_s, u_e) from the C-vine with common random
    numbers.

    (W,F) drawn jointly via Marshall-Olkin; G, S and E conditionally:
      v   = h_{F|W}(u_f | u_w)                (tree-1 pseudo-observation)
      z_x = h^{-1}_gauss(w | v; rho_xF|W)     (tree 2, closed form)
      u_x = h^{-1}_{x|W}(z_x | u_w; theta_wx) (tree 1, bisection)
    Tree 3 is independence, so nothing further is needed.
    """
    u_w, u_f = sample_gumbel(t_wf, base)
    v = np.clip(h_gumbel(u_f, u_w, t_wf), 1e-9, 1 - 1e-9)
    zv = stats.norm.ppf(v)

    def conditional(rho, z_indep, t_wx):
        z = stats.norm.cdf(rho * zv + np.sqrt(1 - rho ** 2) * z_indep)
        return hinv_gumbel(np.clip(z, 1e-9, 1 - 1e-9), u_w, t_wx)

    u_g = conditional(RHO_FG_GIVEN_W, base["Z4"], t_wg)
    u_s = conditional(RHO_SF_GIVEN_W, base["Z3"], t_ws)
    u_e = conditional(RHO_FE_GIVEN_W, base["Z5"], t_we)
    return u_w, u_f, u_g, u_s, u_e


def sample_gaussian5(t_ws, t_wf, t_wg, t_we, base):
    """5-dim Gaussian copula, tau-matched pairwise to the vine (same
    rank correlations, no tail dependence). Order: (W, F, G, S, E)."""
    tau2rho = lambda t: np.sin(np.pi * (1 - 1 / t) / 2).ravel()
    r_wf, r_ws = tau2rho(t_wf), tau2rho(t_ws)
    r_wg, r_we = tau2rho(t_wg), tau2rho(t_we)
    # unconditional pairwise correlations implied by the vine (partial
    # correlation recursion; every tree-3 partial correlation is zero)
    orth = lambda a, b: np.sqrt((1 - a ** 2) * (1 - b ** 2))
    r_fs = r_wf * r_ws + RHO_SF_GIVEN_W * orth(r_wf, r_ws)
    r_fg = r_wf * r_wg + RHO_FG_GIVEN_W * orth(r_wf, r_wg)
    r_fe = r_wf * r_we + RHO_FE_GIVEN_W * orth(r_wf, r_we)
    r_gs = r_wg * r_ws + (RHO_FG_GIVEN_W * RHO_SF_GIVEN_W) * orth(r_wg, r_ws)
    r_ge = r_wg * r_we + (RHO_FG_GIVEN_W * RHO_FE_GIVEN_W) * orth(r_wg, r_we)
    r_se = r_ws * r_we + (RHO_SF_GIVEN_W * RHO_FE_GIVEN_W) * orth(r_ws, r_we)

    d = len(r_wf)
    R = np.empty((d, 5, 5))
    for i in range(5):
        R[:, i, i] = 1.0
    for i, j, r in [(0, 1, r_wf), (0, 2, r_wg), (0, 3, r_ws), (0, 4, r_we),
                    (1, 2, r_fg), (1, 3, r_fs), (1, 4, r_fe),
                    (2, 3, r_gs), (2, 4, r_ge), (3, 4, r_se)]:
        R[:, i, j] = R[:, j, i] = r
    L = np.linalg.cholesky(R)                      # (d, 5, 5)
    Z = np.stack([base["Z1"], base["Z2"], base["Z4"],
                  base["Z3"], base["Z5"]])         # (5, N)
    z = np.einsum("dij,jn->din", L, Z)             # (d, 5, N)
    u = stats.norm.cdf(z)
    return u[:, 0], u[:, 1], u[:, 2], u[:, 3], u[:, 4]


def simulate(district_df):
    rng = np.random.default_rng(RNG_SEED)
    base = {
        "Theta": rng.uniform(1e-9, np.pi - 1e-9, N_SIM),
        "W": rng.exponential(1.0, N_SIM),
        "E1": rng.exponential(1.0, N_SIM),
        "E2": rng.exponential(1.0, N_SIM),
        "Z1": rng.standard_normal(N_SIM),
        "Z2": rng.standard_normal(N_SIM),
        "Z3": rng.standard_normal(N_SIM),
        "Z4": rng.standard_normal(N_SIM),
        "Z5": rng.standard_normal(N_SIM),
        "U_ind_F": rng.uniform(0, 1, N_SIM),   # independence comparison
        "U_ind_S": rng.uniform(0, 1, N_SIM),
        "U_ind_G": rng.uniform(0, 1, N_SIM),
        "U_ind_E": rng.uniform(0, 1, N_SIM),
        # Theft lives OUTSIDE the vine: burglary has no weather root, so
        # welding it to the copula would invent dependence the data does
        # not show. It is a compound leg drawn independently - and it is
        # appended LAST so every draw above keeps its position in the
        # seeded stream: the four weather perils simulate bit-identically
        # with or without it, which is what makes the evidence diff pure.
        "U_th": rng.uniform(0, 1, N_SIM),
        # Escape of water: same reasoning, same discipline - independent
        # leg, appended AFTER U_th so the five published perils simulate
        # bit-identically and the evidence diff stays pure.
        "U_eow": rng.uniform(0, 1, N_SIM),
        # Fire: the same discipline again - independent leg, appended
        # AFTER U_eow so the six published perils simulate
        # bit-identically with or without it.
        "U_fire": rng.uniform(0, 1, N_SIM),
    }

    out = {k: [] for k in [
        "el_sub", "el_wx", "el_fl", "el_gw", "el_th", "el_eow", "el_fire",
        "el_er",
        "el_total",
        "el_total5", "var995_vine",
        "var995_gauss", "var995_indep", "tvar99_vine", "tvar99_gauss",
        "tvar99_indep", "tvar99_vine5", "tvar99_indep5", "uplift_pct",
        "tail_dep_wf", "tail_dep_ws", "tail_dep_wg", "tail_dep_we",
        "theta_wf", "theta_ws", "theta_wg", "theta_we",
    ]}

    def tvar(a, q=0.99):
        # expected shortfall: mean of the worst (1-q) share of years.
        # VaR is not monotone under dependence for skewed compound losses
        # (clustering pushes losses beyond the quantile), TVaR is - so
        # premiums and the uplift layer use TVaR.
        k = max(int(a.shape[1] * (1 - q)), 1)
        return np.partition(a, -k, axis=1)[:, -k:].mean(axis=1)

    # portfolio year-level accumulators (per simulated year, summed over
    # districts) — used for the good-year / bad-year analysis.
    # The pricing sim shares random draws across districts (comonotone),
    # which is fine per district but degenerate as a portfolio view: in
    # most years nothing claims anywhere. For the year view each district
    # mixes the national systemic factor (which carries the vine
    # dependence) with idiosyncratic noise via a Gaussian factor model,
    # preserving each district's marginal exactly:
    #   u_dist = Phi( sqrt(w)*Phi^-1(u_sys) + sqrt(1-w)*eps )
    SPATIAL_LOADING = {k: min(v * SPATIAL_SCALE, 0.98)
                       for k, v in SPATIAL_BASE.items()}
    year = {k: np.zeros(N_SIM) for k in
            ["s_v", "w_v", "f_v", "g_v", "s_i", "f_i", "g_i",
             "inc_s", "inc_w", "inc_f", "inc_g"]}
    # Per-district year-view loss, kept so capital can be allocated to
    # districts by their contribution to the PORTFOLIO tail (Euler).
    #
    # This holds the CONDITIONAL EXPECTED loss given the year's systemic
    # draw, not the realised loss. That is a deliberate variance reduction
    # (Rao-Blackwellisation), and it matters: the allocation averages over
    # the worst 1% of years, which is only 200 draws, and at calibrated
    # frequencies a district claims in 1-2 of them. Averaging REALISED
    # losses over that window made capital - and therefore the premium and
    # the published rating group - largely Monte Carlo noise. Re-running
    # with a different seed churned ~58% of districts into a different
    # decile on a 304-district portfolio, and a +0.4% change in flood
    # expected loss moved one district 8 deciles on the full run.
    #
    # Conditioning on the systemic factor removes the Bernoulli noise
    # entirely and is exact rather than approximate, because the bad-year
    # selection below also uses the smoothed portfolio loss - so the
    # selection is systemic-measurable and the tower property applies.
    # Expected loss is unchanged in expectation; only its variance falls.
    year_loss = np.zeros((len(district_df), N_SIM), dtype=np.float32)
    # exposure: portfolio quantities are per-policy, so districts enter
    # weighted by how many households they actually contain
    expo = district_df["households"].values.astype(np.float64)
    expo_total = float(expo.sum())

    def mix_with(u, w_sp, eps):
        z = stats.norm.ppf(np.clip(u, 1e-12, 1 - 1e-12))
        return stats.norm.cdf(np.sqrt(w_sp) * z + np.sqrt(1 - w_sp) * eps)

    def cond_expected(u_sys, p, sev, w_sp):
        """E[loss | this year's systemic draw] for one peril.

        Under the factor model a district claims when
            Phi(sqrt(w)*Phi^-1(u_sys) + sqrt(1-w)*eps) > 1 - p,
        so conditional on u_sys the claim probability is closed-form, and
        the expected loss is that times the lognormal mean. Same marginal
        as the realised draw, a fraction of the variance.
        """
        z = stats.norm.ppf(np.clip(u_sys, 1e-12, 1 - 1e-12))
        thr = stats.norm.ppf(np.clip(1.0 - p, 1e-12, 1 - 1e-12))
        q = stats.norm.cdf((np.sqrt(w_sp) * z - thr) / np.sqrt(1 - w_sp))
        return q * np.exp(sev["mu"] + sev["sigma"] ** 2 / 2)

    def run_batch(start):
        chunk = district_df.iloc[start:start + BATCH]
        fld = {k: v[:, None] for k, v in _fields(chunk).items()}
        t_ws = theta_ws(fld["sub"], fld["wx"])
        t_wf = theta_wf(fld["wx"], chunk["fl_score"].values[:, None])
        t_wg = theta_wg(fld["wx"], chunk["gw_score"].values[:, None])
        t_we = theta_we(fld["wx"], chunk["er_score"].values[:, None])
        m = marginal_params(fld)

        # The headline total is the four INSURED perils. Erosion is kept
        # separate: gradual coastal erosion is excluded from standard
        # household cover, so folding it into the premium would price a
        # loss no policy pays. It is still drawn from the joint vine, so
        # its dependence on storms and coastal flooding is modelled.
        # u_e is optional because most callers here discard the erosion
        # leg, and this loop is memory-bound (see the BATCH note above) —
        # no point materialising another (BATCH x N_SIM) array to drop it.
        def losses(u_w, u_f, u_g, u_s, u_e=None):
            """Per-peril loss draws: (sub, wx, flood, gw, erosion-or-None)."""
            def leg(u, p, sev):
                return inv_mixed_cdf(u, np.broadcast_to(m[p], u.shape),
                                     **m[sev])
            return (leg(u_s, "p_sub", "sev_sub"), leg(u_w, "p_wx", "sev_wx"),
                    leg(u_f, "p_fl", "sev_fl"), leg(u_g, "p_gw", "sev_gw"),
                    leg(u_e, "p_er", "sev_er") if u_e is not None else None)

        def insured(parts):
            return parts[0] + parts[1] + parts[2] + parts[3]

        u_w, u_f, u_g, u_s, u_e = sample_vine(t_ws, t_wf, t_wg, t_we, base)
        ls, lw, lf, lg, le = losses(u_w, u_f, u_g, u_s, u_e)
        bc = lambda key: np.broadcast_to(base[key], u_w.shape)
        # Theft enters every dependence view IDENTICALLY - vine, Gaussian
        # and independence - because it is independent of the weather
        # perils by construction, so the three tails differ only in how
        # the weather perils cluster. It still fattens each total, which
        # mechanically DILUTES uplift_pct: an independent attritional
        # line diversifying the cat tail is real economics, not a bug.
        l_th = inv_mixed_cdf(bc("U_th"),
                             np.broadcast_to(m["p_th"], u_w.shape),
                             **m["sev_th"])
        # Escape of water: same placement as theft. Freeze-driven bursts
        # do correlate with cold snaps, but cold is the one weather axis
        # the vine does NOT carry (its root is storm/rain-driven), so
        # independence from the four vine perils is the honest structure
        # - the freeze systemicity lives in W_EOW, not in the copula.
        l_eow = inv_mixed_cdf(bc("U_eow"),
                              np.broadcast_to(m["p_eow"], u_w.shape),
                              **m["sev_eow"])
        # Fire: independent leg like theft. Dwelling fires have no
        # weather root at all (the FIRE0201 residuals barely move even
        # in heatwave years), so independence is not an approximation
        # here - it is what the data shows.
        l_fire = inv_mixed_cdf(bc("U_fire"),
                               np.broadcast_to(m["p_fire"], u_w.shape),
                               **m["sev_fire"])
        tot_v = ls + lw + lf + lg + l_th + l_eow + l_fire
        tot5_v = tot_v + le
        tot_n = insured(losses(*sample_gaussian5(t_ws, t_wf, t_wg, t_we,
                                                 base)[:4])) + l_th + l_eow \
            + l_fire
        parts_i = losses(u_w, bc("U_ind_F"), bc("U_ind_G"), bc("U_ind_S"),
                         bc("U_ind_E"))
        tot_i = insured(parts_i) + l_th + l_eow + l_fire
        tot5_i = tot_i + parts_i[4]

        # year view: systemic factor + idiosyncratic district noise
        rng_b = np.random.default_rng(RNG_SEED + 1000 + start)
        shape = (len(chunk), N_SIM)
        eps_w = rng_b.standard_normal(shape)
        eps_f = rng_b.standard_normal(shape)
        eps_s = rng_b.standard_normal(shape)
        eps_g = rng_b.standard_normal(shape)
        # Erosion is deliberately absent from the year view. It is a
        # chronic process, not an event: including it would add a nearly
        # constant charge to every simulated year and blur exactly the
        # good-year / bad-year contrast this view exists to show. Capital
        # is therefore also allocated against insured losses only.
        uw_y = mix_with(u_w, SPATIAL_LOADING["w"], eps_w)
        uf_y = mix_with(u_f, SPATIAL_LOADING["f"], eps_f)
        us_y = mix_with(u_s, SPATIAL_LOADING["s"], eps_s)
        ug_y = mix_with(u_g, SPATIAL_LOADING["g"], eps_g)
        ls_y, lw_y, lf_y, lg_y, _ = losses(uw_y, uf_y, ug_y, us_y)
        # realised losses drive the good/bad-year narrative (incidence,
        # per-peril composition); the smoothed version drives capital
        cond = (cond_expected(u_s, m["p_sub"], m["sev_sub"], SPATIAL_LOADING["s"])
                + cond_expected(u_w, m["p_wx"], m["sev_wx"], SPATIAL_LOADING["w"])
                + cond_expected(u_f, m["p_fl"], m["sev_fl"], SPATIAL_LOADING["f"])
                + cond_expected(u_g, m["p_gw"], m["sev_gw"], SPATIAL_LOADING["g"])
                # Theft is insured, so it belongs in the capital
                # allocation (unlike erosion, excluded above because no
                # policy pays it). With its small fixed loading its
                # contribution to the worst-1% years is close to its
                # mean - the diversification credit an attritional line
                # earns against a cat tail. It stays OUT of the yr
                # narrative dict: the good-year/bad-year story is about
                # weather clustering, and a near-constant theft charge
                # would blur exactly that contrast.
                + cond_expected(bc("U_th"), m["p_th"], m["sev_th"], W_THEFT)
                # EoW joins capital with its own, much larger loading:
                # a 1-in-100 freeze year roughly doubles the national EoW
                # bill (winter 2010), so unlike theft it earns only a
                # partial diversification credit against the cat tail.
                + cond_expected(bc("U_eow"), m["p_eow"], m["sev_eow"],
                                W_EOW)
                # Fire joins capital with a near-zero loading: no
                # systemic fire years exist in the record, so its
                # contribution to the worst-1% years is its mean - the
                # full diversification credit of a genuinely
                # idiosyncratic line.
                + cond_expected(bc("U_fire"), m["p_fire"], m["sev_fire"],
                                W_FIRE))
        year_loss[start:start + len(chunk)] = cond.astype(np.float32)
        # independence year view: same idiosyncratic noise (common random
        # numbers), systemic factors independent across perils
        ufi_y = mix_with(np.broadcast_to(base["U_ind_F"], shape),
                         SPATIAL_LOADING["f"], eps_f)
        usi_y = mix_with(np.broadcast_to(base["U_ind_S"], shape),
                         SPATIAL_LOADING["s"], eps_s)
        ugi_y = mix_with(np.broadcast_to(base["U_ind_G"], shape),
                         SPATIAL_LOADING["g"], eps_g)
        ls_iy, _, lf_iy, lg_iy, _ = losses(uw_y, ufi_y, ugi_y, usi_y)

        ew = expo[start:start + len(chunk)][:, None]      # exposure weights
        yr = {
            "s_v": (ls_y * ew).sum(axis=0),
            "w_v": (lw_y * ew).sum(axis=0),
            "f_v": (lf_y * ew).sum(axis=0),
            "g_v": (lg_y * ew).sum(axis=0),
            "s_i": (ls_iy * ew).sum(axis=0),
            "f_i": (lf_iy * ew).sum(axis=0),
            "g_i": (lg_iy * ew).sum(axis=0),
            "inc_s": ((ls_y > 0) * ew).sum(axis=0),
            "inc_w": ((lw_y > 0) * ew).sum(axis=0),
            "inc_f": ((lf_y > 0) * ew).sum(axis=0),
            "inc_g": ((lg_y > 0) * ew).sum(axis=0),
        }

        q = lambda a: np.quantile(a, 0.995, axis=1)
        t_v, t_n, t_i = tvar(tot_v), tvar(tot_n), tvar(tot_i)

        loc = {}
        loc["el_sub"] = (ls.mean(axis=1))
        loc["el_wx"] = (lw.mean(axis=1))
        loc["el_fl"] = (lf.mean(axis=1))
        loc["el_gw"] = (lg.mean(axis=1))
        # Theft's expected loss is ANALYTIC for the same reason erosion's
        # is (below), with a different failure mode: every district shares
        # ONE U_th stream, so the ~150 draws that clear a p~0.8% threshold
        # carry a COMMON sampling error - the first evidence run came out
        # +17% over the calibrated level (GBP 33.89 vs 29.03) in every
        # district at once, defeating the point of calibrating. The draws
        # still feed the tails (tot_v/tot_n/tot_i), where they belong.
        el_th = (m["p_th"] * np.exp(m["sev_th"]["mu"]
                                    + m["sev_th"]["sigma"] ** 2 / 2)).ravel()
        loc["el_th"] = (el_th)
        # EoW shares theft's failure mode exactly - one U_eow stream
        # across all districts - so its EL is analytic too.
        el_eow = (m["p_eow"] * np.exp(m["sev_eow"]["mu"]
                                      + m["sev_eow"]["sigma"] ** 2 / 2)).ravel()
        loc["el_eow"] = (el_eow)
        # Fire: one shared U_fire stream, so analytic EL for the same
        # reason - and with p ~ 0.2% and sigma 1.3 the draw-mean noise
        # would be worse than theft's was.
        el_fire = (m["p_fire"] * np.exp(m["sev_fire"]["mu"]
                                        + m["sev_fire"]["sigma"] ** 2 / 2)
                   ).ravel()
        loc["el_fire"] = (el_fire)
        # Erosion's expected loss is taken ANALYTICALLY, not from the draws.
        # Its annual probability is ~1.5e-5 for a typical coastal district,
        # so 20,000 years give well under one event: the simulated mean
        # would be a £250,000 spike or nothing at all — pure Monte Carlo
        # noise, the same trap that killed the per-district copula-uplift
        # layer. E[B(p)·LogNormal] = p·exp(mu + sigma²/2) is exact and the
        # severity is built to hit that mean, so there is nothing to gain
        # from simulating it. The DRAWS are still used for the joint tail
        # (tvar99_vine5), where the dependence is the point.
        el_er = (m["p_er"] * np.exp(m["sev_er"]["mu"]
                                    + m["sev_er"]["sigma"] ** 2 / 2)).ravel()
        loc["el_er"] = (el_er)
        # The published expected-loss level must be the CALIBRATED one, so
        # el_total sums the four weather-peril draw means (which the ABI
        # scaling was solved against) with the analytic theft leg - the
        # same construction el_total5 has always used for erosion.
        loc["el_total"] = ((ls + lw + lf + lg).mean(axis=1)
                           + el_th + el_eow + el_fire)
        loc["el_total5"] = (loc["el_total"] + el_er)
        # var995_vine is published; the gauss and indep siblings are NOT in
        # OUTPUT_COLUMNS and nothing downstream reads them. They are kept
        # anyway and this note exists so they are not mistaken for dead
        # code: the three together are the evidence for the README's
        # "VaR can fall as dependence rises" finding, which is why premiums
        # use TVaR. Delete them and the claim can no longer be reproduced
        # from a run. They cost one np.partition each per batch.
        loc["var995_vine"] = (q(tot_v))
        loc["var995_gauss"] = (q(tot_n))
        loc["var995_indep"] = (q(tot_i))
        loc["tvar99_vine"] = (t_v)
        loc["tvar99_gauss"] = (t_n)
        loc["tvar99_indep"] = (t_i)
        loc["tvar99_vine5"] = (tvar(tot5_v))
        loc["tvar99_indep5"] = (tvar(tot5_i))
        loc["uplift_pct"] = (100.0 * (t_v - t_i) / np.maximum(t_i, 1e-9))
        loc["tail_dep_wf"] = ((2.0 - 2.0 ** (1.0 / t_wf)).ravel())
        loc["tail_dep_ws"] = ((2.0 - 2.0 ** (1.0 / t_ws)).ravel())
        loc["tail_dep_wg"] = ((2.0 - 2.0 ** (1.0 / t_wg)).ravel())
        loc["tail_dep_we"] = ((2.0 - 2.0 ** (1.0 / t_we)).ravel())
        loc["theta_wf"] = (t_wf.ravel())
        loc["theta_ws"] = (t_ws.ravel())
        loc["theta_wg"] = (t_wg.ravel())
        loc["theta_we"] = (t_we.ravel())
        return start, loc, yr

    # Batches are independent - the year-view noise is seeded per batch
    # (RNG_SEED + 1000 + start), keyed to the batch OFFSET rather than to
    # execution order - so they can run concurrently. numpy releases the
    # GIL in its ufunc loops, so threads suffice: no pickling, no
    # re-initialising module globals in a spawned interpreter, and one
    # shared copy of `base` instead of one per process.
    #
    # Results are combined strictly IN BATCH ORDER below. That is the part
    # that keeps this bit-identical: floating-point addition is not
    # associative, so accumulating `year` as batches happen to finish
    # would change the last bits of the portfolio series.
    starts = list(range(0, len(district_df), BATCH))
    done = {}

    def note(start):
        # Progress must appear AS batches finish. Collecting with
        # list(ex.map(...)) drains the whole iterator first, so the log
        # stayed silent for the entire simulation and then dumped every
        # line at once - which removes the only reliable way to tell a
        # slow run from a hung one on a machine that sleeps.
        n = sum(len(district_df.iloc[s:s + BATCH]) for s in done)
        print(f"  simulated {n}/{len(district_df)} districts", flush=True)

    if N_THREADS > 1 and len(starts) > 1:
        with ThreadPoolExecutor(N_THREADS) as ex:
            futures = [ex.submit(run_batch, s) for s in starts]
            for fut in as_completed(futures):
                start, loc, yr = fut.result()
                done[start] = (loc, yr)
                note(start)
    else:
        for s in starts:
            start, loc, yr = run_batch(s)
            done[start] = (loc, yr)
            note(start)

    # Combined in BATCH order, not completion order - see the note above
    # on floating-point addition not being associative.
    for start in starts:
        loc, yr = done[start]
        for k, v in loc.items():
            out[k].append(v)
        for k, v in yr.items():
            year[k] += v

    res = {k: np.concatenate(v) for k, v in out.items()}

    # ---- Euler allocation of PORTFOLIO capital -------------------------
    # Capital is held against portfolio outcomes, not against each policy's
    # own worst year, so the charge must be allocated by each district's
    # expected loss GIVEN the portfolio is in its worst 1% of years:
    #     TVaR_i = E[L_i | L_portfolio >= VaR_99(L_portfolio)]
    # These allocations sum exactly to the portfolio TVaR (Euler additivity),
    # so cross-district diversification is credited rather than ignored.
    # `year_loss` holds conditional expectations (see above), so both the
    # ranking of years and the allocation are smooth functions of the
    # systemic draws - which is what makes the result reproducible.
    port = (expo @ year_loss) / expo_total
    k = max(int(N_SIM * 0.01), 1)
    bad = np.argpartition(port, -k)[-k:]
    res["tvar99_euler"] = year_loss[:, bad].mean(axis=1)
    res["el_year"] = year_loss.mean(axis=1)
    port_tvar = float(port[bad].mean())
    standalone = float(np.average(res["tvar99_vine"], weights=expo))
    print(f"  portfolio TVaR99 {port_tvar:,.0f} /policy (systemic-conditional); "
          f"exposure-weighted standalone TVaR99 {standalone:,.0f} "
          f"(diversification credit "
          f"{100 * (1 - port_tvar / standalone):.0f}%)")
    # How concentrated is the tail? With the smoothed allocation this is a
    # property of the hazard, not of the draw.
    share = res["tvar99_euler"] * expo
    share = np.sort(share / max(share.sum(), 1e-9))[::-1]
    print(f"  tail concentration: top 10% of exposure carries "
          f"{100 * share[:max(len(share) // 10, 1)].sum():.0f}% of allocated capital")
    year["expo_total"] = expo_total
    return res, year


# ------------------------------------------------------- year analysis
# Built from the factor-mixed year view (see simulate): each district
# combines the national systemic factor per peril (carrying the vine
# dependence) with idiosyncratic noise, spatial loadings W/F/S =
# 0.50/0.40/0.60 — storm and drought years are large-scale in the UK,
# flood more localised. Marginals are preserved exactly.

BUCKETS = [
    ("good", 0.0, 0.5),
    ("typical", 0.5, 0.9),
    ("bad", 0.9, 0.99),
    ("catastrophic", 0.99, 1.0),
]


def year_analysis(year, n_districts):
    # divide by total exposure, so everything below is per policy nationally
    n = float(year.get("expo_total") or n_districts)
    s, w, f, g = (year["s_v"] / n, year["w_v"] / n,
                  year["f_v"] / n, year["g_v"] / n)
    tv = s + w + f + g                                    # vine, per policy
    ti = (year["s_i"] + year["w_v"] + year["f_i"]
          + year["g_i"]) / n                              # independence
    order = np.argsort(tv)
    order_i = np.argsort(ti)
    n_sim = len(tv)

    def exceedance(tot):
        srt = np.sort(tot)[::-1]
        ranks = np.unique(np.round(
            np.logspace(0, np.log10(n_sim / 2), 140)).astype(int))
        return [[round(n_sim / r, 2), round(float(srt[r - 1]), 1)]
                for r in ranks]

    buckets = []
    typical_mean = None
    for label, lo, hi in BUCKETS:
        idx = order[int(lo * n_sim):int(hi * n_sim)]
        idx_i = order_i[int(lo * n_sim):int(hi * n_sim)]
        b = dict(
            label=label, share_pct=round(100 * (hi - lo), 1),
            mean_total=round(float(tv[idx].mean()), 1),
            mean_sub=round(float(s[idx].mean()), 1),
            mean_wx=round(float(w[idx].mean()), 1),
            mean_fl=round(float(f[idx].mean()), 1),
            mean_gw=round(float(g[idx].mean()), 1),
            inc_sub_pct=round(100 * float(year["inc_s"][idx].mean()) / n, 2),
            inc_wx_pct=round(100 * float(year["inc_w"][idx].mean()) / n, 2),
            inc_fl_pct=round(100 * float(year["inc_f"][idx].mean()) / n, 2),
            inc_gw_pct=round(100 * float(year["inc_g"][idx].mean()) / n, 2),
            indep_mean_total=round(float(ti[idx_i].mean()), 1),
        )
        if label == "typical":
            typical_mean = b["mean_total"]
        buckets.append(b)
    for b in buckets:
        b["extra_vs_typical"] = round(b["mean_total"] - typical_mean, 1)

    worst = int(order[-1])
    return dict(
        n_sim=n_sim,
        n_districts=n_districts,
        mean_total=round(float(tv.mean()), 1),
        buckets=buckets,
        exceedance=dict(vine=exceedance(tv), indep=exceedance(ti)),
        worst_year=dict(
            total=round(float(tv[worst]), 1),
            sub=round(float(s[worst]), 1),
            wx=round(float(w[worst]), 1),
            fl=round(float(f[worst]), 1),
            gw=round(float(g[worst]), 1),
            inc_wx_pct=round(100 * float(year["inc_w"][worst]) / n, 1),
            inc_fl_pct=round(100 * float(year["inc_f"][worst]) / n, 1),
            inc_sub_pct=round(100 * float(year["inc_s"][worst]) / n, 1),
            inc_gw_pct=round(100 * float(year["inc_g"][worst]) / n, 1),
        ),
    )


# ---------------------------------------------------------------- main


def main():
    print("loading district polygons...")
    gdf = load_districts()
    print(f"  {len(gdf)} districts across {gdf['area'].nunique()} postcode areas")

    bng = gdf.to_crs(27700)
    bng_pts = bng.geometry.representative_point()
    targets = np.column_stack([bng_pts.x.values, bng_pts.y.values])

    print("scoring subsidence from BGS 625k geology...")
    # Bedrock blended with the superficial deposits that overlie it, at a
    # bounded weight because 625k publishes no thickness - see
    # subsidence_score() / combine_subsidence() in scores_real.
    (gdf["sub_score"], gdf["geol"],
     gdf["sup_frac"], gdf["sup_geol"]) = subsidence_score(bng)

    print("scoring weather from Met Office grids...")
    gdf["wx_score"], wx_raw = weather_from_metoffice(targets)
    gdf["wind_ms"] = wx_raw["wind"]
    gdf["wdr_idx"] = wx_raw["wdr"]
    gdf["rain10_days"] = wx_raw["rain10"]
    gdf["precip_mm"] = wx_raw["precip"]
    gdf["gust_rp50"] = wx_raw["gust_rp50"]

    print("scoring flood from EA/NRW/SEPA zone fractions...")
    (gdf["fl_score"], gdf["f_high"], gdf["f_low"],
     gdf["sw_high"], gdf["sw_low"]) = flood_from_agencies(gdf["name"].values)

    print("scoring groundwater from EA alert-area fractions...")
    gdf["gw_score"], gdf["gw_frac"] = groundwater_from_ea(gdf["name"].values)

    # Carried through to the front end so England-only layers can say
    # "not mapped here" rather than showing a zero that reads as "no risk".
    gdf["country"] = load_country(gdf["name"].values)

    print("scoring coastal erosion from EA NCERM frontages...")
    gdf["er_score"], er = erosion_from_ncerm(gdf["name"].values)
    for col, vals in er.items():
        gdf[col] = vals
    # the insured-peril calculation uses the SMP (planned defences) case
    gdf["er_frac"] = gdf["er_smp105"]

    print("loading exposure...")
    gdf["households"] = load_households(gdf["name"].values)

    print("conditioning surface-water severity on EA depth bands...")
    gdf["sw_sev"], gdf["sw_depth_m"] = sw_depth_severity(
        gdf["name"].values, gdf["sw_high"].values, gdf["sw_low"].values,
        gdf["households"].values)

    print("scoring theft from police.uk burglary counts...")
    gdf["th_rate"] = theft_from_police(gdf["name"].values,
                                       gdf["households"].values)

    print("scoring escape-of-water freeze exposure from frost days...")
    gdf["frost_days"] = frost_from_metoffice(targets)
    # eow_rate = anchor frequency x (flat base + freeze-sensitive slice
    # on each district's frost days relative to the exposure-weighted
    # mean). The normalisation lives HERE, not in marginal_params: that
    # function runs on batches, and a per-chunk mean would make the
    # marginal depend on which districts share a chunk. The relativity's
    # exposure-weighted mean is exactly 1 by construction, so the column
    # lands on the anchor level and calibrate_frequency re-pins it
    # (FREQ_SCALE["eow"] solves to 1.0) - same division of labour as
    # th_rate, where the police data supplies an approximate level and
    # calibration corrects it.
    fmean = np.average(gdf["frost_days"], weights=gdf["households"])
    gdf["eow_rate"] = ABI_TARGET_FREQ["eow"] * (
        (1.0 - EOW_FREEZE_SHARE)
        + EOW_FREEZE_SHARE * gdf["frost_days"] / fmean)

    print("scoring fire from MHCLG dwelling-fire incidents...")
    # fire_rate = anchor frequency x the district's dwelling-fire
    # relativity. Same division of labour as eow_rate: the relativity
    # is normalised HERE (its exposure-weighted mean is exactly 1), so
    # the column lands on the anchor level and calibrate_frequency
    # re-pins it (FREQ_SCALE["fire"] solves to 1.0). The raw input is
    # the attended-fire rate per household; the attended-to-claim
    # propensity cancels in the normalisation, so it never appears.
    fire_raw = fires_from_mhclg(gdf["name"].values,
                                gdf["households"].values)
    gdf["fire_rate"] = ABI_TARGET_FREQ["fire"] * fire_raw / np.average(
        fire_raw, weights=gdf["households"])

    check_scored_columns(gdf)

    print("calibrating to published UK aggregates...")
    calibrate_frequency(gdf)
    calibrate_spatial(gdf)

    print(f"running copula simulation ({N_SIM:,} years/district)...")
    sim, year = simulate(gdf)
    check_simulated_columns(sim)
    for k, v in sim.items():
        gdf[k] = v

    print("writing year analysis...")
    with open(os.path.join(DATA, "year_analysis.json"), "w") as fh:
        json.dump(year_analysis(year, len(gdf)), fh)

    # Technical premium = expected loss + 6% cost of capital on the
    # district's ALLOCATED share of portfolio tail risk (Euler), not on its
    # standalone TVaR - an insurer holds capital against the portfolio.
    gdf["capital"] = 0.06 * np.maximum(
        gdf["tvar99_euler"] - gdf["el_year"], 0.0)
    gdf["premium"] = gdf["el_total"] + gdf["capital"]
    gdf["group"] = pd.qcut(gdf["premium"].rank(method="first"), 10, labels=False) + 1

    # ---- climate-change repricing ------------------------------------
    # Re-run the SAME model on the EA's future flood extents, holding the
    # ABI calibration fixed. The point is to let the hazard map move and
    # nothing else: recalibrating would absorb the change and report no
    # repricing at all. Common random numbers make it a paired comparison.
    future = flood_future(gdf["name"].values, gdf["f_high"].values,
                          gdf["f_low"].values, gdf["sw_high"].values,
                          gdf["sw_low"].values)
    if future is not None:
        fh_cc, fl_cc, swh_cc, swl_cc, cc_covered = future
        fut = gdf.copy()
        fut["f_high"], fut["f_low"] = fh_cc, fl_cc
        fut["sw_high"], fut["sw_low"] = swh_cc, swl_cc
        fut["fl_score"] = flood_score_from_fractions(
            fh_cc, fl_cc, swh_cc, swl_cc, climate=True)
        fut["sw_sev"], _ = sw_depth_severity(
            gdf["name"].values, swh_cc, swl_cc, gdf["households"].values,
            climate=True)
        print(f"running climate-change simulation "
              f"({N_SIM:,} years/district)...")
        sim_cc, _ = simulate(fut)
        gdf["el_total_cc"] = sim_cc["el_total"]
        gdf["capital_cc"] = 0.06 * np.maximum(
            sim_cc["tvar99_euler"] - sim_cc["el_year"], 0.0)
        gdf["premium_cc"] = gdf["el_total_cc"] + gdf["capital_cc"]
        gdf["cc_covered"] = cc_covered.astype(int)
        gdf["cc_uplift_pct"] = np.where(
            cc_covered,
            100.0 * (gdf["premium_cc"] / np.maximum(gdf["premium"], 1e-9) - 1),
            np.nan)
        w = gdf["households"].values
        cov = cc_covered
        nat = 100 * (np.average(gdf["premium_cc"].values[cov], weights=w[cov])
                     / np.average(gdf["premium"].values[cov], weights=w[cov])
                     - 1)
        print(f"  climate repricing over {int(cov.sum())} covered districts: "
              f"exposure-weighted premium {nat:+.1f}%; "
              f"district range {np.nanmin(gdf['cc_uplift_pct']):+.0f}% to "
              f"{np.nanmax(gdf['cc_uplift_pct']):+.0f}%")
    else:
        for c in ("el_total_cc", "capital_cc", "premium_cc", "cc_uplift_pct"):
            gdf[c] = np.nan
        gdf["cc_covered"] = 0

    modelled = float(gdf["el_total"].mean())
    print(f"  check: modelled loss cost for these four perils "
          f"£{modelled:,.2f}/policy vs ABI £{ABI_LOSS_PER_POLICY:,.2f} "
          f"({modelled / ABI_LOSS_PER_POLICY - 1:+.0%}); "
          f"{modelled / (ABI['total_home_paid'] / POLICIES):.0%} of the "
          f"£{ABI['total_home_paid'] / POLICIES:,.0f} all-perils home claims cost")

    # Coastal erosion, reported alongside but NOT inside the premium.
    # Standard household policies exclude gradual erosion, so adding it to
    # `premium` would price a loss no policy pays; it is kept as its own
    # column so the exposure is visible without contaminating the rating.
    w = gdf["households"].values
    er_el = float(np.average(gdf["el_er"].values, weights=w))
    n_er = int((gdf["el_er"].values > 0.5).sum())
    print(f"  erosion (excluded from premium): £{er_el:,.2f}/policy "
          f"nationally, {100 * er_el / max(modelled, 1e-9):.1f}% of the "
          f"insured loss cost, but concentrated in {n_er} districts "
          f"(max £{gdf['el_er'].max():,.0f}/policy)")

    print("writing geojson...")
    keep = OUTPUT_COLUMNS
    out = gdf[keep].copy()
    out["geometry"] = out.geometry.simplify(0.0025, preserve_topology=True)
    # NaN would be written literally and make the GeoJSON unparseable. The
    # only column that carries it is the mean surface-water depth, which is
    # undefined where no depth is mapped - Wales, Scotland, and English
    # districts with no surface water at all - so send it out as 0.
    out["sw_depth_m"] = out["sw_depth_m"].fillna(0.0)
    # Same for the climate columns: undefined outside England, where the EA
    # publishes no future extents. `cc_covered` is the flag that keeps the
    # zero readable as "not modelled" rather than "no change".
    for col in ("el_total_cc", "capital_cc", "premium_cc", "cc_uplift_pct"):
        out[col] = out[col].fillna(0.0)
    round1 = {"wind_ms": 1, "wdr_idx": 1, "rain10_days": 1, "precip_mm": 0,
              "gust_rp50": 0, "households": 0, "sw_depth_m": 2,
              "frost_days": 1}
    for col in keep:
        if col in ("name", "area", "country", "geometry", "group", "geol",
                   "sup_geol"):
            continue
        if col in round1:
            out[col] = out[col].round(round1[col])
        elif "var" in col or col.startswith("el") or col == "premium":
            out[col] = out[col].round(1)
        elif col.startswith("er_"):
            # erosion fractions run down to ~1e-6 for lightly-clipped
            # districts; 4 dp would round most of them away
            out[col] = out[col].round(7)
        else:
            out[col] = out[col].round(4)
    out.to_file(OUT, driver="GeoJSON", coordinate_precision=4)

    size_mb = os.path.getsize(OUT) / 1e6
    print(f"done: {OUT} ({size_mb:.1f} MB)")
    print(out[["sub_score", "wx_score", "fl_score", "gw_score", "premium",
               "uplift_pct"]].describe().round(2))
    print("\nhighest-premium districts:")
    print(out.nlargest(8, "premium")[["name", "sub_score", "wx_score",
                                      "fl_score", "premium",
                                      "group"]].to_string(index=False))


if __name__ == "__main__":
    main()
