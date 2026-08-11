"""Property tests for the vine-copula machinery.

These check the maths that the whole model rests on: that the sampler
produces valid copula draws, that the Gumbel h-function inverse really
inverts, and that the dependence actually present in the samples matches
the dependence we asked for.

Run:  .venv/Scripts/python -m pytest tests -q
"""

import os
import sys

import numpy as np
import pytest
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_model as bm  # noqa: E402

N = 40_000
SEED = 7


@pytest.fixture(autouse=True)
def _reset_pinned_references():
    """Keep the suite order-independent.

    scores_real pins two module-level normalisation references the first
    time a present-day call sets them (`_FLOOD_REF`, `_DEPTH_REF`), so the
    climate run can be expressed on the present-day scale instead of
    renormalising its own signal away. That is right in production, where
    build_model runs present-day then climate in one process.

    In a test process it means state leaks between tests. Nothing reads it
    today - no test passes climate=True - but the first one that does would
    inherit whichever test happened to run before it, and fail only inside
    the suite while passing alone. Resetting is free; debugging that is not.
    """
    import scores_real as sr
    sr._FLOOD_REF = None
    sr._DEPTH_REF = None
    yield
    sr._FLOOD_REF = None
    sr._DEPTH_REF = None


@pytest.fixture(scope="module")
def base():
    rng = np.random.default_rng(SEED)
    return {
        "Theta": rng.uniform(1e-9, np.pi - 1e-9, N),
        "W": rng.exponential(1.0, N),
        "E1": rng.exponential(1.0, N),
        "E2": rng.exponential(1.0, N),
        "Z1": rng.standard_normal(N),
        "Z2": rng.standard_normal(N),
        "Z3": rng.standard_normal(N),
        "Z4": rng.standard_normal(N),
        "Z5": rng.standard_normal(N),
    }


# Standard theta set for the 5-dim vine: (weather-subsidence,
# weather-flood, weather-groundwater, weather-erosion).
THETAS = (np.array([[1.9]]), np.array([[2.6]]),
          np.array([[1.7]]), np.array([[2.1]]))


# ---------------------------------------------------------------- h-function

@pytest.mark.parametrize("theta", [1.05, 1.5, 2.0, 3.0])
def test_hinv_gumbel_inverts_h_gumbel(theta):
    rng = np.random.default_rng(SEED)
    u = rng.uniform(0.02, 0.98, (1, 4000))
    v = rng.uniform(0.02, 0.98, (1, 4000))
    th = np.array([[theta]])
    t = bm.h_gumbel(v, u, th)
    v_rec = bm.hinv_gumbel(t, u, th)
    assert np.abs(v - v_rec).max() < 1e-8


def test_h_gumbel_is_a_valid_conditional_cdf():
    """h(v|u) must be a CDF in v: in [0,1] and non-decreasing."""
    u = np.full((1, 500), 0.4)
    v = np.linspace(1e-6, 1 - 1e-6, 500)[None, :]
    h = bm.h_gumbel(v, u, np.array([[2.0]]))
    assert h.min() >= 0.0 and h.max() <= 1.0
    assert np.all(np.diff(h[0]) >= -1e-12)


def test_independence_copula_limit():
    """theta -> 1 is the independence copula, so h(v|u) -> v."""
    u = np.full((1, 200), 0.63)
    v = np.linspace(0.01, 0.99, 200)[None, :]
    h = bm.h_gumbel(v, u, np.array([[1.0 + 1e-9]]))
    assert np.abs(h - v).max() < 1e-5


# ---------------------------------------------------------------- sampler

def test_vine_margins_are_uniform(base):
    draws = bm.sample_vine(*THETAS, base)
    assert len(draws) == 5           # W, F, G, S, E
    for u in draws:
        u = np.asarray(u).ravel()
        assert u.min() > 0 and u.max() < 1
        # Kolmogorov-Smirnov against U(0,1)
        assert stats.kstest(u, "uniform").pvalue > 0.01


@pytest.mark.parametrize("theta", [1.4, 2.0, 2.8])
def test_gumbel_pair_recovers_kendall_tau(theta, base):
    """Sampled (W,F) must show tau = 1 - 1/theta."""
    u1, u2 = bm.sample_gumbel(np.array([[theta]]), base)
    tau = stats.kendalltau(u1.ravel()[:6000], u2.ravel()[:6000]).statistic
    assert abs(tau - (1 - 1 / theta)) < 0.03


def test_vine_pairs_recover_their_taus(base):
    u_w, u_f, u_g, u_s, u_e = bm.sample_vine(*THETAS, base)
    cut = slice(0, 6000)
    tau = lambda a, b: stats.kendalltau(np.asarray(a).ravel()[cut],
                                        np.asarray(b).ravel()[cut]).statistic
    assert abs(tau(u_w, u_f) - (1 - 1 / 2.6)) < 0.03
    assert abs(tau(u_w, u_s) - (1 - 1 / 1.9)) < 0.03
    assert abs(tau(u_w, u_g) - (1 - 1 / 1.7)) < 0.03
    assert abs(tau(u_w, u_e) - (1 - 1 / 2.1)) < 0.03
    # tree-2 pairs stay positively but weakly dependent
    assert 0.0 < tau(u_f, u_g) < tau(u_w, u_f)
    assert 0.0 < tau(u_f, u_e) < tau(u_w, u_f)


def test_erosion_is_the_strongest_tree2_pair(base):
    """rho_FE|W (0.35) exceeds rho_FG|W (0.25) and rho_FS|W (0.15), so the
    residual flood-erosion link must come out strongest: coastal flooding
    and erosion are driven by the same surge events."""
    u_w, u_f, u_g, u_s, u_e = bm.sample_vine(*THETAS, base)
    cut = slice(0, 12000)
    # partial association given W, measured on the tree-1 residuals
    resid = lambda u, th: bm.h_gumbel(np.asarray(u), np.asarray(u_w), th)
    r_f = resid(u_f, THETAS[1]).ravel()[cut]
    pairs = {
        "e": stats.kendalltau(r_f, resid(u_e, THETAS[3]).ravel()[cut]).statistic,
        "g": stats.kendalltau(r_f, resid(u_g, THETAS[2]).ravel()[cut]).statistic,
        "s": stats.kendalltau(r_f, resid(u_s, THETAS[0]).ravel()[cut]).statistic,
    }
    assert pairs["e"] > pairs["g"] > pairs["s"] > 0


