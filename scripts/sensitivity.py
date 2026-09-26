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
  sev_sigma_up      the five cat-peril severity sigmas x1.1, means held
                    (heavier tails, same level) - a check: Gate 3 says
                    sigma cancels out of EL and capital, so it should
                    move nothing
  flood_freq_150    flood claim frequencies x1.5 (climate-change-style stress)
  erosion_no_intervention   erosion from the NFI (defences lapse) scenario
                    instead of the adopted SMP. Doubles as a check that the
                    exclusion is wired correctly: it raises erosion exposure
                    (England; Scotland keeps Dynamic Coast) and must move
                    EXACTLY ZERO districts between rating groups, which is
                    what "not in the premium" has to mean.
  depth_flat/half/steep   flood depth-damage relativities DEPTH_DAMAGE**p
                    for p = 0 / 0.5 / 1.5; p = 0 prices no depth at all.
                    Re-normalised per claim and the flood pin re-solved,
                    as build_model does, so the level holds by construction
                    and the scenario measures the spread only.
  depth_jrc_eu      DEPTH_DAMAGE replaced by the JRC Europe residential
                    depth-damage curve (Huizinga et al. 2017) - a
                    citable shape, though on a different basis (see
                    JRC_EU_RESIDENTIAL).

Reading the churn column: since capital stopped being Monte Carlo noise
(see build_model.simulate), churn measures the perturbation rather than the
noise floor - weak perturbations move fewer districts and strong ones move
more (before the fix every scenario sat near the same noise floor). The
check rows (sev_sigma_up, erosion_no_intervention) should read exactly
0.0 - anything else is a wiring fault. The exact figures move
whenever the model inputs do, so quote them from data/sensitivity.json,
never from this docstring.

