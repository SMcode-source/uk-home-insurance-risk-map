"""Build the UK postcode-district risk model for home insurance.

Pipeline:
  1. Load ~2,700 postcode-district polygons (one GeoJSON per postcode area).
  2. Score each district on two perils from REAL open data (see
     scores_real.py):
       - subsidence  : BGS 625k bedrock geology classified for shrink-swell
                       susceptibility, area-weighted per district
       - weather     : Met Office grids (winter wind, wind-driven rain
                       index, >=10mm rain days, annual precipitation)
                       interpolated to district centroids
       - flood       : EA / NRW / SEPA flood-zone extents rasterised to
                       per-district area fractions
  3. Model per-district annual aggregate losses for each peril (compound
     frequency-severity marginals) and join them with a C-vine copula
     (weather at the root; Gumbel pairs weather-flood and
     weather-subsidence, Gaussian subsidence-flood given weather) — with
     trivariate-Gaussian and independence runs for comparison.
  4. Band districts into 10 rating groups on the technical premium
     (expected loss + cost of capital on the 1-in-200 joint loss).
  5. Write districts_risk.geojson for the map front-end.

The hazard inputs are real (BGS + Met Office, OGL); the marginal loss
frequencies/severities and the copula theta remain assumptions — calibrate
those to claims data for production use.
"""

import glob
import json
import os

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy import stats

from scores_real import (subsidence_from_bgs, weather_from_metoffice,
                         flood_from_agencies, groundwater_from_ea)

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

# ---------------------------------------------------------------- load


def load_districts() -> gpd.GeoDataFrame:
    frames = []
    for path in sorted(glob.glob(os.path.join(DATA, "uk-postcode-polygons", "geojson", "*.geojson"))):
        gdf = gpd.read_file(path)
        gdf["area"] = os.path.splitext(os.path.basename(path))[0]
        frames.append(gdf[["name", "area", "geometry"]])
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    return gdf


# ------------------------------------------------- marginal loss models
# Annual aggregate loss per policy, modelled as at-most-one claim per year
# (adequate at district level for banding): L = B(p) * LogNormal(mu, sigma).
# Inverse CDF of this mixed distribution:
#   F^-1(u) = 0                          for u <= 1 - p
#           = LN^-1((u - (1-p)) / p)     otherwise


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
)
# Target per-policy frequency for each modelled peril = paid / severity / policies
ABI_TARGET_FREQ = {
    "wx": ABI["storm_paid"] / ABI["sev_weather"] / POLICIES,
    "fl": ABI["flood_paid"] / ABI["sev_flood"] / POLICIES,
    "sub": ABI["subsidence_paid"] / ABI["sev_subsidence"] / POLICIES,
}
ABI_LOSS_PER_POLICY = (ABI["storm_paid"] + ABI["flood_paid"]
                       + ABI["subsidence_paid"]) / POLICIES

# lognormal median that gives the target MEAN for a given sigma
_median_for_mean = lambda mean, sigma: mean / np.exp(sigma ** 2 / 2)

# One multiplier per peril, set by calibrate_frequency() before simulating.
FREQ_SCALE = {"sub": 1.0, "wx": 1.0, "fl": 1.0, "gw": 1.0}
GW_SHARE_OF_FLOOD = 0.10      # groundwater not published separately