def test_gumbel_has_upper_tail_dependence_and_gaussian_does_not(base):
    """The whole reason for choosing Gumbel: joint extremes survive."""
    theta = 2.5
    t = np.array([[theta]])
    u1, u2 = bm.sample_gumbel(t, base)
    q = 0.99
    joint_g = np.mean((u1.ravel() > q) & (u2.ravel() > q)) / (1 - q)

    ug_w, ug_f, _, _, _ = bm.sample_gaussian5(
        np.array([[1.5]]), t, np.array([[1.5]]), np.array([[1.5]]), base)
    joint_n = np.mean((np.asarray(ug_w).ravel() > q)
                      & (np.asarray(ug_f).ravel() > q)) / (1 - q)

    lambda_u = 2 - 2 ** (1 / theta)
    assert joint_g > 0.5 * lambda_u          # near the theoretical value
    assert joint_g > joint_n + 0.05          # and clearly above Gaussian


def test_gaussian5_margins_uniform_and_taus_match(base):
    t_ws, t_wf, t_wg, t_we = (np.array([[1.8]]), np.array([[2.4]]),
                              np.array([[1.6]]), np.array([[2.0]]))
    draws = bm.sample_gaussian5(t_ws, t_wf, t_wg, t_we, base)
    assert len(draws) == 5
    for u in draws:
        assert stats.kstest(np.asarray(u).ravel(), "uniform").pvalue > 0.01
    u_w, u_f, u_g, u_s, u_e = draws
    cut = slice(0, 6000)
    tau = lambda a, b: stats.kendalltau(np.asarray(a).ravel()[cut],
                                        np.asarray(b).ravel()[cut]).statistic
    # tau-matched to the vine's tree-1 pairs
    assert abs(tau(u_w, u_f) - (1 - 1 / 2.4)) < 0.04
    assert abs(tau(u_w, u_s) - (1 - 1 / 1.8)) < 0.04
    assert abs(tau(u_w, u_e) - (1 - 1 / 2.0)) < 0.04


def test_gaussian5_correlation_matrix_stays_positive_definite():
    """The vine-implied 5x5 matrix is built from partial correlations, so it
    must be PD across the whole theta range - otherwise the Cholesky in
    sample_gaussian5 blows up mid-run."""
    grid = np.linspace(1.0 + 1e-6, 3.0, 12)
    cols = [g.ravel()[:, None] for g in np.meshgrid(grid, grid, grid, grid)]
    base = {k: np.zeros(1) for k in ("Theta", "W", "E1", "E2",
                                     "Z1", "Z2", "Z3", "Z4", "Z5")}
    base["Theta"] = np.full(1, 1.0)
    # exercise the same matrix construction the sampler uses
    u = bm.sample_gaussian5(cols[0], cols[1], cols[2], cols[3], base)
    assert all(np.all(np.isfinite(np.asarray(x))) for x in u)


# ---------------------------------------------------------------- marginals

def test_inv_mixed_cdf_matches_bernoulli_lognormal():
    rng = np.random.default_rng(SEED)
    u = rng.uniform(0, 1, (1, 200_000))
    p = np.full((1, 200_000), 0.05)
    mu, sigma = np.log(10_000.0), 0.9
    loss = bm.inv_mixed_cdf(u, p, mu, sigma)
    assert abs((loss > 0).mean() - 0.05) < 0.002           # frequency
    expected_mean = 0.05 * np.exp(mu + sigma ** 2 / 2)     # E[B]*E[LN]
    assert abs(loss.mean() / expected_mean - 1) < 0.05


def fields(**over):
    """Default marginal_params inputs, overridable per test."""
    f = dict(sub=0.5, wx=0.5, f_high=0.1, f_low=0.2, sw_high=0.1,
             sw_low=0.2, gw_frac=0.1, sw_sev=1.0, er=0.0)
    f.update(over)
    return {k: np.array([v], dtype=float) for k, v in f.items()}


def test_severity_medians_hit_published_means():
    """Severity params are set so each lognormal MEAN equals the ABI figure."""
    m = bm.marginal_params(fields())
    mean = lambda s: float(np.exp(s["mu"] + s["sigma"] ** 2 / 2))
    assert abs(mean(m["sev_sub"]) / bm.ABI["sev_subsidence"] - 1) < 1e-6
    assert abs(mean(m["sev_wx"]) / bm.ABI["sev_weather"] - 1) < 1e-6
    assert abs(mean(m["sev_gw"]) / bm.ABI["sev_groundwater"] - 1) < 1e-6
    assert abs(mean(m["sev_er"]) / bm.ABI["sev_erosion"] - 1) < 1e-6


def test_theta_functions_stay_in_valid_gumbel_range():
    grid = np.linspace(0, 1, 21)
    a, b = np.meshgrid(grid, grid)
    for fn, cap in ((bm.theta_ws, 2.5), (bm.theta_wf, 3.0),
                    (bm.theta_wg, 2.4), (bm.theta_we, 2.6)):
        th = fn(a, b)
        assert th.min() >= 1.0 and th.max() <= cap + 1e-9


# ---------------------------------------------------------------- erosion

def test_erosion_frequency_annualises_over_the_horizon():
    """A district with x% of its area in the 2105 zone loses that share of
    properties across the horizon, so the annual hazard is x/80."""
    m = bm.marginal_params(fields(er=0.24))
    assert abs(float(m["p_er"][0]) - 0.24 / bm.EROSION_HORIZON_YEARS) < 1e-12
    assert float(bm.marginal_params(fields(er=0.0))["p_er"][0]) == 0.0


def test_erosion_is_not_touched_by_the_abi_frequency_scaling():
    """The other perils are scaled to published ABI payouts. Erosion has no
    published payout - it is excluded from cover - so its level must come
    from the physical construction alone."""
    old = dict(bm.FREQ_SCALE)
    try:
        bm.FREQ_SCALE = {"sub": 3.0, "wx": 3.0, "fl": 3.0, "gw": 3.0}
        scaled = float(bm.marginal_params(fields(er=0.1))["p_er"][0])
        bm.FREQ_SCALE = {"sub": 1.0, "wx": 1.0, "fl": 1.0, "gw": 1.0}
        plain = float(bm.marginal_params(fields(er=0.1))["p_er"][0])
    finally:
        bm.FREQ_SCALE = old
    assert scaled == plain


