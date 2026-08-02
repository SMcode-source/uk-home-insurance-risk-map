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
    for key in ("el_sub", "el_wx", "el_fl", "el_gw", "el_er", "el_total",
                "el_total5", "tvar99_vine", "tvar99_vine5", "tvar99_indep5",
                "tvar99_euler", "el_year", "theta_we", "tail_dep_we"):
        assert key in sim, f"simulate() no longer returns {key}"
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