Output: data/sensitivity.json (+ printed table)
"""

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm  # noqa: E402
from scores_real import sw_depth_severity, rs_depth_severity  # noqa: E402

import scores_real  # noqa: E402  (DEPTH_DAMAGE is read at call time)

bm.N_SIM = 8000
bm.BATCH = 100      # smaller than the main run: 8 scenarios back to back

ORIG = dict(theta_ws=bm.theta_ws, theta_wf=bm.theta_wf, theta_wg=bm.theta_wg,
            theta_we=bm.theta_we,
            marginal_params=bm.marginal_params, fields=bm._fields,
            rho_sf=bm.RHO_SF_GIVEN_W, rho_fg=bm.RHO_FG_GIVEN_W,
            rho_fe=bm.RHO_FE_GIVEN_W,
            depth_damage=list(scores_real.DEPTH_DAMAGE))
CTX = {}    # the full frame and the sample, for scenarios that must redo both


def scale_theta(k):
    def wrap(fn, cap):
        return lambda *a: np.clip(1.0 + (fn(*a) - 1.0) * k, 1.0, cap)
    bm.theta_ws = wrap(ORIG["theta_ws"], 3.5)
    bm.theta_wf = wrap(ORIG["theta_wf"], 3.5)
    bm.theta_wg = wrap(ORIG["theta_wg"], 3.5)
    bm.theta_we = wrap(ORIG["theta_we"], 3.5)


def sigma_up(f):
    """Severity sigmas x f with each MEAN held: mu drops by the matching
    (f^2 - 1) sigma^2 / 2, exactly as marginal_params' _median_for_mean
    would have set it.

    Until 2026-09-26 this scaled sigma after mu was fixed, so every mean
    rose by exp((f^2 - 1) sigma^2 / 2) - more for the wider perils - and
    the row labelled "heavier tails" measured an uneven severity LEVEL
    change (10.5% churn, E[loss] +3.7%). Held at the mean, Gate 3 says
    sigma cancels out of EL and capital exactly
    (test_severity_sigma_cannot_move_capital), so this row is now a check,
    like erosion's: it should move nothing.
    """
    def wrapped(*a):
        m = dict(ORIG["marginal_params"](*a))
        for key in ("sev_sub", "sev_wx", "sev_fl", "sev_gw", "sev_er"):
            m[key] = dict(m[key])
            s = m[key]["sigma"]
            m[key]["sigma"] = s * f
            m[key]["mu"] = m[key]["mu"] - (f ** 2 - 1.0) * s ** 2 / 2.0
        return m
    bm.marginal_params = wrapped


def flood_freq(f):
    def wrapped(*a):
        m = dict(ORIG["marginal_params"](*a))
        m["p_fl"] = m["p_fl"] * f
        return m
    bm.marginal_params = wrapped


def erosion_scenario(col):
    """Swap which NCERM scenario drives the erosion peril.

    `er_frac` normally holds er_head: the SMP (planned-defence) 2105 zone
    in England and Dynamic Coast in Scotland. The no-further-intervention
    case - defences allowed to lapse - is the interesting stress, and
    roughly doubles the national land loss. NCERM has no Scottish pair
    (Dynamic Coast publishes one management case), so Scotland keeps its
    er_head rather than being zeroed by an England-only column.
    """
    def wrapped(src):
        f = ORIG["fields"](src)
        f["er"] = np.where(src["er_basis"].values == "dynamiccoast",
                           src["er_head"].values,
                           src[col].values).astype(float)
        return f
    bm._fields = wrapped


def depth_curve(power):
    """Raise the depth-damage relativities to `power`, then re-derive
    everything build_model derives from them.

    DEPTH_DAMAGE is unanchored and, since 2026-09-26, shapes BOTH flood
    legs. power 0 flattens it to 1.0 everywhere (depth carries no price at
    all: severity by likelihood zone only); 0.5 halves its log-spread; 1.5
    stretches it by half again. Unlike the other scenarios this cannot
    live in marginal_params: the multipliers are normalised per claim on
    the FULL frame and the national flood pin (FLOOD_SEV_BLEND) is solved
    from them, so both are redone on the full frame and the sample's
    columns replaced - exactly the order build_model.main() uses.
    """
    set_depth_damage([d ** power for d in ORIG["depth_damage"]])


# JRC global flood depth-damage functions, Europe, residential buildings
# (Huizinga, de Moel & Szewczyk 2017, EUR 28552 EN, JRC105688): damage
# factor by water depth in metres. The one free, citable curve on the
# shelf - but NOT on the model's basis. It is an unconditional damage
# fraction that runs to 0 at 0 m, so its shallow end carries "no claim
# at all", which this model prices in FREQUENCY; DEPTH_DAMAGE is
# severity GIVEN a claim. Read it as a steep bracket, not an anchor.
JRC_EU_RESIDENTIAL = [(0.0, 0.0), (0.5, 0.25), (1.0, 0.40), (1.5, 0.50),
                      (2.0, 0.60), (3.0, 0.75), (4.0, 0.85), (5.0, 0.95),
                      (6.0, 1.00)]


def depth_jrc():
    """DEPTH_DAMAGE replaced by the JRC Europe residential curve, read at
    each band's midpoint depth (the same midpoints the model reports as
    mean depth). Only the shape matters: it is renormalised per claim."""
    xs, ys = zip(*JRC_EU_RESIDENTIAL)
    mids = [0.5 * (lo + hi) for _, lo, hi in scores_real.DEPTH_BANDS]
    set_depth_damage([float(v) for v in np.interp(mids, xs, ys)])


def set_depth_damage(curve):
    """Install a depth-damage curve and redo what build_model derives."""
    scores_real.DEPTH_DAMAGE = list(curve)
    print(f"  DEPTH_DAMAGE -> {[round(c, 3) for c in curve]}", flush=True)
    full, sample = CTX["full"], CTX["sample"]
    full["sw_sev"], _ = sw_depth_severity(
        full["name"].values, full["sw_high"].values, full["sw_low"].values,
        full["households"].values)
    full["rs_sev"], _ = rs_depth_severity(
        full["name"].values, full["households"].values)
    bm.calibrate_frequency(full)
    bm.calibrate_spatial(full)
    for col in ("sw_sev", "rs_sev"):
        sample[col] = full[col].values[::3]


def reset():
    scores_real.DEPTH_DAMAGE = list(ORIG["depth_damage"])
    for frame in ("full", "sample"):
        for col in ("sw_sev", "rs_sev"):
            if frame in CTX:
                CTX[frame][col] = CTX[f"{frame}_{col}"]
    if "flood_sev_blend" in ORIG:
        bm.FLOOD_SEV_BLEND = ORIG["flood_sev_blend"]
        bm.ABI_TARGET_FREQ.clear()
        bm.ABI_TARGET_FREQ.update(ORIG["abi_target_freq"])
    bm.theta_ws, bm.theta_wf, bm.theta_wg, bm.theta_we = (
        ORIG["theta_ws"], ORIG["theta_wf"], ORIG["theta_wg"], ORIG["theta_we"])
    bm.marginal_params = ORIG["marginal_params"]
    bm.RHO_FE_GIVEN_W = ORIG["rho_fe"]
    if "fields" in ORIG:
        bm._fields = ORIG["fields"]
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
    # erosion: defences allowed to lapse instead of maintained as planned
    "erosion_no_intervention": lambda: erosion_scenario("er_nfi105"),
    # flood depth-damage curve (unanchored; prices both flood legs)
    "depth_flat": lambda: depth_curve(0.0),
    "depth_half": lambda: depth_curve(0.5),
    "depth_steep": lambda: depth_curve(1.5),
    "depth_jrc_eu": depth_jrc,
}


def run_scenario(df):
    sim, year = bm.simulate(df)
    d = pd.DataFrame(sim)
    # Capital is the Euler-allocated share of portfolio tail risk, not the
    # district's standalone TVaR - and it is taken on the SAME analytic
    # basis as build_model: el_total, the sum of p*E[sev], never el_year,
    # the draw mean. This line subtracted el_year until 2026-08-25: the
    # last survivor of the 2026-08-18 analytic/draw sweep, which the
    # comment above it wrongly claimed it had followed. Measured on the
    # current baseline (912 districts, 1-in-3 sample) the stale basis put
    # capital 0.28% high and premium 0.01% high, and moved no district
    # across a rating group - so no published sensitivity conclusion turned
    # on it. Fixed for basis consistency, not because it changed an answer.
    d["premium"] = d["el_total"] + 0.06 * np.maximum(
        d["tvar99_euler"] - d["el_total"], 0.0)
    d["group"] = pd.qcut(d["premium"].rank(method="first"), 10,
                         labels=False) + 1
    ya = bm.year_analysis(year, len(df))
    cat = next(b for b in ya["buckets"] if b["label"] == "catastrophic")
    return dict(
        mean_el=round(float(d["el_total"].mean()), 1),
        mean_premium=round(float(d["premium"].mean()), 1),
        # erosion sits outside the premium, so it is reported on its own
        mean_el_erosion=round(float(d["el_er"].mean()), 1),
        mean_tvar99=round(float(d["tvar99_vine"].mean()), 1),
        mean_uplift_pct=round(float(d["uplift_pct"].mean()), 2),
        cat_year_cost=cat["mean_total"],
        cat_vs_indep_pct=round(100 * (cat["mean_total"]
                                      - cat["indep_mean_total"])
                               / cat["indep_mean_total"], 1),
    ), d["group"].values


def main():
    print("loading districts + scores (sampled 1-in-3)...", flush=True)
    # the same frame build_model.main() scores - never a copy of it
    gdf = bm.score_districts(bm.load_districts())
    # calibrate on the FULL set (as build_model does) so every scenario is
    # perturbing a properly calibrated baseline, then sample for speed
    bm.calibrate_frequency(gdf)
    bm.calibrate_spatial(gdf)
    ORIG["freq_scale"] = bm.FREQ_SCALE
    ORIG["spatial_scale"] = bm.SPATIAL_SCALE
    ORIG["flood_sev_blend"] = bm.FLOOD_SEV_BLEND
    ORIG["abi_target_freq"] = dict(bm.ABI_TARGET_FREQ)

    sample = gdf.iloc[::3].reset_index(drop=True)
    CTX["full"], CTX["sample"] = gdf, sample
    for frame in ("full", "sample"):
        for col in ("sw_sev", "rs_sev"):
            CTX[f"{frame}_{col}"] = CTX[frame][col].values.copy()
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