# ------------------------------------------------- surface-water depth

def test_depth_multiplier_raises_surface_water_severity():
    """A deeper district must carry a higher surface-water severity, with
    the fluvial leg untouched."""
    shallow = bm.marginal_params(fields(sw_sev=0.6))
    deep = bm.marginal_params(fields(sw_sev=1.8))
    assert float(deep["sev_fl"]["mu"][0]) > float(shallow["sev_fl"]["mu"][0])
    # with no surface water at all the multiplier cannot matter
    a = bm.marginal_params(fields(sw_high=0.0, sw_low=0.0, sw_sev=0.6))
    b = bm.marginal_params(fields(sw_high=0.0, sw_low=0.0, sw_sev=1.8))
    assert abs(float(a["sev_fl"]["mu"][0])
               - float(b["sev_fl"]["mu"][0])) < 1e-12


def test_depth_severity_is_normalised_and_monotone(tmp_path, monkeypatch):
    """sw_depth_severity must (a) leave the exposure-weighted national mean
    at 1.0, so the ABI calibration is untouched, and (b) rank a deep
    district above a shallow one."""
    import scores_real as sr

    csv_text = ["name,d02_high,d02_low,d03_high,d03_low,d06_high,d06_low,"
                "d09_high,d09_low,d12_high,d12_low"]
    # SHALLOW: well-covered (half the envelope is mapped past 0.2 m) but
    # almost none of it runs deep
    csv_text.append("SHALLOW,0.0,0.050,0.0,0.010,0.0,0.001,0.0,0.000,0.0,0.000")
    # DEEP: most of the envelope is over 0.6 m
    csv_text.append("DEEP,0.0,0.090,0.0,0.080,0.0,0.070,0.0,0.050,0.0,0.030")
    # DRY: no surface water at all -> must fall back to 1.0
    csv_text.append("DRY,0.0,0.000,0.0,0.000,0.0,0.000,0.0,0.000,0.0,0.000")
    (tmp_path / "sw_depth.csv").write_text("\n".join(csv_text))
    (tmp_path / "country.csv").write_text(
        "name,country,share\nSHALLOW,England,1.0\nDEEP,England,1.0\n"
        "DRY,England,1.0\n")
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    names = np.array(["SHALLOW", "DEEP", "DRY"])
    sw_low = np.array([0.10, 0.10, 0.0])
    households = np.array([1000.0, 1000.0, 1000.0])
    # half the envelope sits in the high-likelihood band in each case; the
    # depth split is what this test is about
    mult, depth = sr.sw_depth_severity(names, sw_low * 0.5, sw_low, households)

    assert mult[1] > mult[0]                      # deeper costs more
    assert mult[2] == 1.0                         # no data -> flat
    assert depth[1] > depth[0]
    # normalised across the districts that have data
    assert abs(float(np.average(mult[:2], weights=households[:2])) - 1.0) < 1e-9


def test_erosion_expected_loss_is_analytic_not_simulated(monkeypatch):
    """Erosion's annual probability is ~1e-5, so even 20,000 simulated years
    give well under one event and a simulated mean would be noise. simulate()
    must return the closed form p·E[severity] instead — exactly, and even
    with a simulation far too short to have produced a single event."""
    import pandas as pd

    monkeypatch.setattr(bm, "N_SIM", 200)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = pd.DataFrame({
        "sub_score": [0.5, 0.2], "wx_score": [0.5, 0.4],
        "fl_score": [0.3, 0.6], "gw_score": [0.2, 0.1],
        "er_score": [0.8, 0.0],
        "f_high": [0.1, 0.0], "f_low": [0.2, 0.05],
        "sw_high": [0.05, 0.01], "sw_low": [0.1, 0.03],
        "gw_frac": [0.1, 0.0], "sw_sev": [1.0, 1.0],
        "er_frac": [0.24, 0.0], "households": [1000.0, 2000.0],
    })
    sim, _ = bm.simulate(df)

    expected = 0.24 / bm.EROSION_HORIZON_YEARS * bm.ABI["sev_erosion"]
    assert abs(sim["el_er"][0] - expected) / expected < 1e-9
    assert sim["el_er"][1] == 0.0                     # no exposure, no loss
    # and the five-peril total is the four-peril total plus exactly that
    assert abs((sim["el_total5"][0] - sim["el_total"][0])
               - sim["el_er"][0]) < 1e-6


def test_capital_allocation_is_stable_across_seeds():
    """The premium must not depend on the RNG seed.

    Capital is the Euler allocation of portfolio tail risk, averaged over
    the worst 1% of years - only N_SIM/100 draws, in which a district
    claims once or twice at calibrated frequencies. Averaging REALISED
    losses there made capital, and so the published rating group, largely
    Monte Carlo noise. The allocation therefore averages the CONDITIONAL
    expected loss given each year's systemic draw, which is smooth.

    Measured head to head on this fixture at N_SIM=4000:

        realised (old)      corr 0.49 / 0.39,  median move 20.6%
        conditional (new)   corr 0.97 / 1.00,  median move  6.4%

    and at the production N_SIM=20000 the conditional estimator reaches
    corr 0.9985. The thresholds below sit in the gap, so a regression to
    the realised estimator fails this test rather than silently shipping a
    noise-driven rating group. N_SIM is kept small to keep CI quick; that
    is the harder setting, not the easier one.
    """
    import pandas as pd
    import build_model as m
    rng = np.random.default_rng(3)
    n = 60
    df = pd.DataFrame({
        "sub_score": rng.uniform(0.05, 1.0, n),
        "wx_score": rng.uniform(0.05, 1.0, n),
        "fl_score": rng.uniform(0.0, 1.0, n),
        "gw_score": rng.uniform(0.0, 1.0, n),
        "er_score": rng.uniform(0.0, 0.5, n),
        "f_high": rng.uniform(0, 0.2, n), "f_low": rng.uniform(0.2, 0.5, n),
        "sw_high": rng.uniform(0, 0.1, n), "sw_low": rng.uniform(0.1, 0.3, n),
        "gw_frac": rng.uniform(0, 0.3, n),
        "sw_sev": rng.uniform(0.8, 1.3, n),
        "er_frac": rng.uniform(0, 0.05, n),
        "households": rng.uniform(500, 40_000, n),
    })
    n_sim, batch, seed = m.N_SIM, m.BATCH, m.RNG_SEED
    m.N_SIM, m.BATCH = 4000, 30
    try:
        out = {}
        for s in (42, 43):
            m.RNG_SEED = s
            sim, _ = m.simulate(df)
            out[s] = sim["tvar99_euler"]
    finally:
        m.N_SIM, m.BATCH, m.RNG_SEED = n_sim, batch, seed

    a, b = out[42], out[43]
    corr = float(np.corrcoef(a, b)[0, 1])
    rel = np.abs(b - a) / np.maximum(a, 1e-9)
    assert corr > 0.95, f"allocation not reproducible across seeds (r={corr:.3f})"
    assert np.median(rel) < 0.12, f"median move {np.median(rel):.1%} across seeds"