def calibrate_frequency(gdf):
    """Scale each peril's claim frequency to its published ABI level.

    Only the LEVEL of each peril moves. The relative ranking of districts
    within a peril - which is what the hazard data determines, and the whole
    point of the model - is untouched.
    """
    global FREQ_SCALE
    FREQ_SCALE = {"sub": 1.0, "wx": 1.0, "fl": 1.0, "gw": 1.0}
    p_sub, p_wx, p_fl, p_gw, *_ = marginal_params(
        gdf["sub_score"].values, gdf["wx_score"].values,
        gdf["f_high"].values, gdf["f_low"].values,
        gdf["sw_high"].values, gdf["sw_low"].values,
        gdf["gw_frac"].values)
    raw = {"sub": float(p_sub.mean()), "wx": float(p_wx.mean()),
           "fl": float(p_fl.mean()), "gw": float(p_gw.mean())}
    for k in ("sub", "wx", "fl"):
        FREQ_SCALE[k] = ABI_TARGET_FREQ[k] / raw[k]
    # groundwater has no published total; peg it to a share of flood
    FREQ_SCALE["gw"] = (GW_SHARE_OF_FLOOD * ABI_TARGET_FREQ["fl"]) / raw["gw"]
    for k in ("wx", "fl", "sub"):
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
    p_sub, p_wx, p_fl, p_gw, *_ = marginal_params(
        gdf["sub_score"].values, gdf["wx_score"].values,
        gdf["f_high"].values, gdf["f_low"].values,
        gdf["sw_high"].values, gdf["sw_low"].values,
        gdf["gw_frac"].values)
    perils = [("s", p_sub), ("w", p_wx), ("f", p_fl), ("g", p_gw)]
    mean_freq = sum(float(p.mean()) for _, p in perils)
    z99 = stats.norm.ppf(0.99)

    def tail_freq(lam):
        total = 0.0
        for key, p in perils:
            w = min(SPATIAL_BASE[key] * lam, 0.98)
            thr = stats.norm.ppf(np.clip(1 - p, 1e-12, 1 - 1e-12))
            total += float(np.mean(stats.norm.cdf(
                (np.sqrt(w) * z99 - thr) / np.sqrt(1 - w))))
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


def marginal_params(sub, wx, f_high, f_low, sw_high, sw_low, gw_frac):
    """Per-district claim frequency and severity for each peril.

    Relative frequencies come from the hazard scores; the overall LEVEL is
    set by FREQ_SCALE (calibrate_frequency). Severity medians are chosen so
    each lognormal's MEAN matches the published ABI average claim.
    """
    p_sub = 0.002 + 0.028 * sub ** 1.5
    p_wx = 0.010 + 0.090 * wx ** 1.2
    # river/sea flood frequency from actual zone fractions: ~1.5%/yr for a
    # property in the defended 1in100/200 zone, ~0.3%/yr in the rest of
    # the 1in1000 envelope, 0.05%/yr background
    p_rs = 0.0005 + 0.015 * f_high + 0.003 * np.maximum(f_low - f_high, 0)
    # surface water: ~1%/yr in the >=1% AEP zone, shallower/cheaper events
    p_sw = 0.010 * sw_high + 0.002 * np.maximum(sw_low - sw_high, 0)
    p_fl = p_rs + p_sw
    p_gw = 0.0003 + 0.008 * gw_frac

    s_sub, s_wx, s_fl, s_gw = 0.90, 1.10, 0.90, 0.80
    sev_sub = dict(mu=np.log(_median_for_mean(ABI["sev_subsidence"], s_sub)),
                   sigma=s_sub)
    sev_wx = dict(mu=np.log(_median_for_mean(ABI["sev_weather"], s_wx)),
                  sigma=s_wx)
    # flood severity: frequency-weighted blend of fluvial/tidal and the
    # shallower, cheaper surface-water events
    mu_rs = np.log(_median_for_mean(ABI["sev_flood_fluvial"], s_fl))
    mu_sw = np.log(_median_for_mean(ABI["sev_surface_water"], s_fl))
    mu_fl = (p_rs * mu_rs + p_sw * mu_sw) / np.maximum(p_fl, 1e-12)
    sev_fl = dict(mu=mu_fl, sigma=s_fl)
    sev_gw = dict(mu=np.log(_median_for_mean(ABI["sev_groundwater"], s_gw)),
                  sigma=s_gw)

    k = FREQ_SCALE
    return (p_sub * k["sub"], p_wx * k["wx"], p_fl * k["fl"], p_gw * k["gw"],
            sev_sub, sev_wx, sev_fl, sev_gw)


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
# C-vine on (W=weather, F=flood, G=groundwater, S=subsidence), root W:
#   tree 1:  c_WF Gumbel(theta_wf)   storm rain drives flood - strongest
#            c_WG Gumbel(theta_wg)   prolonged rain recharges aquifers
#            c_WS Gumbel(theta_ws)   shared climate-volatility driver
#   tree 2 (given W, second-level root F):
#            c_FG|W Gaussian(0.25)   wet winters: fluvial + groundwater
#            c_FS|W Gaussian(0.15)   weak residual dependence
#   tree 3:  c_GS|WF = independence
# Gumbel pairs are upper-tail dependent: extreme years hit the perils
# together. Kendall tau = 1 - 1/theta; lambda_U = 2 - 2^(1/theta).

