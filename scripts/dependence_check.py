"""How much does peril dependence actually matter, once frequencies are real?

At calibrated UK frequencies a single policy claims on any peril in well
under 1% of years, so its 99% TVaR is essentially "the average claim, if
one happens" - a statistic almost blind to dependence, and noisy enough
that the vine-vs-independence difference is not distinguishable from zero
with 20k simulations.

This script measures dependence with a statistic that IS stable at these
frequencies: the probability that the SAME home suffers two or more perils
in one year, vine vs independence. It also reports a bootstrap confidence
interval on the TVaR difference, to show that the per-policy TVaR uplift
really is inside the noise.

Output: data/dependence.json
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm  # noqa: E402
from scores_real import (subsidence_from_bgs, weather_from_metoffice,  # noqa: E402
                         flood_from_agencies, groundwater_from_ea)

N_SIM = 400_000          # per district-batch; multi-peril years are rare
SAMPLE = 60              # districts, spread across the premium range
BATCH = 4


def main():
    print("loading districts + scores...", flush=True)
    gdf = bm.load_districts()
    bng = gdf.to_crs(27700)
    pts = bng.geometry.representative_point()
    targets = np.column_stack([pts.x.values, pts.y.values])
    gdf["sub_score"], _ = subsidence_from_bgs(bng)
    gdf["wx_score"], _ = weather_from_metoffice(targets)
    (gdf["fl_score"], gdf["f_high"], gdf["f_low"],
     gdf["sw_high"], gdf["sw_low"]) = flood_from_agencies(gdf["name"].values)
    gdf["gw_score"], gdf["gw_frac"] = groundwater_from_ea(gdf["name"].values)

    bm.calibrate_frequency(gdf)
    step = max(len(gdf) // SAMPLE, 1)
    sample = gdf.iloc[::step].reset_index(drop=True).iloc[:SAMPLE]
    print(f"sample: {len(sample)} districts x {N_SIM:,} years", flush=True)

    rng = np.random.default_rng(11)
    base = {
        "Theta": rng.uniform(1e-9, np.pi - 1e-9, N_SIM),
        "W": rng.exponential(1.0, N_SIM),
        "E1": rng.exponential(1.0, N_SIM),
        "E2": rng.exponential(1.0, N_SIM),
        "Z1": rng.standard_normal(N_SIM),
        "Z2": rng.standard_normal(N_SIM),
        "Z3": rng.standard_normal(N_SIM),
        "Z4": rng.standard_normal(N_SIM),
        "U_ind_F": rng.uniform(0, 1, N_SIM),
        "U_ind_G": rng.uniform(0, 1, N_SIM),
        "U_ind_S": rng.uniform(0, 1, N_SIM),
    }

    multi_v = multi_i = years = 0
    tv_all, ti_all = [], []

    for start in range(0, len(sample), BATCH):
        chunk = sample.iloc[start:start + BATCH]
        sub = chunk["sub_score"].values[:, None]
        wx = chunk["wx_score"].values[:, None]
        fl = chunk["fl_score"].values[:, None]
        p_sub, p_wx, p_fl, p_gw, s_s, s_w, s_f, s_g = bm.marginal_params(
            sub, wx, chunk["f_high"].values[:, None],
            chunk["f_low"].values[:, None], chunk["sw_high"].values[:, None],
            chunk["sw_low"].values[:, None], chunk["gw_frac"].values[:, None])
        t_ws, t_wf = bm.theta_ws(sub, wx), bm.theta_wf(wx, fl)
        t_wg = bm.theta_wg(wx, chunk["gw_score"].values[:, None])

        def losses(u_w, u_f, u_g, u_s):
            lw = bm.inv_mixed_cdf(u_w, np.broadcast_to(p_wx, u_w.shape), **s_w)
            lf = bm.inv_mixed_cdf(u_f, np.broadcast_to(p_fl, u_f.shape), **s_f)
            lg = bm.inv_mixed_cdf(u_g, np.broadcast_to(p_gw, u_g.shape), **s_g)
            ls = bm.inv_mixed_cdf(u_s, np.broadcast_to(p_sub, u_s.shape), **s_s)
            n_perils = ((lw > 0).astype(np.int8) + (lf > 0) + (lg > 0) + (ls > 0))
            return lw + lf + lg + ls, n_perils

        u_w, u_f, u_g, u_s = bm.sample_vine(t_ws, t_wf, t_wg, base)
        tot_v, n_v = losses(u_w, u_f, u_g, u_s)
        shape = tot_v.shape
        tot_i, n_i = losses(u_w,
                            np.broadcast_to(base["U_ind_F"], shape),
                            np.broadcast_to(base["U_ind_G"], shape),
                            np.broadcast_to(base["U_ind_S"], shape))

        multi_v += int((n_v >= 2).sum())
        multi_i += int((n_i >= 2).sum())
        years += tot_v.size
        tv_all.append(tot_v.astype(np.float32))
        ti_all.append(tot_i.astype(np.float32))
        print(f"  {min(start + BATCH, len(sample))}/{len(sample)} districts",
              flush=True)

    tv = np.concatenate([a.ravel() for a in tv_all])
    ti = np.concatenate([a.ravel() for a in ti_all])

    def tvar(a, q=0.99):
        k = max(int(a.size * (1 - q)), 1)
        return float(np.partition(a, -k)[-k:].mean())

    # bootstrap the TVaR difference to size the Monte Carlo noise
    rs = np.random.default_rng(3)
    diffs = []
    for _ in range(120):
        idx = rs.integers(0, tv.size, size=min(tv.size, 400_000))
        diffs.append(100 * (tvar(tv[idx]) / tvar(ti[idx]) - 1))
    lo, hi = np.percentile(diffs, [2.5, 97.5])

    out = dict(
        districts=int(len(sample)), years_per_district=int(N_SIM),
        multi_peril_vine=multi_v / years,
        multi_peril_indep=multi_i / years,
        multi_peril_ratio=(multi_v / max(multi_i, 1)),
        tvar99_vine=tvar(tv), tvar99_indep=tvar(ti),
        tvar_uplift_pct=100 * (tvar(tv) / tvar(ti) - 1),
        tvar_uplift_ci=[float(lo), float(hi)],
    )
    with open(os.path.join("data", "dependence.json"), "w") as fh:
        json.dump(out, fh, indent=1)

    print("\n--- dependence at calibrated frequencies ---")
    print(f"P(2+ perils in one year)  vine {out['multi_peril_vine']:.3e}"
          f"  indep {out['multi_peril_indep']:.3e}"
          f"  ratio x{out['multi_peril_ratio']:.2f}")
    print(f"per-policy TVaR99 uplift  {out['tvar_uplift_pct']:+.1f}% "
          f"(95% CI {lo:+.1f}% to {hi:+.1f}%)")
    print("wrote data/dependence.json")


if __name__ == "__main__":
    main()