def test_climate_scenario_does_not_clamp_away_the_districts_that_improve():
    """The rivers/sea future is a separate EA model run, not an uplift.

    flood_future() clamps f_low >= f_high to enforce BAND nesting inside
    the future. It is easy to misread that as "the future should contain
    the present" and extend it to np.maximum(future, present) - which
    would silently rewrite every district whose flood band shrinks and
    delete the finding README states under "Rivers/sea is not a strict
    uplift". Nothing else would look wrong: the national +37% growth is
    unaffected, so the headline would still read correctly.

    So assert the decreases survive the function.
    """
    import scores_real as sr
    data = os.path.join(os.path.dirname(__file__), "..", "data")
    if not os.path.exists(os.path.join(data, "flood_fractions_cc.csv")):
        pytest.skip("climate flood fractions not fetched")

    names, f_high, f_low, sw_high, sw_low = [], [], [], [], []
    with open(os.path.join(data, "flood_fractions.csv"), newline="") as fh:
        import csv as _csv
        for row in _csv.DictReader(fh):
            names.append(row["name"])
            f_high.append(float(row["f_high"]))
            f_low.append(float(row["f_low"]))
    sw = {}
    with open(os.path.join(data, "sw_fractions.csv"), newline="") as fh:
        import csv as _csv
        for row in _csv.DictReader(fh):
            sw[row["name"]] = (float(row["sw_high"]), float(row["sw_low"]))
    sw_high = [sw.get(n, (0.0, 0.0))[0] for n in names]
    sw_low = [sw.get(n, (0.0, 0.0))[1] for n in names]

    names = np.array(names)
    out = sr.flood_future(names, np.array(f_high), np.array(f_low),
                          np.array(sw_high), np.array(sw_low))
    assert out is not None
    fh_cc, fl_cc, swh_cc, swl_cc, covered = out

    # the band nesting the clamp DOES enforce
    assert (fl_cc >= fh_cc - 1e-12).all(), "1-in-1000 envelope lost its zone"
    assert (swl_cc >= swh_cc - 1e-12).all(), "surface-water envelope broke"

    # and the decreases that must NOT be clamped away
    shrank = int((fh_cc[covered] < np.array(f_high)[covered] - 1e-9).sum())
    assert shrank > 0, (
        "no covered district's 1-in-100/200 band shrinks under the climate "
        "scenario - the future has been clamped to contain the present, "
        "which is exactly what flood_future must not do")
    # comparison is only meaningful where the EA actually models a future
    assert 0 < covered.sum() < len(names), "coverage mask looks wrong"
    # and it must still be a large national increase overall
    grew = fh_cc[covered].sum() / max(np.array(f_high)[covered].sum(), 1e-9)
    assert grew > 1.2, f"national high-band growth only {grew:.2f}x"


STATS_KEYS_NO_TEMPLATE_USES = {
    # Computed by build_site.load_stats() and read by no template. Listed
    # rather than deleted: the per-district uplift layer was removed on
    # purpose (it is Monte Carlo noise at calibrated frequencies), and the
    # capital/catastrophe figures are still worth having available. Pinned
    # so the set cannot grow silently - a NEW unused key almost always
    # means a figure was meant to be shown and the placeholder was lost.
    # __MEAN_STANDALONE__ and __PORT_TVAR__ left here on 2026-08-04: the
    # methodology page now uses them to show the standalone-vs-allocated
    # tail gap. This guard is doing its job when the set SHRINKS.
    "__CAT_COST__", "__CAT_INDEP__", "__CAT_UPLIFT__", "__DIST_UPLIFT__",
    "__MEAN_CAPITAL__",
}


def test_truncated_geology_fetch_can_never_be_written_as_complete(tmp_path,
                                                                  monkeypatch):
    """A short geology layer must never wear the real filename.

    This is the project's worst failure mode, not a hypothetical: missing
    polygons read as "no deposits here" and silently change subsidence
    scores, with nothing in the log. A GitHub run shipped 10,500 of 10,651
    superficial polygons *as complete* and moved sub_score on 1,560
    districts, because a resumed run whose first request was refused never
    learned numberMatched, and the completeness test was written as
    `matched is not None and len != matched` - which passes when the total
    is unknown.

    Unknown must count as incomplete. Checked for both the cold-start and
    the resumed path, since only the resumed one had the hole.
    """
    import json

    import fetch_bgs

    out = tmp_path / "layer.geojson"
    cfg = dict(collection="x", out=str(out), keep=["lex_d"])
    monkeypatch.setattr(fetch_bgs, "PACE", 0)
    monkeypatch.setattr(fetch_bgs, "PAGE", 200)

    def feat(i):
        return {"type": "Feature", "properties": {"lex_d": f"TILL{i}"},
                "geometry": None}

    # --- cold start, server dies after one page of three ---------------
    calls = {"n": 0}

    def one_then_dead(url):
        calls["n"] += 1
        return ({"numberMatched": 600,
                 "features": [feat(i) for i in range(200)]}
                if calls["n"] == 1 else None)

    monkeypatch.setattr(fetch_bgs, "_get", one_then_dead)
    assert fetch_bgs.fetch(cfg) is True, "short fetch must report incomplete"
    assert not out.exists(), "a truncated layer must not wear the real name"
    assert (tmp_path / "layer.geojson.partial").exists()

    # --- resume whose FIRST request is refused, total NOT yet known ----
    # Exactly the shape that shipped a truncated layer: delete the meta
    # sidecar so numberMatched is unknown for this run.
    (tmp_path / "layer.geojson.progress.json").unlink(missing_ok=True)
    (tmp_path / "layer.geojson.partial").unlink()
    monkeypatch.setattr(fetch_bgs, "_get", lambda url: None)
    assert fetch_bgs.fetch(cfg) is True, (
        "unknown total must count as INCOMPLETE - this is the bug that "
        "shipped 10,500 of 10,651 polygons as complete")
    assert not out.exists()
    assert (tmp_path / "layer.geojson.partial").exists()

    # --- and the happy path still completes and cleans up --------------
    def all_pages(url):
        off = int(url.split("offset=")[1])
        return {"numberMatched": 600,
                "features": [feat(i) for i in range(off, min(off + 200, 600))]}

    monkeypatch.setattr(fetch_bgs, "_get", all_pages)
    assert fetch_bgs.fetch(cfg) is False
    assert out.exists()
    assert not (tmp_path / "layer.geojson.partial").exists(), (
        "a completed resume must clear the earlier .partial, or the "
        "workflow's own geology guard trips on a layer that is fine")
    assert not (tmp_path / "layer.geojson.progress.jsonl").exists()
    assert len(json.loads(out.read_text())["features"]) == 600