RHO_SF_GIVEN_W = 0.15
RHO_FG_GIVEN_W = 0.25


def theta_ws(sub, wx):
    return np.clip(1.25 + 1.25 * np.sqrt(sub * wx), 1.0, 2.5)


def theta_wf(wx, fl):
    return np.clip(1.40 + 1.60 * np.sqrt(wx * fl), 1.0, 3.0)


def theta_wg(wx, gw):
    # groundwater responds to cumulative winter rainfall
    return np.clip(1.30 + 1.10 * np.sqrt(wx * gw), 1.0, 2.4)


def h_gumbel(v, u, th):
    """h(v|u) = dC(u,v)/du for the Gumbel copula (conditional CDF of v)."""
    u = np.clip(u, 1e-12, 1 - 1e-12)
    v = np.clip(v, 1e-12, 1 - 1e-12)
    lu, lv = -np.log(u), -np.log(v)
    s = lu ** th + lv ** th
    return np.exp(-s ** (1 / th)) * lu ** (th - 1) / u * s ** (1 / th - 1)


def hinv_gumbel(t, u, th, iters=40):
    """Invert h_gumbel in v by bisection (h is increasing in v)."""
    lo = np.full(np.broadcast_shapes(t.shape, u.shape), 1e-9)
    hi = np.full_like(lo, 1 - 1e-9)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        below = h_gumbel(mid, u, th) < t
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


def sample_vine(t_ws, t_wf, t_wg, base):
    """Sample (u_w, u_f, u_g, u_s) from the C-vine with common random
    numbers.

    (W,F) drawn jointly via Marshall-Olkin; G and S conditionally:
      v   = h_{F|W}(u_f | u_w)                (tree-1 pseudo-observation)
      z_x = h^{-1}_gauss(w | v; rho_xF|W)     (tree 2, closed form)
      u_x = h^{-1}_{x|W}(z_x | u_w; theta_wx) (tree 1, bisection)
    Tree 3 (G,S | W,F) is independence, so S needs no extra step.
    """
    u_w, u_f = sample_gumbel(t_wf, base)
    v = np.clip(h_gumbel(u_f, u_w, t_wf), 1e-9, 1 - 1e-9)
    zv = stats.norm.ppf(v)

    rho_g = RHO_FG_GIVEN_W
    z_g = stats.norm.cdf(rho_g * zv + np.sqrt(1 - rho_g ** 2) * base["Z4"])
    u_g = hinv_gumbel(np.clip(z_g, 1e-9, 1 - 1e-9), u_w, t_wg)

    rho_s = RHO_SF_GIVEN_W
    z_s = stats.norm.cdf(rho_s * zv + np.sqrt(1 - rho_s ** 2) * base["Z3"])
    u_s = hinv_gumbel(np.clip(z_s, 1e-9, 1 - 1e-9), u_w, t_ws)
    return u_w, u_f, u_g, u_s


