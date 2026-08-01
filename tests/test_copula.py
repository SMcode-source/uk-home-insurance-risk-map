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
    }


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
    t_ws, t_wf, t_wg = (np.array([[1.8]]), np.array([[2.5]]),
                        np.array([[1.6]]))
    for u in bm.sample_vine(t_ws, t_wf, t_wg, base):
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
    t_ws, t_wf, t_wg = (np.array([[1.9]]), np.array([[2.6]]),
                        np.array([[1.7]]))
    u_w, u_f, u_g, u_s = bm.sample_vine(t_ws, t_wf, t_wg, base)
    cut = slice(0, 6000)
    tau = lambda a, b: stats.kendalltau(np.asarray(a).ravel()[cut],
                                        np.asarray(b).ravel()[cut]).statistic
    assert abs(tau(u_w, u_f) - (1 - 1 / 2.6)) < 0.03
    assert abs(tau(u_w, u_s) - (1 - 1 / 1.9)) < 0.03
    assert abs(tau(u_w, u_g) - (1 - 1 / 1.7)) < 0.03
    # tree-2 pairs stay positively but weakly dependent
    assert 0.0 < tau(u_f, u_g) < tau(u_w, u_f)


def test_gumbel_has_upper_tail_dependence_and_gaussian_does_not(base):
    """The whole reason for choosing Gumbel: joint extremes survive."""
    theta = 2.5
    t = np.array([[theta]])
    u1, u2 = bm.sample_gumbel(t, base)
    q = 0.99
    joint_g = np.mean((u1.ravel() > q) & (u2.ravel() > q)) / (1 - q)

    ug_w, ug_f, _, _ = bm.sample_gaussian4(
        np.array([[1.5]]), t, np.array([[1.5]]), base)
    joint_n = np.mean((np.asarray(ug_w).ravel() > q)
                      & (np.asarray(ug_f).ravel() > q)) / (1 - q)

    lambda_u = 2 - 2 ** (1 / theta)
    assert joint_g > 0.5 * lambda_u          # near the theoretical value
    assert joint_g > joint_n + 0.05          # and clearly above Gaussian


def test_gaussian4_margins_uniform_and_taus_match(base):
    t_ws, t_wf, t_wg = (np.array([[1.8]]), np.array([[2.4]]),
                        np.array([[1.6]]))
    u_w, u_f, u_g, u_s = bm.sample_gaussian4(t_ws, t_wf, t_wg, base)
    for u in (u_w, u_f, u_g, u_s):
        assert stats.kstest(np.asarray(u).ravel(), "uniform").pvalue > 0.01
    cut = slice(0, 6000)
    tau = lambda a, b: stats.kendalltau(np.asarray(a).ravel()[cut],
                                        np.asarray(b).ravel()[cut]).statistic
    # tau-matched to the vine's tree-1 pairs
    assert abs(tau(u_w, u_f) - (1 - 1 / 2.4)) < 0.04
    assert abs(tau(u_w, u_s) - (1 - 1 / 1.8)) < 0.04


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


def test_severity_medians_hit_published_means():
    """Severity params are set so each lognormal MEAN equals the ABI figure."""
    (_, _, _, _, sev_sub, sev_wx, _, sev_gw) = bm.marginal_params(
        np.array([0.5]), np.array([0.5]), np.array([0.1]), np.array([0.2]),
        np.array([0.1]), np.array([0.2]), np.array([0.1]))
    mean = lambda s: float(np.exp(s["mu"] + s["sigma"] ** 2 / 2))
    assert abs(mean(sev_sub) / bm.ABI["sev_subsidence"] - 1) < 1e-6
    assert abs(mean(sev_wx) / bm.ABI["sev_weather"] - 1) < 1e-6
    assert abs(mean(sev_gw) / bm.ABI["sev_groundwater"] - 1) < 1e-6


def test_theta_functions_stay_in_valid_gumbel_range():
    grid = np.linspace(0, 1, 21)
    a, b = np.meshgrid(grid, grid)
    for fn, cap in ((bm.theta_ws, 2.5), (bm.theta_wf, 3.0),
                    (bm.theta_wg, 2.4)):
        th = fn(a, b)
        assert th.min() >= 1.0 and th.max() <= cap + 1e-9