def test_thread_count_does_not_change_a_single_bit():
    """Parallelism must be an optimisation, never a modelling choice.

    The batch loop runs on threads. Batches are independent - the year-view
    noise is seeded per batch from its OFFSET, not from execution order -
    but the results are combined afterwards, and floating-point addition is
    not associative. Accumulating `year` as batches happen to finish would
    make the portfolio series depend on thread scheduling, i.e. on the
    machine. Results must be bit-identical, not merely close, because a
    last bit here propagates through 20,000 years into rating deciles.
    """
    import pandas as pd
    rng = np.random.default_rng(99)
    n = 120                       # >1 batch at the reduced BATCH below
    df = pd.DataFrame({
        "sub_score": rng.uniform(0.05, 1.0, n),
        "wx_score": rng.uniform(0.05, 1.0, n),
        "fl_score": rng.uniform(0.0, 1.0, n),
        "gw_score": rng.uniform(0.0, 1.0, n),
        "er_score": rng.uniform(0.0, 0.8, n),
        "f_high": np.full(n, 0.05), "f_low": np.full(n, 0.10),
        "sw_high": np.full(n, 0.02), "sw_low": np.full(n, 0.05),
        "gw_frac": rng.uniform(0.0, 0.5, n),
        "sw_sev": rng.uniform(0.6, 2.5, n),
        "er_frac": rng.uniform(0.0, 0.05, n),
        "households": rng.uniform(200, 40000, n),
    })
    keep = (bm.N_SIM, bm.BATCH, bm.N_THREADS)
    bm.N_SIM, bm.BATCH = 400, 25          # 5 batches
    try:
        bm.N_THREADS = 1
        serial, year_s = bm.simulate(df)
        bm.N_THREADS = 4
        threaded, year_t = bm.simulate(df)
    finally:
        bm.N_SIM, bm.BATCH, bm.N_THREADS = keep

    assert set(serial) == set(threaded)
    for k in serial:
        assert np.array_equal(serial[k], threaded[k], equal_nan=True), (
            f"{k} differs between 1 and 4 threads - the batch results are "
            f"being combined in completion order, not batch order")
    for k in year_s:
        assert np.array_equal(np.asarray(year_s[k]), np.asarray(year_t[k]),
                              equal_nan=True), f"year[{k}] is thread-dependent"


def test_superficial_modifier_is_bounded_and_two_sided():
    """combine_subsidence must move relativities, not run away with them."""
    import scores_real as sr
    bed = np.array([1.00, 1.00, 0.08, 0.08, 0.50, 0.90])
    sup = np.array([0.05, 0.05, 0.75, 0.75, 0.50, 0.45])
    cov = np.array([1.00, 0.00, 1.00, 0.00, 1.00, 0.50])
    out = sr.combine_subsidence(bed, sup, cov)

    # zero cover is exactly a no-op: a district with no mapped drift must
    # come out at its bedrock score, not merely close to it
    assert out[1] == bed[1] and out[3] == bed[3]
    # it cuts both ways
    assert out[0] < bed[0], "granular drift over clay must lower"
    assert out[2] > bed[2], "clay drift over benign bedrock must raise"
    # and is bounded by SUP_WEIGHT even at full cover - drift can never
    # override mapped bedrock outright, because thickness is unknown
    assert out[0] >= (1 - sr.SUP_WEIGHT) * bed[0]
    assert abs(out[0] - ((1 - sr.SUP_WEIGHT) * 1.00
                         + sr.SUP_WEIGHT * 0.05)) < 1e-12
    # equal scores are a fixed point regardless of cover
    assert abs(out[4] - 0.50) < 1e-12
    # stays in range for any input
    rng = np.random.default_rng(3)
    r = sr.combine_subsidence(rng.uniform(0, 1, 500), rng.uniform(0, 1, 500),
                              rng.uniform(0, 1, 500))
    assert r.min() >= 0.0 and r.max() <= 1.0