def sample_gaussian4(t_ws, t_wf, t_wg, base):
    """4-dim Gaussian copula, tau-matched pairwise to the vine (same
    rank correlations, no tail dependence). Order: (W, F, G, S)."""
    tau2rho = lambda t: np.sin(np.pi * (1 - 1 / t) / 2).ravel()
    r_wf, r_ws, r_wg = tau2rho(t_wf), tau2rho(t_ws), tau2rho(t_wg)
    # unconditional pairwise correlations implied by the vine (partial
    # correlation recursion; rho_GS|WF = 0)
    orth = lambda a, b: np.sqrt((1 - a ** 2) * (1 - b ** 2))
    r_fs = r_wf * r_ws + RHO_SF_GIVEN_W * orth(r_wf, r_ws)
    r_fg = r_wf * r_wg + RHO_FG_GIVEN_W * orth(r_wf, r_wg)
    r_gs = r_wg * r_ws + (RHO_FG_GIVEN_W * RHO_SF_GIVEN_W) * orth(r_wg, r_ws)

    d = len(r_wf)
    R = np.empty((d, 4, 4))
    R[:, 0, 0] = R[:, 1, 1] = R[:, 2, 2] = R[:, 3, 3] = 1.0
    R[:, 0, 1] = R[:, 1, 0] = r_wf
    R[:, 0, 2] = R[:, 2, 0] = r_wg
    R[:, 0, 3] = R[:, 3, 0] = r_ws
    R[:, 1, 2] = R[:, 2, 1] = r_fg
    R[:, 1, 3] = R[:, 3, 1] = r_fs
    R[:, 2, 3] = R[:, 3, 2] = r_gs
    L = np.linalg.cholesky(R)                      # (d, 4, 4)
    Z = np.stack([base["Z1"], base["Z2"], base["Z4"], base["Z3"]])  # (4, N)
    z = np.einsum("dij,jn->din", L, Z)             # (d, 4, N)
    u = stats.norm.cdf(z)
    return u[:, 0], u[:, 1], u[:, 2], u[:, 3]


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
        "U_ind_F": rng.uniform(0, 1, N_SIM),   # independence comparison
        "U_ind_S": rng.uniform(0, 1, N_SIM),
        "U_ind_G": rng.uniform(0, 1, N_SIM),
    }

    out = {k: [] for k in [
        "el_sub", "el_wx", "el_fl", "el_gw", "el_total", "var995_vine",
        "var995_gauss", "var995_indep", "tvar99_vine", "tvar99_gauss",
        "tvar99_indep", "uplift_pct",
        "tail_dep_wf", "tail_dep_ws", "tail_dep_wg",
        "theta_wf", "theta_ws", "theta_wg",
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
    # per-district year-view loss, kept so capital can be allocated to
    # districts by their contribution to the PORTFOLIO tail (Euler)
    year_loss = np.zeros((len(district_df), N_SIM), dtype=np.float32)

    def mix_with(u, w_sp, eps):
        z = stats.norm.ppf(np.clip(u, 1e-12, 1 - 1e-12))
        return stats.norm.cdf(np.sqrt(w_sp) * z + np.sqrt(1 - w_sp) * eps)

    for start in range(0, len(district_df), BATCH):
        chunk = district_df.iloc[start:start + BATCH]
        sub = chunk["sub_score"].values[:, None]
        wx = chunk["wx_score"].values[:, None]
        fl = chunk["fl_score"].values[:, None]
        fh = chunk["f_high"].values[:, None]
        flo = chunk["f_low"].values[:, None]
        swh = chunk["sw_high"].values[:, None]
        swl = chunk["sw_low"].values[:, None]
        gwf = chunk["gw_frac"].values[:, None]
        gws = chunk["gw_score"].values[:, None]
        t_ws = theta_ws(sub, wx)
        t_wf = theta_wf(wx, fl)
        t_wg = theta_wg(wx, gws)
        p_sub, p_wx, p_fl, p_gw, sev_s, sev_w, sev_f, sev_g = marginal_params(
            sub, wx, fh, flo, swh, swl, gwf)

        def total(u_w, u_f, u_g, u_s):
            lw = inv_mixed_cdf(u_w, np.broadcast_to(p_wx, u_w.shape), **sev_w)
            lf = inv_mixed_cdf(u_f, np.broadcast_to(p_fl, u_f.shape), **sev_f)
            lg = inv_mixed_cdf(u_g, np.broadcast_to(p_gw, u_g.shape), **sev_g)
            ls = inv_mixed_cdf(u_s, np.broadcast_to(p_sub, u_s.shape), **sev_s)
            return ls, lw, lf, lg, ls + lw + lf + lg

        u_w, u_f, u_g, u_s = sample_vine(t_ws, t_wf, t_wg, base)
        ls, lw, lf, lg, tot_v = total(u_w, u_f, u_g, u_s)
        _, _, _, _, tot_n = total(*sample_gaussian4(t_ws, t_wf, t_wg, base))
        _, _, _, _, tot_i = total(
            u_w,
            np.broadcast_to(base["U_ind_F"], u_w.shape),
            np.broadcast_to(base["U_ind_G"], u_w.shape),
            np.broadcast_to(base["U_ind_S"], u_w.shape))

        # year view: systemic factor + idiosyncratic district noise
        rng_b = np.random.default_rng(RNG_SEED + 1000 + start)
        shape = (len(chunk), N_SIM)
        eps_w = rng_b.standard_normal(shape)
        eps_f = rng_b.standard_normal(shape)
        eps_s = rng_b.standard_normal(shape)
        eps_g = rng_b.standard_normal(shape)
        uw_y = mix_with(u_w, SPATIAL_LOADING["w"], eps_w)
        uf_y = mix_with(u_f, SPATIAL_LOADING["f"], eps_f)
        us_y = mix_with(u_s, SPATIAL_LOADING["s"], eps_s)
        ug_y = mix_with(u_g, SPATIAL_LOADING["g"], eps_g)
        ls_y, lw_y, lf_y, lg_y, tot_y = total(uw_y, uf_y, ug_y, us_y)
        year_loss[start:start + len(chunk)] = tot_y.astype(np.float32)
        # independence year view: same idiosyncratic noise (common random
        # numbers), systemic factors independent across perils
        ufi_y = mix_with(np.broadcast_to(base["U_ind_F"], shape),
                         SPATIAL_LOADING["f"], eps_f)
        usi_y = mix_with(np.broadcast_to(base["U_ind_S"], shape),
                         SPATIAL_LOADING["s"], eps_s)
        ugi_y = mix_with(np.broadcast_to(base["U_ind_G"], shape),
                         SPATIAL_LOADING["g"], eps_g)
        ls_iy, _, lf_iy, lg_iy, _ = total(uw_y, ufi_y, ugi_y, usi_y)

        year["s_v"] += ls_y.sum(axis=0)
        year["w_v"] += lw_y.sum(axis=0)
        year["f_v"] += lf_y.sum(axis=0)
        year["g_v"] += lg_y.sum(axis=0)
        year["s_i"] += ls_iy.sum(axis=0)
        year["f_i"] += lf_iy.sum(axis=0)
        year["g_i"] += lg_iy.sum(axis=0)
        year["inc_s"] += (ls_y > 0).sum(axis=0)
        year["inc_w"] += (lw_y > 0).sum(axis=0)
        year["inc_f"] += (lf_y > 0).sum(axis=0)
        year["inc_g"] += (lg_y > 0).sum(axis=0)

        q = lambda a: np.quantile(a, 0.995, axis=1)
        t_v, t_n, t_i = tvar(tot_v), tvar(tot_n), tvar(tot_i)

        out["el_sub"].append(ls.mean(axis=1))
        out["el_wx"].append(lw.mean(axis=1))
        out["el_fl"].append(lf.mean(axis=1))
        out["el_gw"].append(lg.mean(axis=1))
        out["el_total"].append(tot_v.mean(axis=1))
        out["var995_vine"].append(q(tot_v))
        out["var995_gauss"].append(q(tot_n))
        out["var995_indep"].append(q(tot_i))
        out["tvar99_vine"].append(t_v)
        out["tvar99_gauss"].append(t_n)
        out["tvar99_indep"].append(t_i)
        out["uplift_pct"].append(100.0 * (t_v - t_i) / np.maximum(t_i, 1e-9))
        out["tail_dep_wf"].append((2.0 - 2.0 ** (1.0 / t_wf)).ravel())
        out["tail_dep_ws"].append((2.0 - 2.0 ** (1.0 / t_ws)).ravel())
        out["tail_dep_wg"].append((2.0 - 2.0 ** (1.0 / t_wg)).ravel())
        out["theta_wf"].append(t_wf.ravel())
        out["theta_ws"].append(t_ws.ravel())
        out["theta_wg"].append(t_wg.ravel())
        print(f"  simulated {min(start + BATCH, len(district_df))}/{len(district_df)} districts")

    res = {k: np.concatenate(v) for k, v in out.items()}

    # ---- Euler allocation of PORTFOLIO capital -------------------------
    # Capital is held against portfolio outcomes, not against each policy's
    # own worst year, so the charge must be allocated by each district's
    # expected loss GIVEN the portfolio is in its worst 1% of years:
    #     TVaR_i = E[L_i | L_portfolio >= VaR_99(L_portfolio)]
    # These allocations sum exactly to the portfolio TVaR (Euler additivity),
    # so cross-district diversification is credited rather than ignored.
    port = year_loss.mean(axis=0)                      # mean loss per policy
    k = max(int(N_SIM * 0.01), 1)
    bad = np.argpartition(port, -k)[-k:]
    res["tvar99_euler"] = year_loss[:, bad].mean(axis=1)
    res["el_year"] = year_loss.mean(axis=1)
    port_tvar = float(port[bad].mean())
    print(f"  portfolio TVaR99 {port_tvar:,.0f} /policy; "
          f"mean standalone TVaR99 {res['tvar99_vine'].mean():,.0f} "
          f"(diversification credit "
          f"{100 * (1 - port_tvar / res['tvar99_vine'].mean()):.0f}%)")
    return res, year


# ------------------------------------------------- good vs bad years


def year_analysis(year, n):
    """Summarise the simulated portfolio years for the analysis page.

    year: dict of shape-(N_SIM,) arrays — per-year losses summed over all
    n districts (vine and independence runs) and per-peril claim counts.
    All money figures are converted to per-policy averages (sum / n).
    NOTE: common random numbers across districts mean within-year spatial
    dependence is effectively perfect — a 'bad year' is bad everywhere at
    once, which overstates portfolio concentration vs reality; treat the
    bucket contrasts as an upper bound on year-to-year swing.
    """
    tv = (year["s_v"] + year["w_v"] + year["f_v"]) / n
    ti = (year["s_i"] + year["w_v"] + year["f_i"]) / n

    order = np.argsort(tv)
    order_i = np.argsort(ti)
    edges = [(0.0, 0.5, "good"), (0.5, 0.9, "typical"),
             (0.9, 0.99, "bad"), (0.99, 1.0, "catastrophic")]

    typical_mask = order[int(0.5 * N_SIM):int(0.9 * N_SIM)]
    typical_mean = float(tv[typical_mask].mean())

    buckets = []
    for lo, hi, label in edges:
        idx = order[int(lo * N_SIM):int(hi * N_SIM)]
        idx_i = order_i[int(lo * N_SIM):int(hi * N_SIM)]
        b = dict(
            label=label, share_pct=round(100 * (hi - lo), 1),
            mean_total=round(float(tv[idx].mean()), 1),
            mean_sub=round(float(year["s_v"][idx].mean() / n), 1),
            mean_wx=round(float(year["w_v"][idx].mean() / n), 1),
            mean_fl=round(float(year["f_v"][idx].mean() / n), 1),
            extra_vs_typical=round(float(tv[idx].mean()) - typical_mean, 1),
            inc_sub_pct=round(100 * float(year["inc_s"][idx].mean() / n), 2),
            inc_wx_pct=round(100 * float(year["inc_w"][idx].mean() / n), 2),
            inc_fl_pct=round(100 * float(year["inc_f"][idx].mean() / n), 2),
            indep_mean_total=round(float(ti[idx_i].mean()), 1),
        )
        buckets.append(b)

    def exceedance(t):
        srt = np.sort(t)[::-1]
        ranks = np.unique(np.round(np.geomspace(1, N_SIM / 2, 140)).astype(int))
        return [[round(float(N_SIM / k), 2), round(float(srt[k - 1]), 1)]
                for k in ranks]

    worst = int(order[-1])
    return dict(
        n_sim=N_SIM, n_districts=n,
        mean_total=round(float(tv.mean()), 1),
        mean_indep=round(float(ti.mean()), 1),
        buckets=buckets,
        exceedance=dict(vine=exceedance(tv), indep=exceedance(ti)),
        worst_year=dict(
            total=round(float(tv[worst]), 1),
            sub=round(float(year["s_v"][worst] / n), 1),
            wx=round(float(year["w_v"][worst] / n), 1),
            fl=round(float(year["f_v"][worst] / n), 1),
            inc_wx_pct=round(100 * float(year["inc_w"][worst] / n), 1),
            inc_fl_pct=round(100 * float(year["inc_f"][worst] / n), 1),
            inc_sub_pct=round(100 * float(year["inc_s"][worst] / n), 1),
        ),
    )


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
    n = float(n_districts)
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

    pts = gdf.geometry.representative_point()
    gdf["lon"], gdf["lat"] = pts.x, pts.y

    bng = gdf.to_crs(27700)
    bng_pts = bng.geometry.representative_point()
    targets = np.column_stack([bng_pts.x.values, bng_pts.y.values])

    print("scoring subsidence from BGS 625k geology...")
    gdf["sub_score"], gdf["geol"] = subsidence_from_bgs(bng)

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

    print("calibrating to published UK aggregates...")
    calibrate_frequency(gdf)
    calibrate_spatial(gdf)

    print(f"running copula simulation ({N_SIM:,} years/district)...")
    sim, year = simulate(gdf)
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

    modelled = float(gdf["el_total"].mean())
    print(f"  check: modelled loss cost for these four perils "
          f"£{modelled:,.2f}/policy vs ABI £{ABI_LOSS_PER_POLICY:,.2f} "
          f"({modelled / ABI_LOSS_PER_POLICY - 1:+.0%}); "
          f"{modelled / (ABI['total_home_paid'] / POLICIES):.0%} of the "
          f"£{ABI['total_home_paid'] / POLICIES:,.0f} all-perils home claims cost")

    print("writing geojson...")
    keep = ["name", "area", "sub_score", "wx_score", "fl_score", "gw_score",
            "geol", "wind_ms", "wdr_idx", "rain10_days", "precip_mm",
            "gust_rp50",
            "f_high", "f_low", "sw_high", "sw_low", "gw_frac",
            "el_sub", "el_wx", "el_fl", "el_gw",
            "el_total", "var995_vine", "tvar99_vine", "tvar99_gauss",
            "tvar99_indep", "tvar99_euler", "capital",
            "uplift_pct", "tail_dep_wf", "tail_dep_ws",
            "tail_dep_wg", "theta_wf", "theta_ws", "theta_wg",
            "premium", "group", "geometry"]
    out = gdf[keep].copy()
    out["geometry"] = out.geometry.simplify(0.0025, preserve_topology=True)
    round1 = {"wind_ms": 1, "wdr_idx": 1, "rain10_days": 1, "precip_mm": 0,
              "gust_rp50": 0}
    for col in keep:
        if col in ("name", "area", "geometry", "group", "geol"):
            continue
        if col in round1:
            out[col] = out[col].round(round1[col])
        elif "var" in col or col.startswith("el") or col == "premium":
            out[col] = out[col].round(1)
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
