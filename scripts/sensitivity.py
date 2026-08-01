"""Sensitivity analysis: which model assumptions actually move the answer?

Re-runs the vine simulation on a 1-in-3 district sample (stratified by
premium ordering is unnecessary — systematic sampling keeps the geography)
with N_SIM=8000 under perturbed assumptions, and reports for each
scenario: mean expected loss, mean technical premium, mean TVaR99, mean
copula uplift, catastrophic-year cost, and the share of sampled districts
whose rating-group decile changes vs the sampled baseline.

Scenarios:
  baseline          as shipped (sampled - numbers differ slightly from full run)
  theta_low/high    Gumbel dependence excess (theta-1) x0.75 / x1.25, all pairs
  rho2_zero/high    tree-2 partial correlations 0 / doubled (FG 0.5, FS 0.3)
  sev_sigma_up      all severity sigmas x1.1 (heavier tails)
  flood_freq_150    flood claim frequencies x1.5 (climate-change-style stress)

Output: data/sensitivity.json (+ printed table)
"""

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm  # noqa: E402
from scores_real import (subsidence_from_bgs, weather_from_metoffice,  # noqa: E402
                         flood_from_agencies, groundwater_from_ea)

bm.N_SIM = 8000
bm.BATCH = 100      # smaller than the main run: 7 scenarios back to back

ORIG = dict(theta_ws=bm.theta_ws, theta_wf=bm.theta_wf, theta_wg=bm.theta_wg,
            marginal_params=bm.marginal_params,
            rho_sf=bm.RHO_SF_GIVEN_W, rho_fg=bm.RHO_FG_GIVEN_W)


def scale_theta(k):
    def wrap(fn, cap):
        return lambda *a: np.clip(1.0 + (fn(*a) - 1.0) * k, 1.0, cap)
    bm.theta_ws = wrap(ORIG["theta_ws"], 3.5)
    bm.theta_wf = wrap(ORIG["theta_wf"], 3.5)
    bm.theta_wg = wrap(ORIG["theta_wg"], 3.5)


def sigma_up(f):
    def wrapped(*a):
        p_sub, p_wx, p_fl, p_gw, s_s, s_w, s_f, s_g = ORIG["marginal_params"](*a)
        for s in (s_s, s_w, s_f, s_g):
            s["sigma"] = s["sigma"] * f
        return p_sub, p_wx, p_fl, p_gw, s_s, s_w, s_f, s_g
    bm.marginal_params = wrapped


def flood_freq(f):
    def wrapped(*a):
        p_sub, p_wx, p_fl, p_gw, s_s, s_w, s_f, s_g = ORIG["marginal_params"](*a)
        return p_sub, p_wx, p_fl * f, p_gw, s_s, s_w, s_f, s_g
    bm.marginal_params = wrapped


def reset():
    bm.theta_ws, bm.theta_wf, bm.theta_wg = (
        ORIG["theta_ws"], ORIG["theta_wf"], ORIG["theta_wg"])
    bm.marginal_params = ORIG["marginal_params"]
    bm.RHO_SF_GIVEN_W = ORIG["rho_sf"]
    bm.RHO_FG_GIVEN_W = ORIG["rho_fg"]
    # scenario wrappers call the original marginal_params, which reads the
    # module-level FREQ_SCALE - restore the calibrated values each time
    if "freq_scale" in ORIG:
        bm.FREQ_SCALE = ORIG["freq_scale"]
        bm.SPATIAL_SCALE = ORIG["spatial_scale"]


SCENARIOS = {
    "baseline": lambda: None,
    "theta_low": lambda: scale_theta(0.75),
    "theta_high": lambda: scale_theta(1.25),
    "rho2_zero": lambda: (setattr(bm, "RHO_SF_GIVEN_W", 0.0),
                          setattr(bm, "RHO_FG_GIVEN_W", 0.0)),
    "rho2_high": lambda: (setattr(bm, "RHO_SF_GIVEN_W", 0.30),
                          setattr(bm, "RHO_FG_GIVEN_W", 0.50)),
    "sev_sigma_up": lambda: sigma_up(1.10),
    "flood_freq_150": lambda: flood_freq(1.50),
}


def run_scenario(df):
    sim, year = bm.simulate(df)
    d = pd.DataFrame(sim)
    # same basis as build_model: capital is the Euler-allocated share of
    # portfolio tail risk, not the district's standalone TVaR
    d["premium"] = d["el_total"] + 0.06 * np.maximum(
        d["tvar99_euler"] - d["el_year"], 0.0)
    d["group"] = pd.qcut(d["premium"].rank(method="first"), 10,
                         labels=False) + 1
    ya = bm.year_analysis(year, len(df))
    cat = next(b for b in ya["buckets"] if b["label"] == "catastrophic")
    return dict(
        mean_el=round(float(d["el_total"].mean()), 1),
        mean_premium=round(float(d["premium"].mean()), 1),
        mean_tvar99=round(float(d["tvar99_vine"].mean()), 1),
        mean_uplift_pct=round(float(d["uplift_pct"].mean()), 2),
        cat_year_cost=cat["mean_total"],
        cat_vs_indep_pct=round(100 * (cat["mean_total"]
                                      - cat["indep_mean_total"])
                               / cat["indep_mean_total"], 1),
    ), d["group"].values


def main():
    print("loading districts + scores (sampled 1-in-3)...", flush=True)
    gdf = bm.load_districts()
    bng = gdf.to_crs(27700)
    bng_pts = bng.geometry.representative_point()
    targets = np.column_stack([bng_pts.x.values, bng_pts.y.values])
    gdf["sub_score"], gdf["geol"] = subsidence_from_bgs(bng)
    gdf["wx_score"], _ = weather_from_metoffice(targets)
    (gdf["fl_score"], gdf["f_high"], gdf["f_low"],
     gdf["sw_high"], gdf["sw_low"]) = flood_from_agencies(gdf["name"].values)
    gdf["gw_score"], gdf["gw_frac"] = groundwater_from_ea(gdf["name"].values)
    # calibrate on the FULL set (as build_model does) so every scenario is
    # perturbing a properly calibrated baseline, then sample for speed
    bm.calibrate_frequency(gdf)
    bm.calibrate_spatial(gdf)
    ORIG["freq_scale"] = bm.FREQ_SCALE
    ORIG["spatial_scale"] = bm.SPATIAL_SCALE

    sample = gdf.iloc[::3].reset_index(drop=True)
    print(f"sample: {len(sample)} districts, N_SIM={bm.N_SIM}", flush=True)

    results, base_groups = {}, None
    for name, setup in SCENARIOS.items():
        reset()
        setup()
        print(f"scenario {name}...", flush=True)
        res, groups = run_scenario(sample)
        if name == "baseline":
            base_groups = groups
            res["group_churn_pct"] = 0.0
        else:
            res["group_churn_pct"] = round(
                100 * float((groups != base_groups).mean()), 1)
        results[name] = res
        print(f"  {res}", flush=True)
    reset()

    with open(os.path.join("data", "sensitivity.json"), "w") as fh:
        json.dump(results, fh)
    print("wrote data/sensitivity.json", flush=True)


if __name__ == "__main__":
    main()