def test_superficial_vocabulary_is_fully_enumerated():
    """Every 625k deposit is classified or explicitly excluded.

    SUP_SUSCEP is a closed table rather than keyword-matching with a
    default, so an unrecognised deposit means the layer changed and must
    be a loud failure - a silent default would quietly rescore districts.
    """
    import json
    import scores_real as sr
    both = set(sr.SUP_SUSCEP) | sr.SUP_EXCLUDED
    assert not (set(sr.SUP_SUSCEP) & sr.SUP_EXCLUDED), "peat cannot be both"
    assert "PEAT" in sr.SUP_EXCLUDED, "peat is excluded on purpose"
    assert all(0.0 <= v <= 1.0 for v in sr.SUP_SUSCEP.values())

    path = os.path.join(os.path.dirname(__file__), "..", "data",
                        "bgs_625k_superficial.geojson")
    if not os.path.exists(path):
        pytest.skip("superficial layer not fetched")
    with open(path, encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    seen = {(f["properties"].get("lex_d") or "").strip().upper()
            for f in feats}
    seen.discard("")
    unknown = sorted(seen - both)
    assert not unknown, (
        f"unclassified superficial deposits {unknown} - classify them in "
        f"SUP_SUSCEP or SUP_EXCLUDED rather than letting them default")


def test_published_geojson_satisfies_the_models_own_identities():
    """Catch a stale or half-written districts_risk.geojson in seconds.

    A full rebuild is ~110 minutes, and everything published downstream -
    the CSV, the map popups, the injected site figures - is derived from
    this one file. These are the identities a rebuild would have to
    reproduce, so checking them directly is the cheap half of that
    guarantee.

    Tolerances come from the write-time rounding, not from taste:
    build_model writes el_*/premium/var/tvar at 1dp and most other columns
    at 4dp.
    """
    import json
    root = os.path.join(os.path.dirname(__file__), "..")
    path = os.path.join(root, "data", "districts_risk.geojson")
    if not os.path.exists(path):
        pytest.skip("districts_risk.geojson not built")
    with open(path, encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    assert len(feats) > 2000, f"only {len(feats)} districts"

    def col(name):
        return np.array([f.get(name, np.nan) for f in feats], dtype=float)

    premium, capital, el_total = col("premium"), col("capital"), col("el_total")

    # premium arithmetic (1dp on each term)
    assert np.abs(premium - (el_total + capital)).max() <= 0.15
    assert np.abs(el_total - (col("el_sub") + col("el_wx") + col("el_fl")
                              + col("el_gw"))).max() <= 0.25
    assert np.abs(col("el_total5") - (el_total + col("el_er"))).max() <= 0.25
    assert (capital >= -1e-9).all()

    # rating groups: 10 balanced, monotone deciles
    grp = col("group")
    assert ((grp >= 1) & (grp <= 10)).all()
    sizes = np.bincount(grp.astype(int), minlength=11)[1:]
    assert sizes.max() - sizes.min() <= 2, f"unbalanced deciles {sizes}"
    for g in range(1, 10):
        assert premium[grp == g].max() <= premium[grp == g + 1].min() + 1e-6

    # the Gumbel tail-dependence identity, on published values
    for pair in ("wf", "ws", "wg", "we"):
        th, td = col(f"theta_{pair}"), col(f"tail_dep_{pair}")
        assert np.abs(td - (2 - 2 ** (1 / th))).max() <= 2e-4

    # band nesting survives the write
    assert (col("f_low") >= col("f_high") - 1e-9).all()
    assert (col("sw_low") >= col("sw_high") - 1e-9).all()

    # tail measures order correctly
    assert (col("tvar99_vine") >= col("var995_vine") - 0.15).all()
    assert (col("tvar99_vine5") >= col("tvar99_vine") - 0.15).all()

    # climate repricing. SECTOR-MODEL BRANCH: the climate fetches are
    # deliberately deferred (see the branch's first commit), so the
    # coverage identity only applies when the climate inputs exist -
    # a guard on an input that was intentionally not provided is not a
    # guard, it is a veto on the phase plan. Everything else about the
    # cc columns must still hold in the all-absent state.
    cov = col("cc_covered") > 0
    has_climate_inputs = os.path.exists(
        os.path.join(os.path.dirname(__file__), "..", "data",
                     "flood_fractions_cc.csv"))
    if has_climate_inputs:
        assert cov.any() and not cov.all()
    else:
        assert not cov.any(), (
            "cc_covered set without climate inputs on disk - where did "
            "the coverage come from?")
    pc = col("premium_cc")
    assert np.abs(pc - (col("el_total_cc") + col("capital_cc"))).max() <= 0.15
    assert (col("cc_uplift_pct")[~cov] == 0).all()

    # cc_uplift_pct is computed from UNROUNDED premiums and written at 4dp,
    # so recomputing it from the 1dp published pair carries an error that
    # grows as the premium shrinks - at premium ~£25 a ±0.05 rounding is
    # already ±0.2%. A flat tolerance flags ~70 districts spuriously; the
    # honest bound is interval arithmetic over the two roundings.
    p, pcc = premium[cov], pc[cov]
    recomputed = 100.0 * (pcc / np.maximum(p, 1e-9) - 1)
    hi = 100.0 * ((pcc + 0.05) / np.maximum(p - 0.05, 1e-9) - 1)
    lo = 100.0 * ((pcc - 0.05) / np.maximum(p + 0.05, 1e-9) - 1)
    bound = np.maximum(np.abs(hi - recomputed), np.abs(lo - recomputed))
    resid = np.abs(col("cc_uplift_pct")[cov] - recomputed)
    assert (resid <= bound + 1e-9).all(), (
        f"{int((resid > bound).sum())} districts break the uplift identity "
        f"by more than write-time rounding can explain")


def test_site_placeholders_all_resolve():
    """A placeholder with no stats key ships as literal `__FOO__`.

    render_template() does a plain str.replace per stats key, so an
    unmatched placeholder is not an error - the raw token goes straight to
    the published page. Checked statically (regex over build_site.py and
    the templates) so the test needs neither the 5 MB GeoJSON nor a build.
    """
    import re
    root = os.path.join(os.path.dirname(__file__), "..")
    token = re.compile(r"__[A-Z][A-Z_0-9]*__")

    with open(os.path.join(root, "scripts", "build_site.py"),
              encoding="utf-8") as fh:
        keys = set(re.findall(r'"(__[A-Z][A-Z_0-9]*__)"', fh.read()))
    assert len(keys) > 30, f"only {len(keys)} stats keys found - regex stale"

    used = set()
    for tpl in ("index.template.html", "methodology.template.html"):
        with open(os.path.join(root, "site", tpl), encoding="utf-8") as fh:
            found = set(token.findall(fh.read()))
        assert found, f"{tpl} has no placeholders - extraction is stale"
        unknown = sorted(found - keys)
        assert not unknown, (
            f"{tpl} uses {unknown}, which build_site.py never defines - "
            f"these ship to the live page as literal text")
        used |= found

    unused = keys - used - {"__NAV__", "__HEAD__"}
    assert unused == STATS_KEYS_NO_TEMPLATE_USES, (
        f"the set of stats keys no template uses has changed: "
        f"unexpected {sorted(unused - STATS_KEYS_NO_TEMPLATE_USES)}, "
        f"no longer unused {sorted(STATS_KEYS_NO_TEMPLATE_USES - unused)}")

    # and nothing survived into the built pages
    docs = os.path.join(root, "docs")
    for page in sorted(os.listdir(docs)):
        if not page.endswith(".html"):
            continue
        with open(os.path.join(docs, page), encoding="utf-8") as fh:
            left = sorted(set(token.findall(fh.read())))
        assert not left, f"docs/{page} still contains {left}"


def test_every_asset_the_published_site_references_exists():
    """No broken links or missing assets in docs/, checked offline.

    A 404 on Pages is invisible until someone clicks. The three reference
    styles all have to be covered, because this site genuinely uses all
    three and checking only the obvious one misses two of them:

      href=/src=   stylesheets, favicons, page-to-page nav
      content=     the og:image social card, in a <meta> tag
      fetch('..')  assets/districts.json, loaded by the postcode lookup

    A scan for href/src alone passes while the social card and the
    postcode search are both broken.
    """
    import re
    docs = os.path.join(os.path.dirname(__file__), "..", "docs")
    pages = [f for f in sorted(os.listdir(docs)) if f.endswith(".html")]
    assert pages, "docs/ has no built pages"

    patterns = [
        re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I),
        re.compile(r'content\s*=\s*["\']([^"\']+)["\']', re.I),
        re.compile(r'fetch\(\s*["\']([^"\']+)["\']'),
    ]
    external = ("http://", "https://", "//", "#", "data:", "mailto:",
                "javascript:")
    site_root = "https://smcode-source.github.io/uk-home-insurance-risk-map/"

    missing, checked = [], set()
    for page in pages:
        with open(os.path.join(docs, page), encoding="utf-8") as fh:
            html = fh.read()
        for pat in patterns:
            for ref in set(pat.findall(html)):
                # the og:image is absolute, but it points back at our own
                # site, so it still has to exist in docs/
                if ref.startswith(site_root):
                    ref = ref[len(site_root):]
                elif ref.startswith(external):
                    continue
                target = ref.split("#")[0].split("?")[0]
                # <meta content="..."> is mostly prose and numbers; only
                # treat it as a reference if it looks like a local file
                if not target or "." not in os.path.basename(target):
                    continue
                if not re.fullmatch(r"[\w./-]+", target):
                    continue
                checked.add(target)
                if not os.path.exists(os.path.join(docs, target.lstrip("/"))):
                    missing.append((page, ref))

    assert not missing, f"docs/ references files that do not exist: {missing}"
    # again, pin the scale so a template rewrite cannot silently empty this
    assert len(checked) >= 8, (
        f"only {len(checked)} local references found across {len(pages)} "
        f"pages - the extraction has stopped matching")
    for required in ("assets/site.css", "assets/districts.json",
                     "assets/social.png", "assets/map_data.geojson"):
        assert required in checked, (
            f"{required} is no longer referenced by any page - if that is "
            f"deliberate, stop building it too")


def test_the_map_and_site_only_read_columns_the_model_writes():
    """The other half of the GeoJSON contract, and the silent half.

    The test below guarantees simulate() produces what OUTPUT_COLUMNS
    promises. Nothing guaranteed the reverse: that the front end only reads
    what OUTPUT_COLUMNS actually ships. Both consumers fail quietly if it
    does not -

      * map/template.html reads `p.<col>` off the GeoJSON properties, so a
        dropped column renders as `undefined` in the district popup;
      * build_site.py builds the published CSV with `p.get(c, "")`, so a
        dropped column becomes a silently EMPTY column in
        docs/assets/uk_district_risk.csv.

    Neither raises. Both ship.
    """
    import ast
    import re
    root = os.path.join(os.path.dirname(__file__), "..")
    published = set(bm.OUTPUT_COLUMNS)

    with open(os.path.join(root, "map", "template.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()
    # \b matters: without it `ramp.length` and `tooltip.district-tip` match
    # as `p.length` / `p.district` and the test drowns in false positives.
    read_by_map = set(re.findall(r"\bp\.([A-Za-z_][A-Za-z_0-9]*)", tpl))
    read_by_map |= set(re.findall(
        r"\.properties\.([A-Za-z_][A-Za-z_0-9]*)", tpl))
    stray = sorted(read_by_map - published)
    assert not stray, (
        f"map/template.html reads {stray}, which build_model.py does not "
        f"write - these render as `undefined` in the popup")

    # A guard that stops finding anything is worse than no guard, so pin the
    # scale: if a template rewrite changes the access pattern this fails
    # loudly instead of passing vacuously.
    assert len(read_by_map) > 40, (
        f"only {len(read_by_map)} property reads found in map/template.html "
        f"- the extraction pattern has stopped matching, not the template "
        f"stopped reading")

    # build_site.py's published-CSV column list
    with open(os.path.join(root, "scripts", "build_site.py"),
              encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    site_cols = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.targets
                and getattr(node.targets[0], "id", None) == "cols"
                and isinstance(node.value, ast.List)):
            vals = [e.value for e in node.value.elts
                    if isinstance(e, ast.Constant)]
            if len(vals) > 20:
                site_cols = vals
    assert site_cols, "could not find build_site.py's CSV `cols` list"
    stray = sorted(set(site_cols) - published)
    assert not stray, (
        f"build_site.py publishes {stray}, which build_model.py does not "
        f"write - p.get(c, '') makes these silently empty CSV columns")


def test_simulate_returns_the_columns_the_map_and_site_read():
    """The GeoJSON contract: build_map.py and build_site.py index these by
    name, so losing one breaks the published pages rather than the tests."""
    import pandas as pd
    import build_model as m
    n_sim, batch = m.N_SIM, m.BATCH
    m.N_SIM, m.BATCH = 120, 8
    try:
        df = pd.DataFrame({
            "sub_score": [0.4], "wx_score": [0.4], "fl_score": [0.4],
            "gw_score": [0.2], "er_score": [0.3], "f_high": [0.05],
            "f_low": [0.1], "sw_high": [0.02], "sw_low": [0.05],
            "gw_frac": [0.05], "sw_sev": [1.0], "er_frac": [0.01],
            "households": [500.0],
        })
        sim, year = m.simulate(df)
    finally:
        m.N_SIM, m.BATCH = n_sim, batch
    # Assert the DECLARED contract, not a hand-picked subset. The list this
    # replaced named 14 of the 26 columns simulate() promises, so losing
    # var995_vine, tvar99_gauss, uplift_pct or any of the theta_*/tail_dep_*
    # pairs passed the tests and failed at the GeoJSON write instead - after
    # both simulations, i.e. ~110 minutes in. Driving it from
    # SIMULATED_COLUMNS means the two cannot drift apart again.
    missing = sorted(m.SIMULATED_COLUMNS - set(sim))
    assert not missing, f"simulate() no longer returns {missing}"
    # and nothing may claim to be simulated that main() actually computes
    assert not (m.SIMULATED_COLUMNS & m.MAIN_COLUMNS)
    # every published column must come from scoring, simulate() or main()
    assert m.DERIVED_COLUMNS == m.SIMULATED_COLUMNS | m.MAIN_COLUMNS
    # the year view stays on the four insured perils
    assert "g_v" in year and "expo_total" in year


def test_border_sliver_is_not_read_as_a_shallow_district(tmp_path, monkeypatch):
    """The border trap.

    A handful of Scottish and Welsh districts (Annan, Jedburgh, Wrexham,
    Caldicot...) clip just far enough into England to pick up a sliver of
    EA depth mapping, while their sw_low covers the whole district
    including the part England never mapped. The ratio is dragged towards
    zero and they come out looking uniformly shallow. Coverage well below
    the national norm (~0.44) must be treated as missing data.
    """
    import scores_real as sr
    rows = ["name,d02_high,d02_low,d03_high,d03_low,d06_high,d06_low,"
            "d09_high,d09_low,d12_high,d12_low",
            # properly covered English district
            "ENG,0.0,0.050,0.0,0.030,0.0,0.015,0.0,0.008,0.0,0.003",
            # border district: envelope 0.13, but only 0.00002 mapped
            "BORDER,0.0,0.00002,0.0,0.00001,0.0,0.0,0.0,0.0,0.0,0.0"]
    (tmp_path / "sw_depth.csv").write_text("\n".join(rows))
    # BORDER is mostly in England but not enough of it for the English-only
    # depth product to describe the whole district
    (tmp_path / "country.csv").write_text(
        "name,country,share\nENG,England,1.0\nBORDER,England,0.64\n")
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    mult, depth = sr.sw_depth_severity(
        np.array(["ENG", "BORDER"]),
        np.array([0.05, 0.0652]),
        np.array([0.10, 0.1304]),
        np.array([1000.0, 1000.0]))

    assert mult[1] == 1.0, "border sliver must fall back, not read as shallow"
    assert np.isnan(depth[1])
    assert not np.isnan(depth[0])       # the covered one still works


def test_england_mask_reads_the_boundary_not_the_data(tmp_path, monkeypatch):
    """Coverage must come from the country boundary, and straddlers excluded.

    This is the rule three separate datasets kept getting wrong: EA depth,
    NCERM erosion and the climate-change flood extents all stop at the
    border, and every attempt to infer that from the numbers produced a
    plausible-looking mistake.
    """
    import scores_real as sr
    (tmp_path / "country.csv").write_text(
        "name,country,share\n"
        "LEEDS,England,1.0\n"
        "CARDIFF,Wales,1.0\n"
        "DUNDEE,Scotland,1.0\n"
        "BERWICK,England,0.64\n"        # genuine straddler
        "CHESTER,England,0.97\n")       # nominally split, effectively English
    monkeypatch.setattr(sr, "DATA", str(tmp_path))
    m = sr.england_mask(np.array(
        ["LEEDS", "CARDIFF", "DUNDEE", "BERWICK", "CHESTER", "UNKNOWN"]))
    assert list(m) == [True, False, False, False, True, False]


def test_depth_severity_missing_file_is_a_flat_fallback(tmp_path, monkeypatch):
    """Wales and Scotland have no depth product; the model must still run."""
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))
    mult, depth = sr.sw_depth_severity(
        np.array(["A", "B"]), np.array([0.05, 0.1]),
        np.array([0.1, 0.2]), np.array([1.0, 1.0]))
    assert np.all(mult == 1.0)
    assert np.all(np.isnan(depth))


def test_uncovered_district_with_surface_water_is_not_read_as_shallow(
        tmp_path, monkeypatch):
    """The Wales/Scotland trap.

    fetch_sw_depth.py writes a row for EVERY district, zero-filled outside
    England. A Welsh district therefore has real surface water (sw_low > 0
    from NRW) but all-zero depth fractions. Read naively that says "none of
    it is over 0.2 m", i.e. the shallowest possible severity — which would
    quietly under-price all of Wales and Scotland. It must take the neutral
    1.0 fallback instead.
    """
    import scores_real as sr
    hdr = ("name,d02_high,d02_low,d03_high,d03_low,d06_high,d06_low,"
           "d09_high,d09_low,d12_high,d12_low")
    rows = [hdr,
            # England: real depth mapped
            "ENG,0.0,0.060,0.0,0.040,0.0,0.020,0.0,0.010,0.0,0.004",
            # Wales: zero-filled row, but the district really does flood
            "WAL,0.0,0.000,0.0,0.000,0.0,0.000,0.0,0.000,0.0,0.000"]
    (tmp_path / "sw_depth.csv").write_text("\n".join(rows))
    (tmp_path / "country.csv").write_text(
        "name,country,share\nENG,England,1.0\nWAL,Wales,1.0\n")
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    mult, depth = sr.sw_depth_severity(
        np.array(["ENG", "WAL"]),
        np.array([0.05, 0.05]),
        np.array([0.10, 0.10]),          # both have surface water
        np.array([1000.0, 1000.0]))

    assert mult[1] == 1.0, "uncovered district must fall back, not go shallow"
    assert np.isnan(depth[1])
    # and the covered one is normalised on its own, so it is exactly 1.0 too
    assert abs(mult[0] - 1.0) < 1e-9
