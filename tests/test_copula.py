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
    f = dict(sub=0.5, sub_rel=1.0, wx=0.5, f_high=0.1, f_low=0.2,
             sw_high=0.1,
             sw_low=0.2, gw_frac=0.1, sw_sev=1.0, er=0.0, th=0.009,
             eow=1.0, fire=0.002, ad=0.009,
             ct_th=1.0, ct_eow=1.0, ct_fire=1.0, ct_ad=1.0)
    f.update(over)
    return {k: np.array([v], dtype=float) for k, v in f.items()}


def test_severity_medians_hit_published_means():
    """Severity params are set so each lognormal MEAN equals the ABI figure."""
    m = bm.marginal_params(fields())
    mean = lambda s: float(np.mean(np.exp(s["mu"] + s["sigma"] ** 2 / 2)))
    assert abs(mean(m["sev_sub"]) / bm.ABI["sev_subsidence"] - 1) < 1e-6
    assert abs(mean(m["sev_wx"]) / bm.ABI["sev_weather"] - 1) < 1e-6
    assert abs(mean(m["sev_gw"]) / bm.ABI["sev_groundwater"] - 1) < 1e-6
    assert abs(mean(m["sev_er"]) / bm.ABI["sev_erosion"] - 1) < 1e-6


def test_ct_band_relativity_scales_severity_not_frequency():
    """The council-tax band value relativity multiplies the attritional
    severity MEANS linearly and touches nothing else: frequencies are
    untouched, and at the neutral 1.0 every mean sits exactly on its
    ABI anchor (which is what keeps the other severity tests honest)."""
    base = bm.marginal_params(fields())
    up = bm.marginal_params(fields(ct_th=1.25, ct_eow=1.25,
                                   ct_fire=1.25, ct_ad=1.25))
    mean = lambda s: float(np.mean(np.exp(s["mu"] + s["sigma"] ** 2 / 2)))
    for peril, anchor in (("th", "sev_theft"), ("eow", "sev_eow"),
                          ("fire", "sev_fire"), ("ad", "sev_ad")):
        assert abs(mean(base[f"sev_{peril}"]) / bm.ABI[anchor] - 1) < 1e-6
        assert abs(mean(up[f"sev_{peril}"])
                   / (1.25 * bm.ABI[anchor]) - 1) < 1e-6
        assert float(up[f"p_{peril}"][0]) == float(base[f"p_{peril}"][0])
    # weather severities are NOT scaled by the band mix
    assert abs(mean(up["sev_wx"]) / mean(base["sev_wx"]) - 1) < 1e-12


def test_theta_functions_stay_in_valid_gumbel_range():
    grid = np.linspace(0, 1, 21)
    a, b = np.meshgrid(grid, grid)
    for fn, cap in ((bm.theta_ws, 2.5), (bm.theta_wf, 3.0),
                    (bm.theta_wg, 2.4), (bm.theta_we, 2.6)):
        th = fn(a, b)
        assert th.min() >= 1.0 and th.max() <= cap + 1e-9


# ---------------------------------------------------------------- erosion

def test_theft_severity_mean_hits_the_abi_average():
    """sev_th's lognormal MEAN equals the published ABI average claim."""
    m = bm.marginal_params(fields())
    mean = float(np.mean(np.exp(m["sev_th"]["mu"] + m["sev_th"]["sigma"] ** 2 / 2)))
    assert abs(mean / bm.ABI["sev_theft"] - 1) < 1e-6


def test_theft_frequency_is_the_burglary_rate_scaled():
    """p_th is the district burglary rate times the ABI level scale and
    nothing else - the geography comes straight from the police data."""
    old = dict(bm.FREQ_SCALE)
    try:
        bm.FREQ_SCALE = dict(old, th=0.85)
        m = bm.marginal_params(fields(th=0.02))
        assert abs(float(m["p_th"][0]) - 0.02 * 0.85) < 1e-12
        # and the safety clip cannot produce a probability above one half
        m = bm.marginal_params(fields(th=3.0))
        assert float(m["p_th"][0]) == 0.5
    finally:
        bm.FREQ_SCALE = old


def test_eow_severity_mean_hits_the_abi_average():
    """sev_eow's lognormal MEAN equals the anchor-triangle average claim."""
    m = bm.marginal_params(fields())
    mean = float(np.mean(np.exp(m["sev_eow"]["mu"] + m["sev_eow"]["sigma"] ** 2 / 2)))
    assert abs(mean / bm.ABI["sev_eow"] - 1) < 1e-6


def test_eow_frequency_is_the_frost_rate_scaled():
    """p_eow is the precomputed eow_rate (anchor level x frost relativity,
    built in main() where the exposure weights live) times the ABI level
    scale and nothing else - marginal_params must not renormalise it,
    because it runs on batches and a per-chunk mean would depend on chunk
    membership."""
    old = dict(bm.FREQ_SCALE)
    try:
        bm.FREQ_SCALE = dict(old, eow=0.02)
        m = bm.marginal_params(fields(eow=1.15))
        assert abs(float(m["p_eow"][0]) - 1.15 * 0.02) < 1e-12
        # and the safety clip cannot produce a probability above one half
        m = bm.marginal_params(fields(eow=80.0))
        assert float(m["p_eow"][0]) == 0.5
    finally:
        bm.FREQ_SCALE = old


def test_sub_frequency_carries_the_drought_relativity():
    """p_sub is the geology base times sub_rel (the Gate 2 SMD curve,
    normalised in main() where the exposure weights live) and nothing
    else - marginal_params must not renormalise it, for the same
    batch-membership reason as eow_rate. The column is REQUIRED: a
    frame without it must fail loudly rather than silently price
    geology-only, because that is exactly the failure the experiment
    branch's provably-inert default would have hidden after a publish.
    """
    base = bm.marginal_params(fields())
    up = bm.marginal_params(fields(sub_rel=1.3))
    assert abs(float(up["p_sub"][0]) / float(base["p_sub"][0])
               - 1.3) < 1e-12
    # frequency only: the severity params must be bit-identical
    assert np.array_equal(base["sev_sub"]["mu"], up["sev_sub"]["mu"])
    assert np.array_equal(base["sev_sub"]["sigma"], up["sev_sub"]["sigma"])
    # and the dependence input is untouched by construction: theta_ws
    # reads sub_score, which fields() carries separately as `sub`
    f = fields()
    del f["sub_rel"]
    with pytest.raises(KeyError):
        bm.marginal_params(f)


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
        bm.FREQ_SCALE = {"sub": 3.0, "wx": 3.0, "fl": 3.0, "gw": 3.0,
                         "th": 3.0, "eow": 3.0, "fire": 3.0, "ad": 3.0}
        scaled = float(bm.marginal_params(fields(er=0.1))["p_er"][0])
        bm.FREQ_SCALE = {"sub": 1.0, "wx": 1.0, "fl": 1.0, "gw": 1.0,
                         "th": 1.0, "eow": 1.0, "fire": 1.0, "ad": 1.0}
        plain = float(bm.marginal_params(fields(er=0.1))["p_er"][0])
    finally:
        bm.FREQ_SCALE = old
    assert scaled == plain


def _erosion_fixture(tmp_path):
    """Minimal data dir for erosion_from_ncerm: two English districts with
    NCERM rows and one Scottish district with a Dynamic Coast row."""
    (tmp_path / "erosion.csv").write_text(
        "name,er_smp55,er_smp105,er_nfi55,er_nfi105,er_smp105_lo,"
        "er_smp105_hi,er_nfi105_lo,er_nfi105_hi,er_gi,er_smp105_m2,"
        "er_coastal\n"
        "HOLD,0.0,0.0,0.01,0.04,0.0,0.0,0.02,0.05,0.0,0.0,1\n"
        "GONE,0.02,0.06,0.03,0.09,0.03,0.07,0.05,0.10,0.0,600.0,1\n")
    (tmp_path / "erosion_scotland.csv").write_text(
        "name,er_dc50_hi,er_dc100_hi,er_dc50_lo,er_dc100_lo,"
        "er_dc100_hi_m2\n"
        "SCOT,0.03,0.08,0.02,0.04,800.0\n")
    return np.array(["HOLD", "GONE", "SCOT", "INLAND"])


def test_er_head_takes_ncerm_in_england_and_dynamic_coast_in_scotland(
        tmp_path, monkeypatch):
    """The headline erosion column is SMP-2105 where NCERM reaches and
    Dynamic Coast's RCP8.5-2100 where it does not, and er_basis says which
    per district - because the two are different measurements and no
    single number can carry that."""
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    names = _erosion_fixture(tmp_path)
    score, out = sr.erosion_from_ncerm(names)

    assert list(out["er_basis"]) == ["ncerm", "ncerm", "dynamiccoast", "none"]
    # England: er_head is SMP-2105, NOT the bigger NFI figure beside it
    assert list(out["er_head"][:2]) == [0.0, 0.06]
    # Scotland: er_head is the Dynamic Coast 2100 high case
    assert out["er_head"][2] == 0.08
    # and Scotland has NO NCERM columns - absent, which is why er_basis
    # exists; a reader summing er_nfi105 nationally must not read this as
    # "Scotland has no unmanaged erosion"
    assert out["er_nfi105"][2] == 0.0
    assert out["er_dc100_hi"][1] == 0.0        # and no DC leakage into England
    # inland: nothing anywhere
    assert out["er_head"][3] == 0.0 and score[3] == 0.0
    # the score is monotone in er_head, so Scotland outranks the English
    # district whose defences hold it at zero
    assert score[2] > score[1] > score[0] == 0.0


def test_erosion_scotland_wrong_grain_is_fatal_not_silent(tmp_path,
                                                          monkeypatch):
    """A district-keyed erosion_scotland.csv on a sector-keyed frame joins
    nothing, and .get(name, 0.0) would quietly restore Scotland's old zero
    - a VOID run that looks like 'Scotland has no eroding coast'. It must
    raise. Same trap as premises.csv and housebreaking.csv before it."""
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    _erosion_fixture(tmp_path)
    sectors = np.array(["HOLD 1", "GONE 2", "SCOT 3"])
    with pytest.raises(SystemExit, match="matched NONE"):
        sr.erosion_from_ncerm(sectors)


def test_erosion_without_the_scottish_file_degrades_to_england_only(
        tmp_path, monkeypatch):
    """No erosion_scotland.csv is the pre-2026-09-03 state and must still
    run: England unchanged, Scotland zero, and nothing claiming otherwise."""
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    names = _erosion_fixture(tmp_path)
    (tmp_path / "erosion_scotland.csv").unlink()
    _, out = sr.erosion_from_ncerm(names)

    assert list(out["er_basis"]) == ["ncerm", "ncerm", "none", "none"]
    assert out["er_head"][1] == 0.06 and out["er_head"][2] == 0.0


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


def _theft_fixture(tmp_path, premises_rows):
    """Minimal data dir for theft_from_police: two E&W areas and one
    Scottish one, with whatever premises.csv the caller wants to test."""
    (tmp_path / "burglary.csv").write_text(
        "name,burglaries,months\nCORE,600,12\nHOME,60,12\nSCOT,30,12\n")
    (tmp_path / "country.csv").write_text(
        "name,country,share\nCORE,England,1.0\nHOME,England,1.0\n"
        "SCOT,Scotland,1.0\n")
    (tmp_path / "premises.csv").write_text(
        "name,premises\n" + premises_rows)
    (tmp_path / "housebreaking.csv").write_text(
        "name,hb_1yr,hb_3yr\nSCOT,3.0,3.3\n")
    return np.array(["CORE", "HOME", "SCOT"]), np.array([100.0, 5000.0, 900.0])


def test_premises_denominator_lowers_the_commercial_core(tmp_path,
                                                         monkeypatch):
    """The 2a correction: a district that is mostly shops must be charged
    a lower burglary rate than its households-only rate implies, because
    most of those burglary points were never homes."""
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    names, hh = _theft_fixture(tmp_path, "CORE,1900.0\nHOME,50.0\n")
    with_prem = sr.theft_from_police(names, hh)
    # same book, no premises data at all -> the OLD households-only rate
    (tmp_path / "premises.csv").write_text("name,premises\nCORE,0.0\nHOME,0.0\n")
    without = sr.theft_from_police(names, hh)

    assert with_prem[0] < without[0]          # the commercial core falls
    # 100 homes + 1900 premises: only 5% of its burglaries were homes
    assert abs(with_prem[0] / without[0] - 100.0 / 2000.0) < 1e-9
    # the residential district barely moves, and never upward
    assert with_prem[1] <= without[1]
    assert with_prem[1] / without[1] > 0.98


def test_premises_join_failure_is_fatal_not_silent(tmp_path, monkeypatch):
    """A premises.csv keyed on the wrong geography joins nothing, and the
    .get(name, 0.0) fallback would quietly restore the households-only
    denominator - a VOID run that looks like 'no impact'. It must raise.

    This is the households.csv trap: patching a fetcher without
    regenerating its output produced a run that changed nothing and
    reported success. Guard, do not warn."""
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    # sector-style keys ("CORE 1") against district-style names ("CORE")
    names, hh = _theft_fixture(tmp_path, "CORE 1,1900.0\nHOME 2,50.0\n")
    with pytest.raises(SystemExit, match="premises.csv covers only"):
        sr.theft_from_police(names, hh)

    # Scotland is overridden, so it must not count toward coverage: an
    # E&W-complete file with no Scottish row is legitimate and must pass.
    (tmp_path / "premises.csv").write_text(
        "name,premises\nCORE,1900.0\nHOME,50.0\n")
    sr.theft_from_police(names, hh)


def test_scotland_reads_council_housebreaking_and_a_missing_file_is_fatal(
        tmp_path, monkeypatch):
    """Scotland's theft rate comes from housebreaking.csv, per area.

    Until 2026-09-01 every Scottish district shared one national rate,
    and the fallback that produced it was arithmetic on a constant -
    nothing to go stale, nothing to join wrong. Council geography made
    it a FILE, which brings both file traps with it: absent (the run
    should stop, not fall back to a flat rate nobody chose) and keyed on
    the wrong grain (a district-keyed file on the sector branch joins
    nothing, and `.get(n, 0.0)` would hand every Scottish sector a rate
    of exactly zero - a void run that looks like cheap Scotland).
    """
    import scores_real as sr
    monkeypatch.setattr(sr, "DATA", str(tmp_path))

    names, hh = _theft_fixture(tmp_path, "CORE,1900.0\nHOME,50.0\n")
    # two Scottish areas in different councils, so the rate cannot be flat
    (tmp_path / "burglary.csv").write_text(
        "name,burglaries,months\nCORE,600,12\nHOME,60,12\n"
        "SCOT,30,12\nSCOT2,30,12\n")
    (tmp_path / "country.csv").write_text(
        "name,country,share\nCORE,England,1.0\nHOME,England,1.0\n"
        "SCOT,Scotland,1.0\nSCOT2,Scotland,1.0\n")
    (tmp_path / "housebreaking.csv").write_text(
        "name,hb_1yr,hb_3yr\nSCOT,3.0,3.3\nSCOT2,30.0,33.0\n")
    names = np.array(["CORE", "HOME", "SCOT", "SCOT2"])
    hh = np.array([100.0, 5000.0, 900.0, 900.0])

    rate = sr.theft_from_police(names, hh)
    assert rate[2] == pytest.approx(3.3 / 900.0)      # hb_3yr, not hb_1yr
    assert rate[3] == pytest.approx(33.0 / 900.0)
    assert rate[3] > rate[2]                          # geography, not a rate

    # wrong grain: the file joins nothing rather than yielding zeros
    (tmp_path / "housebreaking.csv").write_text(
        "name,hb_1yr,hb_3yr\nSCOT 1,3.0,3.3\nSCOT2 1,30.0,33.0\n")
    with pytest.raises(SystemExit, match="housebreaking.csv covers only"):
        sr.theft_from_police(names, hh)

    (tmp_path / "housebreaking.csv").unlink()
    with pytest.raises(SystemExit, match="housebreaking.csv missing"):
        sr.theft_from_police(names, hh)


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
        "th_rate": [0.010, 0.005], "eow_rate": [0.011, 0.009],
        "sub_rel": [1.0, 1.0],
        "fire_rate": [0.002, 0.001], "ad_rate": [0.009, 0.008],
        "ct_th": [1.0, 1.0], "ct_eow": [1.0, 1.0],
        "ct_fire": [1.0, 1.0], "ct_ad": [1.0, 1.0],
    })
    sim, _ = bm.simulate(df)

    expected = 0.24 / bm.EROSION_HORIZON_YEARS * bm.ABI["sev_erosion"]
    assert abs(sim["el_er"][0] - expected) / expected < 1e-9
    assert sim["el_er"][1] == 0.0                     # no exposure, no loss
    # and the five-peril total is the four-peril total plus exactly that
    assert abs((sim["el_total5"][0] - sim["el_total"][0])
               - sim["el_er"][0]) < 1e-6


def _cover_split_frame():
    import pandas as pd
    return pd.DataFrame({
        "sub_score": [0.5, 0.2], "wx_score": [0.5, 0.4],
        "fl_score": [0.3, 0.6], "gw_score": [0.2, 0.1],
        "er_score": [0.0, 0.0],
        "f_high": [0.1, 0.0], "f_low": [0.2, 0.05],
        "sw_high": [0.05, 0.01], "sw_low": [0.1, 0.03],
        "gw_frac": [0.1, 0.0], "sw_sev": [1.0, 1.0],
        "er_frac": [0.0, 0.0], "households": [1000.0, 2000.0],
        "th_rate": [0.010, 0.005], "eow_rate": [0.011, 0.009],
        "sub_rel": [1.0, 1.0],
        "fire_rate": [0.002, 0.001], "ad_rate": [0.009, 0.008],
        # Neutral council-tax relativities (Phase 2c). marginal_params
        # reads these for the four attritional severities, so the frame
        # cannot be built without them. 1.0 keeps this frame testing the
        # cover split alone, which is what these two tests are about.
        "ct_th": [1.0, 1.0], "ct_eow": [1.0, 1.0],
        "ct_fire": [1.0, 1.0], "ct_ad": [1.0, 1.0],
    })


def test_cover_split_is_a_pure_reweighting_of_the_same_losses(monkeypatch):
    """The buildings/contents split must re-weight the losses the model
    already simulated, never re-estimate them. Two degenerate settings
    prove it without depending on the published split fractions: send
    every peril to buildings and the buildings leg must equal the whole,
    send every peril to contents and it must vanish - exactly, not
    approximately, at both the expected-loss and the capital-allocation
    level."""
    monkeypatch.setattr(bm, "N_SIM", 400)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = _cover_split_frame()

    monkeypatch.setattr(bm, "SPLIT_BUILDINGS",
                        {k: 1.0 for k in bm.SPLIT_BUILDINGS})
    allb, _ = bm.simulate(df)
    assert allb["el_buildings"] == pytest.approx(allb["el_total"], abs=1e-9)
    assert allb["tvar99_euler_b"] == pytest.approx(allb["tvar99_euler"],
                                                   abs=1e-9)
    assert allb["el_year_b"] == pytest.approx(allb["el_year"], abs=1e-9)

    monkeypatch.setattr(bm, "SPLIT_BUILDINGS",
                        {k: 0.0 for k in bm.SPLIT_BUILDINGS})
    allc, _ = bm.simulate(df)
    assert allc["el_buildings"] == pytest.approx(0.0, abs=1e-9)
    assert allc["tvar99_euler_b"] == pytest.approx(0.0, abs=1e-9)
    # the totals themselves are untouched by where the split sends the loss
    assert allc["el_total"] == pytest.approx(allb["el_total"], abs=1e-12)
    assert allc["tvar99_euler"] == pytest.approx(allb["tvar99_euler"],
                                                 abs=1e-12)


def test_cover_split_fractions_are_shares(monkeypatch):
    """Every peril's buildings share is a fraction, and every modelled
    peril has one - a peril added to the model without a split entry
    would silently vanish from both covers."""
    priced = {"sub", "wx", "fl", "gw", "th", "eow", "fire", "ad"}
    assert set(bm.SPLIT_BUILDINGS) == priced
    for peril, share in bm.SPLIT_BUILDINGS.items():
        assert 0.0 <= share <= 1.0, f"{peril} share {share} is not a fraction"


def test_theft_expected_loss_is_analytic_not_simulated(monkeypatch):
    """Theft shares ONE U_th stream across all districts, so a simulated
    mean carries a common sampling error - the first evidence run came out
    +17% over the calibrated level in every district at once. simulate()
    must return p_th * E[severity] exactly, at any simulation length, and
    el_total must carry the analytic leg so the published level is the
    calibrated one."""
    import pandas as pd

    monkeypatch.setattr(bm, "N_SIM", 200)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = pd.DataFrame({
        "sub_score": [0.5, 0.2], "wx_score": [0.5, 0.4],
        "fl_score": [0.3, 0.6], "gw_score": [0.2, 0.1],
        "er_score": [0.0, 0.0],
        "f_high": [0.1, 0.0], "f_low": [0.2, 0.05],
        "sw_high": [0.05, 0.01], "sw_low": [0.1, 0.03],
        "gw_frac": [0.1, 0.0], "sw_sev": [1.0, 1.0],
        "er_frac": [0.0, 0.0], "households": [1000.0, 2000.0],
        "th_rate": [0.010, 0.0], "eow_rate": [0.0, 0.0],
        "sub_rel": [1.0, 1.0],
        "fire_rate": [0.0, 0.0], "ad_rate": [0.0, 0.0],
        "ct_th": [1.0, 1.0], "ct_eow": [1.0, 1.0],
        "ct_fire": [1.0, 1.0], "ct_ad": [1.0, 1.0],
    })
    sim, _ = bm.simulate(df)

    expected = 0.010 * bm.FREQ_SCALE["th"] * bm.ABI["sev_theft"]
    assert abs(sim["el_th"][0] - expected) / expected < 1e-9
    assert sim["el_th"][1] == 0.0                     # no burglary, no loss
    # el_total = the four weather-peril draw means + the analytic theft leg
    four = (sim["el_sub"][0] + sim["el_wx"][0]
            + sim["el_fl"][0] + sim["el_gw"][0])
    assert abs((sim["el_total"][0] - four) - sim["el_th"][0]) < 1e-6


def test_fire_severity_mean_hits_the_anchor_average():
    """sev_fire's lognormal MEAN equals the anchor-triangle average claim
    (£14,000) regardless of the sigma chosen for the spread."""
    m = bm.marginal_params(fields())
    mean = float(np.mean(np.exp(m["sev_fire"]["mu"] + m["sev_fire"]["sigma"] ** 2 / 2)))
    assert abs(mean / bm.ABI["sev_fire"] - 1) < 1e-6


def test_fire_frequency_is_the_dwelling_rate_scaled():
    """p_fire is the precomputed fire_rate (anchor level x dwelling-fire
    relativity, built in main() where the exposure weights live) times
    the ABI level scale and nothing else - marginal_params must not
    renormalise it, because it runs on batches and a per-chunk mean
    would depend on chunk membership. This is the guard the EoW wiring
    added after the 0.5-clip near-miss: feed a RATE, never an O(1)
    relativity."""
    old = dict(bm.FREQ_SCALE)
    try:
        bm.FREQ_SCALE = dict(old, fire=0.9)
        m = bm.marginal_params(fields(fire=0.003))
        assert abs(float(m["p_fire"][0]) - 0.003 * 0.9) < 1e-12
        # and the safety clip cannot produce a probability above one half
        m = bm.marginal_params(fields(fire=80.0))
        assert float(m["p_fire"][0]) == 0.5
    finally:
        bm.FREQ_SCALE = old


def test_fire_expected_loss_is_analytic_not_simulated(monkeypatch):
    """Fire shares the theft/EoW failure mode - ONE U_fire stream across
    every district - and at p ~ 0.2% with sigma 1.3 a simulated mean
    would be noisier than either. simulate() must return
    p_fire * E[severity] exactly, at any simulation length, and
    el_total must carry the analytic leg."""
    import pandas as pd

    monkeypatch.setattr(bm, "N_SIM", 200)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = pd.DataFrame({
        "sub_score": [0.5, 0.2], "wx_score": [0.5, 0.4],
        "fl_score": [0.3, 0.6], "gw_score": [0.2, 0.1],
        "er_score": [0.0, 0.0],
        "f_high": [0.1, 0.0], "f_low": [0.2, 0.05],
        "sw_high": [0.05, 0.01], "sw_low": [0.1, 0.03],
        "gw_frac": [0.1, 0.0], "sw_sev": [1.0, 1.0],
        "er_frac": [0.0, 0.0], "households": [1000.0, 2000.0],
        "th_rate": [0.0, 0.0], "eow_rate": [0.0, 0.0],
        "sub_rel": [1.0, 1.0],
        "fire_rate": [0.0025, 0.0], "ad_rate": [0.0, 0.0],
        "ct_th": [1.0, 1.0], "ct_eow": [1.0, 1.0],
        "ct_fire": [1.0, 1.0], "ct_ad": [1.0, 1.0],
    })
    sim, _ = bm.simulate(df)

    expected = 0.0025 * bm.FREQ_SCALE["fire"] * bm.ABI["sev_fire"]
    assert abs(sim["el_fire"][0] - expected) / expected < 1e-9
    assert sim["el_fire"][1] == 0.0                   # no exposure, no loss
    # el_total = the four weather-peril draw means + the analytic fire leg
    four = (sim["el_sub"][0] + sim["el_wx"][0]
            + sim["el_fl"][0] + sim["el_gw"][0])
    assert abs((sim["el_total"][0] - four) - sim["el_fire"][0]) < 1e-6


def test_eow_expected_loss_is_analytic_not_simulated(monkeypatch):
    """Escape of water shares theft's failure mode exactly - ONE U_eow
    stream across every district - so a simulated mean would carry a
    common sampling error into the calibrated level. simulate() must
    return p_eow * E[severity] exactly, at any simulation length, and
    el_total must carry the analytic leg."""
    import pandas as pd

    monkeypatch.setattr(bm, "N_SIM", 200)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = pd.DataFrame({
        "sub_score": [0.5, 0.2], "wx_score": [0.5, 0.4],
        "fl_score": [0.3, 0.6], "gw_score": [0.2, 0.1],
        "er_score": [0.0, 0.0],
        "f_high": [0.1, 0.0], "f_low": [0.2, 0.05],
        "sw_high": [0.05, 0.01], "sw_low": [0.1, 0.03],
        "gw_frac": [0.1, 0.0], "sw_sev": [1.0, 1.0],
        "er_frac": [0.0, 0.0], "households": [1000.0, 2000.0],
        "th_rate": [0.0, 0.0], "eow_rate": [0.012, 0.0],
        "sub_rel": [1.0, 1.0],
        "fire_rate": [0.0, 0.0], "ad_rate": [0.0, 0.0],
        "ct_th": [1.0, 1.0], "ct_eow": [1.0, 1.0],
        "ct_fire": [1.0, 1.0], "ct_ad": [1.0, 1.0],
    })
    sim, _ = bm.simulate(df)

    expected = 0.012 * bm.FREQ_SCALE["eow"] * bm.ABI["sev_eow"]
    assert abs(sim["el_eow"][0] - expected) / expected < 1e-9
    assert sim["el_eow"][1] == 0.0                    # no exposure, no loss
    # el_total = the four weather-peril draw means + the analytic EoW leg
    four = (sim["el_sub"][0] + sim["el_wx"][0]
            + sim["el_fl"][0] + sim["el_gw"][0])
    assert abs((sim["el_total"][0] - four) - sim["el_eow"][0]) < 1e-6


def test_ad_severity_mean_hits_the_anchor_average():
    """sev_ad's lognormal MEAN equals the anchor-triangle average claim
    (£1,650) regardless of the sigma chosen for the spread."""
    m = bm.marginal_params(fields())
    mean = float(np.mean(np.exp(m["sev_ad"]["mu"] + m["sev_ad"]["sigma"] ** 2 / 2)))
    assert abs(mean / bm.ABI["sev_ad"] - 1) < 1e-6


def test_ad_frequency_is_the_child_share_rate_scaled():
    """p_ad is the precomputed ad_rate (anchor level x child-share
    relativity, built in main() where the exposure weights live) times
    the ABI level scale and nothing else - the rate-not-relativity
    guard, fourth application."""
    old = dict(bm.FREQ_SCALE)
    try:
        bm.FREQ_SCALE = dict(old, ad=0.95)
        m = bm.marginal_params(fields(ad=0.010))
        assert abs(float(m["p_ad"][0]) - 0.010 * 0.95) < 1e-12
        # and the safety clip cannot produce a probability above one half
        m = bm.marginal_params(fields(ad=80.0))
        assert float(m["p_ad"][0]) == 0.5
    finally:
        bm.FREQ_SCALE = old


def test_ad_expected_loss_is_analytic_not_simulated(monkeypatch):
    """AD shares the theft/EoW/fire failure mode - ONE U_ad stream
    across every district - so simulate() must return
    p_ad * E[severity] exactly, at any simulation length, and el_total
    must carry the analytic leg."""
    import pandas as pd

    monkeypatch.setattr(bm, "N_SIM", 200)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = pd.DataFrame({
        "sub_score": [0.5, 0.2], "wx_score": [0.5, 0.4],
        "fl_score": [0.3, 0.6], "gw_score": [0.2, 0.1],
        "er_score": [0.0, 0.0],
        "f_high": [0.1, 0.0], "f_low": [0.2, 0.05],
        "sw_high": [0.05, 0.01], "sw_low": [0.1, 0.03],
        "gw_frac": [0.1, 0.0], "sw_sev": [1.0, 1.0],
        "er_frac": [0.0, 0.0], "households": [1000.0, 2000.0],
        "th_rate": [0.0, 0.0], "eow_rate": [0.0, 0.0],
        "sub_rel": [1.0, 1.0],
        "fire_rate": [0.0, 0.0], "ad_rate": [0.0095, 0.0],
        "ct_th": [1.0, 1.0], "ct_eow": [1.0, 1.0],
        "ct_fire": [1.0, 1.0], "ct_ad": [1.0, 1.0],
    })
    sim, _ = bm.simulate(df)

    expected = 0.0095 * bm.FREQ_SCALE["ad"] * bm.ABI["sev_ad"]
    assert abs(sim["el_ad"][0] - expected) / expected < 1e-9
    assert sim["el_ad"][1] == 0.0                     # no exposure, no loss
    # el_total = the four weather-peril draw means + the analytic AD leg
    four = (sim["el_sub"][0] + sim["el_wx"][0]
            + sim["el_fl"][0] + sim["el_gw"][0])
    assert abs((sim["el_total"][0] - four) - sim["el_ad"][0]) < 1e-6


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
        "th_rate": rng.uniform(0.001, 0.03, n),
        # appended LAST: earlier draws keep their positions in the fixture
        # stream, so pre-EoW expectations in these tests stay valid
        "eow_rate": rng.uniform(0.005, 0.03, n),
        "sub_rel": np.ones(n),
        # and fire after EoW, same discipline
        "fire_rate": rng.uniform(0.001, 0.005, n),
        # and AD after fire, same discipline
        "ad_rate": rng.uniform(0.006, 0.012, n),
        # band-value severity relativities: neutral, so every el_
        # assertion in here keeps reading straight off the ABI anchors
        "ct_th": np.ones(n), "ct_eow": np.ones(n),
        "ct_fire": np.ones(n), "ct_ad": np.ones(n),
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
        "th_rate": rng.uniform(0.001, 0.03, n),
        # appended LAST: earlier draws keep their positions in the fixture
        # stream, so pre-EoW expectations in these tests stay valid
        "eow_rate": rng.uniform(0.005, 0.03, n),
        "sub_rel": np.ones(n),
        # and fire after EoW, same discipline
        "fire_rate": rng.uniform(0.001, 0.005, n),
        # and AD after fire, same discipline
        "ad_rate": rng.uniform(0.006, 0.012, n),
        # band-value severity relativities: neutral, so every el_
        # assertion in here keeps reading straight off the ABI anchors
        "ct_th": np.ones(n), "ct_eow": np.ones(n),
        "ct_fire": np.ones(n), "ct_ad": np.ones(n),
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
    # el_th joined the insured total on exp/theft-peril. A build from
    # before the theft peril has no el_th column at all - that reads as
    # zero, and the identity still binds. A build that LOST el_th while
    # el_total still contains theft fails by ~GBP 29, so the fallback
    # cannot mask a partial regression.
    el_th = col("el_th")
    if np.isnan(el_th).all():
        el_th = np.zeros(len(feats))
    # el_eow gets the same treatment for the same reason: absent reads as
    # zero (a pre-EoW build still satisfies the identity), but a build
    # that lost the column while el_total contains EoW fails by ~GBP 42.
    el_eow = col("el_eow")
    if np.isnan(el_eow).all():
        el_eow = np.zeros(len(feats))
    # el_fire likewise: absent reads as zero, a lost column fails by
    # ~GBP 28. (The fire evidence run itself taught this the hard way:
    # forgetting to add the new leg HERE failed the identity check at
    # the END of the 55-minute rebuild, after the artifact upload was
    # skipped - the whole run was lost. When adding a peril, this test
    # is part of the wiring, not part of the copy pass.)
    el_fire = col("el_fire")
    if np.isnan(el_fire).all():
        el_fire = np.zeros(len(feats))
    # el_ad likewise: absent reads as zero, a lost column fails by
    # ~GBP 15.
    el_ad = col("el_ad")
    if np.isnan(el_ad).all():
        el_ad = np.zeros(len(feats))
    # Tolerance is the rounding budget, not a vibe: el_total and each of
    # the EIGHT legs is written at 1dp (+-0.05 each), so the legitimate
    # worst case is 9 x 0.05 = 0.45. The old 0.30 was sized for six legs
    # and fire's arrival produced a sector that stacked its roundings to
    # exactly 0.30 + 1e-13 - a real build failed on float epsilon. The
    # bound moves in the SAME commit as the peril that widens it.
    assert np.abs(el_total - (col("el_sub") + col("el_wx") + col("el_fl")
                              + col("el_gw") + el_th + el_eow
                              + el_fire + el_ad)).max() <= 0.45
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

    # Enumerated from disk, not listed here. This was a hard-coded pair
    # until temperature.template.html was added beside them and every one
    # of its placeholders read as "defined but unused" - the guard could
    # not see the page it was meant to be guarding. A glob cannot fall
    # behind the directory; the count assertion below stops it silently
    # matching nothing instead.
    used = set()
    templates = sorted(f for f in os.listdir(os.path.join(root, "site"))
                       if f.endswith(".template.html"))
    assert len(templates) >= 3, (
        f"only {templates} found in site/ - the glob is stale, and an "
        "unscanned template ships raw __TOKENS__ to the live page")
    for tpl in templates:
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


def test_templates_do_not_retype_live_model_figures():
    """A model figure typed into a template goes stale silently.

    This is the defect this repository keeps rediscovering. The peril
    table hand-wrote the theft cap and contradicted the prose two
    sections down. The temperature tab then shipped with THIRTEEN typed
    figures - the bad-year decomposition, the premium, and the peril
    shares - every one measured before Gate 2 and every one wrong by
    publication, including `GBP169.66` when the model had moved to
    169.6477. Nothing caught any of it, because a typed number is
    perfectly valid HTML and the page it contradicts is a different file.

    So the check is the other way round: take what the model says NOW,
    format it exactly as the placeholder does, and fail if that string
    appears literally in a template. Whatever collides is either the
    figure (inject it) or a genuine coincidence (see below).

    Deliberately NOT checked: EOW_FREEZE_SHARE as "31%". The methodology
    page's claims-mix table legitimately sums to 31%, so that string
    cannot distinguish the constant from an unrelated total - a guard
    that cries wolf gets weakened, and a weakened guard is worse than an
    honest gap. It is injected as __EOW_FREEZE_PCT__ regardless.
    """
    import json
    import re
    root = os.path.join(os.path.dirname(__file__), "..")

    with open(os.path.join(root, "data", "districts_risk.geojson"),
              encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    hh = sum(p.get("households", 0) for p in feats)
    prem = sum(p["premium"] * p.get("households", 0) for p in feats) / hh

    forbidden = {
        f"{prem:,.2f}": "the household-weighted premium - use __PREM_MEAN__",
        f"{100 * bm.SUB_DROUGHT_SHARE:.1f}%":
            "SUB_DROUGHT_SHARE - use __SUB_DROUGHT_PCT__",
        f"{100 * (1 - bm.SUB_DROUGHT_SHARE):.1f}%":
            "the flat remainder - use __SUB_FLAT_PCT__",
    }

    templates = sorted(f for f in os.listdir(os.path.join(root, "site"))
                       if f.endswith(".template.html"))
    assert len(templates) >= 3, f"only {templates} found - glob is stale"

    typed = []
    for tpl in templates:
        with open(os.path.join(root, "site", tpl), encoding="utf-8") as fh:
            body = fh.read()
        # Strip <style> - CSS carries percentages and lengths that can
        # collide with a share by pure arithmetic accident.
        body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
        for lit, why in forbidden.items():
            if lit in body:
                line = body[:body.index(lit)].count("\n") + 1
                typed.append(f"{tpl}:{line} types {lit!r} - {why}")

    assert not typed, (
        "a live model figure is typed into a template; it will be wrong "
        "the next time the model moves and nothing else will notice:\n  "
        + "\n  ".join(typed))


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
        # the vector tile set, which is handed to the PMTiles protocol
        # through new URL(...) rather than fetched directly - a fourth
        # reference style, and the one whose 404 would blank the map
        re.compile(r'new URL\(\s*["\']([^"\']+)["\']'),
    ]
    external = ("http://", "https://", "//", "#", "data:", "mailto:",
                "javascript:")
    site_root = "https://smcode-source.github.io/uk-home-insurance-risk-map/"

    # Tiles, popup shards and the name index are BUILD outputs, kept out
    # of git because PMTiles do not delta-compress (~33 MB per publish).
    # On an unbuilt checkout they are absent BY CONSTRUCTION, so their
    # existence is not a thing this test can assert there. It still
    # asserts every committed reference, and still asserts that the
    # pages REFERENCE the tiles (the required[] list below). The
    # existence check is run post-build by pages.yml before deploying
    # and by tests.yml's rebuild job on every push.
    built = os.path.isdir(os.path.join(docs, "assets", "tiles"))
    BUILD_ONLY = ("assets/tiles/", "assets/units/",
                  "assets/districts_index.json",
                  "assets/sectors_index.json")

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
                if not built and target.lstrip("/").startswith(BUILD_ONLY):
                    continue
                if not os.path.exists(os.path.join(docs, target.lstrip("/"))):
                    missing.append((page, ref))

    assert not missing, f"docs/ references files that do not exist: {missing}"
    # again, pin the scale so a template rewrite cannot silently empty this
    assert len(checked) >= 8, (
        f"only {len(checked)} local references found across {len(pages)} "
        f"pages - the extraction has stopped matching")
    for required in ("assets/site.css", "assets/districts.json",
                     "assets/social.png", "assets/maplibre-gl.js",
                     "assets/districts_index.json",
                     "assets/tiles/districts.pmtiles"):
        assert required in checked, (
            f"{required} is no longer referenced by any page - if that is "
            f"deliberate, stop building it too")


def test_the_methodology_figure_uses_the_maps_own_climate_ramp():
    """The districts-vs-sectors figure must not invent its own colours.

    It is generated by build_site.py from the published GeoJSON, while
    the live map colours the same quantity from map/template.html. Two
    copies of a ramp is two chances to retune one and not the other, and
    a reader comparing the figure with the map would be misled by a
    difference nobody intended - so pin them equal.
    """
    import re
    import build_site
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "map", "template.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()

    ramp = re.search(r"const RAMP_DIVERGING = \[([^\]]+)\]", tpl)
    breaks = re.search(r"const CC_BREAKS = \[([^\]]+)\]", tpl)
    assert ramp and breaks, "the map's climate ramp declarations moved"
    map_ramp = [c.strip().strip("'\"") for c in ramp.group(1).split(",")]
    map_breaks = [float(v) for v in breaks.group(1).split(",")]

    assert build_site.CC_RAMP == map_ramp, (
        f"figure ramp {build_site.CC_RAMP} != map ramp {map_ramp}")
    assert [float(v) for v in build_site.CC_BREAKS] == map_breaks, (
        f"figure breaks {build_site.CC_BREAKS} != map breaks {map_breaks}")
    assert len(map_ramp) == len(map_breaks) + 1, (
        "a diverging ramp needs exactly one more colour than it has breaks")


def test_the_sector_model_nests_inside_the_district_model():
    """Sectors are the district model at finer grain, not a second model.

    Publishing both invites the reader to compare them, so the two must
    actually be comparable:

      * every sector's name is its district plus one digit, and every
        modelled district is covered - the nesting the whole derivation
        rests on (derive_sectors.py partitions each district);
      * household exposure is conserved - the sector build must not
        invent or lose homes against the district build;
      * household-weighted sector premiums must aggregate back to the
        district level. Not exactly: different geography means different
        hazard aggregation and a separately-fitted decile split. But a
        LARGE drift would mean the geography change moved the model
        rather than resolving it, which is the one thing that would
        make publishing them side by side dishonest.
    """
    import json
    from collections import defaultdict
    root = os.path.join(os.path.dirname(__file__), "..")

    def props(name):
        with open(os.path.join(root, "data", name), encoding="utf-8") as fh:
            return [f["properties"] for f in json.load(fh)["features"]]

    districts = {p["name"]: p for p in props("districts_risk.geojson")}
    sectors = props("sectors_risk.geojson")

    # On this branch build_model writes the SECTOR grain to the generic
    # output path, so data/districts_risk.geojson is not a district build
    # and there is nothing to nest against. Detect that rather than fail:
    # a district name is an outward code with no space ("AB10"), a sector
    # name always carries the inward digit ("AB10 1"). The test still runs
    # for real on main, which is the grain pair that actually publishes.
    if districts and any(" " in n for n in districts):
        pytest.skip("districts_risk.geojson is at sector grain on this "
                    "branch - run this test on main, where the district "
                    "build and the crossed sector output sit side by side")
    assert len(sectors) > 10000, f"only {len(sectors)} sectors"

    by_district = defaultdict(list)
    for s in sectors:
        assert " " in s["name"], f"{s['name']} carries no sector digit"
        outward, digit = s["name"].rsplit(" ", 1)
        assert len(digit) == 1 and digit.isalnum(), s["name"]
        by_district[outward].append(s)

    orphans = sorted(set(by_district) - set(districts))
    assert not orphans, f"sectors outside any modelled district: {orphans[:5]}"
    uncovered = sorted(set(districts) - set(by_district))
    assert not uncovered, (
        f"{len(uncovered)} modelled districts have no sectors, first "
        f"{uncovered[:5]} - the partition is incomplete")

    # Exposure must now agree to a fraction of a per cent. It did NOT
    # before 2026-08-12: the sector build ran 2.7% light because ONSPD
    # retains terminated postcodes (a third of its rows) and households
    # were apportioned across them, so wholly-dead sectors were credited
    # ~730k homes but had no Code-Point centroid and hence no polygon.
    # Excluding terminated postcodes closed the gap to -0.06%, which is
    # the residue of districts whose sectors are not all in the boundary
    # set. Keep this tight: a re-widening means phantom exposure is back.
    hh_d = sum(p.get("households", 0) for p in districts.values())
    hh_s = sum(p.get("households", 0) for p in sectors)
    assert abs(hh_s / hh_d - 1) < 0.005, (
        f"exposure diverged between scales: {hh_d:,.0f} households across "
        f"districts vs {hh_s:,.0f} across sectors "
        f"({100 * (hh_s / hh_d - 1):+.2f}%) - phantom exposure is back, or "
        f"a new cause of loss has appeared")

    # The two resolutions publish through different pipelines - the
    # district file lands via rebuild.yml's bot commit, the sector file
    # is copied over from the sector-model branch - so a NEW PERIL
    # necessarily reaches one committed file before the other. Across
    # that window the level comparison measures the transition, not the
    # geography, and rebuild.yml's pre-flight would deadlock on it (the
    # run that reconciles the files is the run it blocks). Skip only
    # while the peril sets visibly differ; the moment both files carry
    # the same perils this re-arms, so a real level drift still fails.
    d_any = next(iter(districts.values()))
    # Compare the whole el_* column sets rather than naming one peril:
    # the theft transition taught us this guard is needed, and the EoW
    # transition taught us not to hard-code which peril is in flight.
    # PERIL legs only. "el_" also prefixes aggregates and derived
    # columns, and treating those as perils makes this skip far too
    # eager: Phase 3 adds el_buildings/el_contents/el_year_b to the
    # district file, so a district-only publish would have looked like a
    # peril transition and SILENTLY DISARMED both checks below - the
    # exact failure this whole test exists to catch. The skip is for a
    # new peril reaching one grain first, nothing else.
    _derived = {"el_total", "el_total5", "el_total_cc", "el_year",
                "el_year_b", "el_buildings", "el_contents"}
    d_perils = {k for k in d_any if k.startswith("el_")} - _derived
    s_perils = {k for k in sectors[0] if k.startswith("el_")} - _derived
    if d_perils != s_perils:
        pytest.skip("district and sector outputs are mid-transition: "
                    f"peril sets differ by {sorted(d_perils ^ s_perils)} - "
                    "the publish rebuild reconciles them")

    num = den = 0.0
    for name, group in by_district.items():
        for s in group:
            w = s.get("households", 0)
            num += w * s["premium"]
            den += w
    sector_level = num / den
    district_level = (sum(p.get("households", 0) * p["premium"]
                          for p in districts.values()) / hh_d)
    # 0.5%, tightened from 5% on 2026-08-25. The loose bound is why this
    # test watched both publish-order mistakes go by without a word: the
    # grains sat 1.39% apart across the 2026-08-19 window and 4.1% apart
    # across the 2026-08-25 one, and BOTH fit inside 5%. HANDOFF recorded
    # the guard as "not built"; it was built, just set 574x wider than the
    # thing it was guarding against.
    #
    # 0.5% is ~57x the agreement the grains actually hold (0.0087% today,
    # 0.0085% historically) and ~8x under the drift that got through. It
    # is deliberately not tighter: a real model change may widen the
    # genuine geography gap, and this must fail on mixed pairs, not on
    # honest resolution differences.
    #
    # This does mean rebuild.yml's pre-flight refuses to run while the two
    # committed files disagree. That is the intended behaviour and not the
    # deadlock the peril-set skip above avoids: recovery from a mixed pair
    # is crossing the sector file, a plain commit, not a rebuild. Both
    # sanctioned publish orders land the pair in ONE push, so a correct
    # publish never sees this.
    assert abs(sector_level / district_level - 1) < 0.005, (
        f"exposure-weighted premium differs by "
        f"{100 * (sector_level / district_level - 1):+.3f}% between scales "
        f"(£{district_level:.2f} vs £{sector_level:.2f}) - the two grains "
        f"are a MIXED PAIR: one file carries a model change the other does "
        f"not, and the live site is serving both. Cross the sector output "
        f"to main, or hold the district publish until it is ready")

    # The level check above is necessary and NOT sufficient. It compares
    # one national number, so it is blind to a re-rating: Phase 2c moved
    # 70.5% of districts across rating groups while leaving the level at
    # -0.00%, and a mixed pair across that publish sat 0.009% apart on
    # level - inside ANY level bound, including this one. Two grains can
    # agree perfectly on the national premium while disagreeing about
    # every district in the country.
    #
    # So also check the shape: each district against the household-
    # weighted mean of its own sectors. Measured on the Phase 2c publish,
    # where both pairs existed on disk at once:
    #
    #   consistent pair   median 1.09%   p95  6.43%   47 districts >10%
    #   mixed pair        median 7.21%   p95 20.36%  964 districts >10%
    #
    # The median separates them by 6.6x. 3% sits ~2.7x above the honest
    # grain difference and ~2.4x below a stale pair - the same balance as
    # the level bound. Median rather than max: a handful of districts
    # genuinely disagree at either grain (47 exceed 10% even when the
    # pair is correct), so a max-based bound would be noise.
    devs = []
    for name, group in by_district.items():
        if name not in districts:
            continue
        w = [s.get("households", 0) for s in group]
        if sum(w) <= 0:
            continue
        sm = sum(x * s["premium"] for x, s in zip(w, group)) / sum(w)
        devs.append(abs(sm / districts[name]["premium"] - 1))
    devs.sort()
    median_dev = devs[len(devs) // 2]
    over = sum(1 for d in devs if d > 0.10)
    assert median_dev < 0.03, (
        f"district-by-district the two grains disagree by a median "
        f"{100 * median_dev:.2f}% ({over} of {len(devs)} districts over "
        f"10%) while the national levels still match - this is a MIXED "
        f"PAIR from a re-rating publish, which the level check above "
        f"cannot see. Cross the sector output to main")


def test_every_published_map_asset_carries_the_columns_its_page_reads():
    """The third direction of the column contract, added with sectors.

    The pages carry no data of their own. The popup's row comes from a
    per-postcode-area shard written by build_tiles.py, which is a way to
    ship a silently broken popup - drop a column the template reads and
    it renders `undefined`, with nothing raising anywhere. So: every
    column the template reads must be present on EVERY unit of EVERY
    shard, and the two grains must agree with each other (the same
    template drives both, so a column in one and not the other is a bug
    by construction).

    Checked against the shards rather than the tiles because the shard
    is what the popup reads, and it is the one that carries all 62
    columns - the tile deliberately carries only the 20 that paint.
    """
    import json
    import build_map
    root = os.path.join(os.path.dirname(__file__), "..")
    needed = build_map.columns_read_by_template()
    assert len(needed) > 40, "extractor went stale"

    # Transition guard, not a loophole. When the template is AHEAD of
    # the committed model output - a new column merged, the publish
    # rebuild's bot commit not landed yet - the docs/ assets cannot
    # carry the column by construction, and failing here deadlocks
    # rebuild.yml's pre-flight against the very run that would fix it.
    # Skipping is safe because build_map.rounded_props hard-fails the BUILD
    # if the model output lacks a template-read column, so `undefined`
    # can never actually publish. Once the model output carries every
    # column the template reads, this re-arms and guards drift again.
    with open(os.path.join(root, "data", "districts_risk.geojson"),
              encoding="utf-8") as fh:
        model_cols = set(json.load(fh)["features"][0]["properties"])
    ahead = sorted(needed - model_cols)
    if ahead:
        pytest.skip(f"template reads {ahead}, which the committed model "
                    "output does not carry yet - awaiting the publish "
                    "rebuild's bot commit")

    # Same reason as above: the shards are a build output. Skipping on an
    # unbuilt checkout is safe because build_site.py hard-fails when the
    # shards are missing, so an unbuilt docs/ cannot reach Pages.
    if not os.path.isdir(os.path.join(root, "docs", "assets", "units")):
        pytest.skip("docs/assets/units/ is a build output and this "
                    "checkout has not been built - pages.yml and the "
                    "rebuild job run this check after building")

    seen = {}
    for grain, min_units in (("districts", 2700), ("sectors", 10000)):
        d = os.path.join(root, "docs", "assets", "units", grain)
        assert os.path.isdir(d), f"docs/assets/units/{grain}/ was not built"
        rows = {}
        for f in sorted(os.listdir(d)):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                rows.update(json.load(fh))
        assert len(rows) >= min_units, (
            f"{grain} shards hold only {len(rows)} units")
        cols = set(next(iter(rows.values())))
        missing = sorted(needed - cols)
        assert not missing, (
            f"the {grain} shards lack {missing}, which the map template "
            f"reads - the popup renders `undefined` for them")
        # every unit, not just the first: a column present on one and
        # absent on another is the same bug, one district deep
        ragged = [k for k, v in rows.items() if set(v) != cols]
        assert not ragged, (
            f"{grain}: {len(ragged)} units have a different column set, "
            f"first {ragged[:3]}")
        seen[grain] = cols

    a, b = seen.values()
    assert a == b, (
        f"the two map assets disagree on columns (only in one: "
        f"{sorted(a ^ b)}) - both are built from one template")


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
    import build_map
    root = os.path.join(os.path.dirname(__file__), "..")
    published = set(bm.OUTPUT_COLUMNS)

    # ONE extractor, shared with the asset writer that trims the shipped
    # GeoJSON to these same columns - if the two disagreed, the writer
    # would drop a column this test swears is safe.
    read_by_map = build_map.columns_read_by_template()
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
            "households": [500.0], "th_rate": [0.009], "eow_rate": [0.011],
            "sub_rel": [1.0],
            "fire_rate": [0.002], "ad_rate": [0.009],
            "ct_th": [1.0], "ct_eow": [1.0],
            "ct_fire": [1.0], "ct_ad": [1.0],
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


def test_cover_split_capital_uses_the_same_basis_as_combined_capital(monkeypatch):
    """capital_buildings must be built on the ANALYTIC EL, like capital.

    This is the corner the older split test could not reach: it exercised
    simulate() only, and the capital columns are assembled afterwards in
    main(). Send every peril to buildings and capital_buildings must equal
    capital exactly; send every peril to contents and it must vanish.
    Against a draw-mean EL (`el_year_b`, which is what shipped until
    2026-08-25) the first corner came back 0.2-0.3% low, and the
    additivity assertion in apply_cover_split could not see it because
    capital_contents is defined as the remainder.
    """
    import pandas as pd
    monkeypatch.setattr(bm, "N_SIM", 400)
    monkeypatch.setattr(bm, "BATCH", 8)
    df = _cover_split_frame()

    def split_at(fraction):
        monkeypatch.setattr(bm, "SPLIT_BUILDINGS",
                            {k: fraction for k in bm.SPLIT_BUILDINGS})
        sim, _ = bm.simulate(df)
        g = pd.DataFrame({k: sim[k] for k in
                          ("el_total", "el_buildings", "tvar99_euler",
                           "tvar99_euler_b", "el_year_b")})
        g["capital"] = 0.06 * np.maximum(g["tvar99_euler"] - g["el_total"], 0.0)
        g["premium"] = g["el_total"] + g["capital"]
        return bm.apply_cover_split(g)

    allb = split_at(1.0)
    assert allb["capital_buildings"].values == pytest.approx(
        allb["capital"].values, abs=1e-9)
    assert allb["capital_contents"].values == pytest.approx(0.0, abs=1e-9)
    assert allb["premium_buildings"].values == pytest.approx(
        allb["premium"].values, abs=1e-9)

    allc = split_at(0.0)
    assert allc["capital_buildings"].values == pytest.approx(0.0, abs=1e-9)
    assert allc["capital_contents"].values == pytest.approx(
        allc["capital"].values, abs=1e-9)
    assert allc["premium_contents"].values == pytest.approx(
        allc["premium"].values, abs=1e-9)


def test_every_split_peril_has_a_published_anchor():
    """SPLIT_ANCHORED may only name perils DATA_SOURCES #31 anchors.

    The site splits exactly this set and leaves the rest blank, so adding
    a peril here silently promotes a guess to a published figure. That
    already happened once: SPLIT_BUILDINGS shipped theft 0.20, fire 0.70,
    flood 0.65 and groundwater 0.80 as though they were anchors, when the
    anchor search had settled on 0.242, 0.78, 0.48 and 0.48. This pins
    the anchored values to the sources so the two cannot drift apart
    again without a test failing.
    """
    anchors = {"sub": 1.00,    # contents excluded in every wording checked
               "th": 0.242,    # ONS CSEW nature-of-crime damage share
               "fire": 0.78,   # Home Office economic and social cost of fire
               "fl": 0.48,     # Multi-Coloured Manual depth-damage curves
               "gw": 0.48}     # same curves, same water
    assert set(bm.SPLIT_ANCHORED) == set(anchors), (
        "SPLIT_ANCHORED changed - every member needs a source in "
        "DATA_SOURCES #31 before the site is allowed to split it")
    for peril, expected in anchors.items():
        assert bm.SPLIT_BUILDINGS[peril] == pytest.approx(expected), (
            f"{peril} is declared anchored but carries "
            f"{bm.SPLIT_BUILDINGS[peril]}, not the published {expected}")
    assert set(bm.SPLIT_ANCHORED) < set(bm.SPLIT_BUILDINGS)
    assert set(bm.PERIL_LABELS) == set(bm.SPLIT_BUILDINGS)


def test_the_published_cover_table_adds_up():
    """The risk-type table must reconcile to el_total and split only the
    anchored perils - it is a disclosure, so its arithmetic is the claim."""
    import json
    import numpy as np
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "districts_risk.geojson")
    if not os.path.exists(path):
        pytest.skip("no built model output")
    with open(path, encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    w = np.array([p.get("households", 1) for p in feats], dtype=float)
    tot = np.average([p["el_total"] for p in feats], weights=w)
    legs = {k: float(np.average([p["el_" + k] for p in feats], weights=w))
            for k in bm.PERIL_LABELS}
    # The eight labelled perils ARE el_total; erosion is deliberately out.
    # Tolerance is set by the PUBLISHED file, which carries one decimal
    # place: eight rounded legs against one rounded total leaves ~0.03 on
    # 164, so 2e-3 absorbs the rounding. It still catches a dropped peril
    # - the smallest, groundwater, is 0.8% of cost, forty times the
    # tolerance.
    assert sum(legs.values()) == pytest.approx(tot, rel=2e-3), (
        "the risk-type table does not reconcile to el_total - a peril is "
        "missing from PERIL_LABELS, or erosion has leaked into el_total")
    anchored = sum(v for k, v in legs.items() if k in bm.SPLIT_ANCHORED)
    assert 0.4 * tot < anchored < 0.8 * tot, (
        f"anchored share is {100 * anchored / tot:.1f}% - if this moved a "
        "long way the table's headline claim needs rewriting, not the bound")
def test_no_capital_formula_is_taken_against_a_draw_mean():
    """Capital is always (tail - analytic EL), never (tail - draw mean).

    `el_total` is the sum of the analytic legs (p * E[sev]); `el_year` is
    the mean of the simulated years. They estimate the same quantity and
    differ only by Monte Carlo error, which is exactly what makes this bug
    survivable: it never looks wrong, it just quietly puts capital on a
    basis the calibration loop does not target.

    The 2026-08-18 audit moved the model onto the analytic basis but missed
    call sites. Three more surfaced afterwards, one at a time - the
    cover-split capital, its buildings leg, and sensitivity.py - each found
    by hand, none by CI. This test is that sweep made permanent. It reads
    the source rather than the numbers, because the two bases agree to
    fractions of a percent: no value assertion would ever fail on this.
    """
    import re
    from pathlib import Path

    def first_argument(code, open_paren):
        """Text of arg 1 of the call whose '(' is at `open_paren`.

        Scanned with a paren counter rather than a regex: a non-greedy
        `.*?` still happily runs from one np.maximum call to the next
        file-spanning `, 0.0)` and reports the wrong line.
        """
        depth, i = 0, open_paren
        while i < len(code):
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
                if depth == 0:
                    return code[open_paren + 1:i]
            elif code[i] == "," and depth == 1:
                return code[open_paren + 1:i]
            i += 1
        return ""

    scripts = Path(__file__).resolve().parent.parent / "scripts"
    draw_mean = re.compile(r"\bel_year\w*\b")

    offenders = []
    for src in sorted(scripts.glob("*.py")):
        text = src.read_text(encoding="utf-8")
        # strip comments: prose may name el_year, executable code may not
        code = "\n".join(ln.split("#")[0] for ln in text.splitlines())
        for m in re.finditer(r"np\.maximum\(", code):
            expr = first_argument(code, m.end() - 1)
            if "tvar" not in expr:          # not a capital formula
                continue
            if draw_mean.search(expr):
                line = code[: m.start()].count("\n") + 1
                offenders.append(
                    f"{src.name}:{line}: {' '.join(expr.split())}")

    assert not offenders, (
        "capital taken against a draw mean instead of el_total:\n  "
        + "\n  ".join(offenders))


# The eight rows of README's calibration table, in README's order, each
# naming the two ABI keys the row is a copy of. Groundwater is absent on
# purpose: it has no published total and only its severity is a figure.
README_CALIB_ROWS = [
    ("Storm", "storm_paid", "sev_weather"),
    ("Flood", "flood_paid", "sev_flood"),
    ("Subsidence", "subsidence_paid", "sev_subsidence"),
    ("Theft", "theft_paid", "sev_theft"),
    ("Escape of water", "eow_paid", "sev_eow"),
    ("Fire", "fire_paid", "sev_fire"),
    ("Accidental damage", "ad_paid", "sev_ad"),
]


def test_readme_calibration_table_matches_the_model():
    """README's calibration table is hand-written. Pin it to build_model.ABI.

    Markdown has no build step, so this table is the one statement of the
    anchors that cannot be derived. It has drifted twice in three days -
    theft's 2026-08-25 level correction and subsidence's 2026-08-28
    severity fix - and both times the wrong figure was published and sat
    there. The same table on the methodology page IS derived now
    (build_site.py, the __CAL_*__ keys); this test is the equivalent guard
    for the copy that cannot be.

    Checks the paid total, the average claim and the implied claim count.
    The frequency column is the same division again and is left to the
    count check, which is the tighter of the two.
    """
    import re
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()

    def cells(peril):
        # the table is indented three spaces inside a numbered list item
        m = re.search(r"^\s*\|\s*" + re.escape(peril) + r"\s*\|(.+)$",
                      readme, re.M)
        assert m, f"README has no calibration row for {peril}"
        return [c.strip() for c in m.group(1).split("|")]

    def money(cell):
        m = re.search(r"£([\d,]+(?:\.\d+)?)\s*(m|bn)?", cell)
        assert m, f"no money figure in {cell!r}"
        return float(m.group(1).replace(",", "")) * {
            None: 1.0, "m": 1e6, "bn": 1e9}[m.group(2)]

    def count(cell):
        m = re.search(r"([\d,]+)", cell)
        assert m, f"no count in {cell!r}"
        return float(m.group(1).replace(",", ""))

    wrong = []
    for peril, paid_key, sev_key in README_CALIB_ROWS:
        paid_cell, sev_cell, n_cell = cells(peril)[:3]
        paid, sev = bm.ABI[paid_key], bm.ABI[sev_key]
        if abs(money(paid_cell) - paid) > 0.5e6:
            wrong.append(f"{peril} paid: README {paid_cell!r} vs "
                         f"ABI[{paid_key!r}] = {paid / 1e6:,.1f}m")
        if abs(money(sev_cell) - sev) > 0.5:
            wrong.append(f"{peril} severity: README {sev_cell!r} vs "
                         f"ABI[{sev_key!r}] = {sev:,.0f}")
        # three significant figures, which is how the table is written
        implied = paid / sev
        if abs(count(n_cell) - implied) > max(implied * 0.005, 50):
            wrong.append(f"{peril} implied claims: README {n_cell!r} vs "
                         f"{implied:,.0f}")

    assert not wrong, (
        "README's calibration table no longer matches build_model.ABI:\n  "
        + "\n  ".join(wrong)
        + "\n(README.md is hand-written - fix it there, then re-run "
          "scripts/anchor_budget.py)")


def test_severity_sigma_cannot_move_capital():
    """SEV_SIGMA affects DIAGNOSTICS only - never the published premium.

    Both places the premium comes from take the severity's MEAN and
    nothing else:

      simulate()  el_<peril> = p * exp(mu + sigma^2/2)          (analytic EL)
      simulate()  cond_expected(...) = q * exp(mu + sigma^2/2)  (year_loss,
                  from which tvar99_euler and therefore capital are built)

    and marginal_params sets mu = log(_median_for_mean(M, s)), with
    _median_for_mean(M, s) = M / exp(s^2/2). So exp(mu + s^2/2) == M and
    sigma cancels out of both, exactly.

    That is deliberate, not an oversight: averaging REALISED losses over
    the worst 200 of 20,000 years made the allocation correlate 0.49 with
    itself across seeds, and conditioning on the systemic draw took it to
    0.9985 (see the methodology page, "Averaging expectations, not
    accidents"). The price is that capital responds to frequency
    CLUSTERING and never to severity DISPERSION.

    Gate 3 priced SEV_SIGMA["eow"] at 0.96 / 1.00 / 1.20 / 1.41 on CI
    (run 33217184873) and got tvar99_euler identical to the last bit in
    all four. This test is that result turned into a guard, so nobody
    spends another CI run discovering it. If the model ever SHOULD charge
    capital for severity dispersion, this test is the one to change, and
    changing it means revisiting the seed-stability result above.
    """
    for M in (4_000.0, 17_264.0, 30_000.0):
        base = None
        for s in (0.35, 0.80, 0.96, 1.00, 1.20, 1.41, 1.60):
            mu = np.log(bm._median_for_mean(M, s))
            mean = np.exp(mu + s * s / 2)
            assert abs(mean / M - 1) < 1e-12, (
                f"severity mean moved with sigma: M={M}, sigma={s}, "
                f"got {mean}")
            if base is None:
                base = mean
            # every sigma must give the SAME mean, not merely the right one
            assert abs(mean - base) < 1e-9 * M, (
                f"sigma {s} changed the mean by {mean - base:.3e} on {M}")


def test_year_view_claim_count_and_value():
    """The year view's claim COUNT and VALUE must reconstruct its own means.

    Gate 4. `inc_*_pct` is published to 2 dp of a percent, so deriving a
    cost per claim by dividing `mean_*` by it carries 2.4-12.5% error on
    flood and subsidence and 25-50% on groundwater, whose incidence rounds
    to 0.00/0.01/0.01/0.02 across the four buckets. year_analysis now
    emits both quantities from the unrounded arrays instead.

    This drives year_analysis with a SYNTHETIC year dict whose answers are
    known by construction, so it needs no simulation: every district-year
    loss is a fixed amount on a fixed fraction of exposure. Then

        mean_<peril> == claims_<peril>_per_100k / 1e5 * cost_<peril>_per_claim

    must hold, and cost_<peril>_per_claim must equal the amount actually
    paid per claiming policy.
    """
    n_sim = 1000
    expo_total = 1_000_000.0
    rng = np.random.default_rng(3)
    year = {}
    # peril -> (incidence fraction, cost per claim). Deliberately includes
    # a peril rarer than the 0.01% the old published field could resolve.
    spec = {"s": (0.0015, 17_264.0), "w": (0.0071, 2_450.0),
            "f": (0.0009, 30_000.0), "g": (0.00004, 20_000.0)}
    for k, (frac, cost) in spec.items():
        # vary incidence year to year so the bucket ordering is non-trivial
        jitter = 1.0 + 0.3 * rng.standard_normal(n_sim)
        inc = np.clip(frac * jitter, 0.0, 1.0) * expo_total
        year[f"inc_{k}"] = inc
        year[f"{k}_v"] = inc * cost           # exposure-weighted loss
    for k in ("s", "f", "g"):                 # independence view, unused here
        year[f"{k}_i"] = year[f"{k}_v"]
    year["expo_total"] = expo_total

    out = bm.year_analysis(year, 2736)

    for b in out["buckets"]:
        for key, ik in (("sub", "s"), ("wx", "w"), ("fl", "f"), ("gw", "g")):
            cnt = b[f"claims_{key}_per_100k"]
            cost = b[f"cost_{key}_per_claim"]
            assert cnt > 0, f"{b['label']}/{key}: synthetic data always claims"
            # the cost per claim is known exactly by construction
            assert abs(cost - spec[ik][1]) <= 1, (
                f"{b['label']}/{key}: cost per claim {cost} != "
                f"{spec[ik][1]}")
            # and it must rebuild the published mean
            rebuilt = cnt / 1e5 * cost
            assert abs(rebuilt - b[f"mean_{key}"]) < 0.05 + 0.001 * rebuilt, (
                f"{b['label']}/{key}: {cnt}/1e5 x {cost} = {rebuilt} != "
                f"published mean {b[f'mean_{key}']}")
        # groundwater here is 4 claims per 100k - a rate the OLD 2-dp
        # inc_gw_pct field rounds to 0.00%, i.e. loses completely. This
        # asserts the new field does not.
        assert b["claims_gw_per_100k"] > 0 and b["inc_gw_pct"] == 0.0, (
            "the synthetic groundwater rate should be invisible to "
            "inc_gw_pct and visible to claims_gw_per_100k - if this fails "
            "the rates were changed and the point of the test is lost")

    # totals are claims, not claimants: a policy can claim on two perils
    for b in out["buckets"]:
        parts = sum(b[f"claims_{k}_per_100k"]
                    for k in ("sub", "wx", "fl", "gw"))
        assert abs(b["claims_total_per_100k"] - parts) < 0.02


def test_analytic_el_check_builds_every_column_the_model_scores(
        tmp_path, monkeypatch, capsys):
    """scripts/analytic_el_check.py is the closed-form audit of the
    simulated expected losses, and NOTHING else runs it - it is not in the
    build path, so neither CI nor the rebuild workflow touches it.

    It went dead on 2026-08-31, the moment the Gate 2 SMD curve added
    sub_drought_mm/sub_rel to OUTPUT_COLUMNS, and stayed dead for three
    days without anyone noticing. This drives the real script end to end
    with every reader stubbed, so it costs a second instead of the minutes
    the real fetchers need, and it fails on exactly that rot:

      * a new SCORED column the script does not build (check_scored_columns
        raises), and
      * a new marginal_params input it does not build - ct_th and friends
        are intermediates, absent from OUTPUT_COLUMNS, so
        check_scored_columns is blind to them and _fields() KeyErrors
        instead.

    The stubs are the guard's other half: if the script starts calling a
    reader that is not stubbed here, the real one runs, the test slows to
    a crawl or fails on missing data, and that is the signal to update it.
    """
    import io as _io
    import json as _json
    import runpy
    import geopandas as gpd
    import shapely.geometry as sgeom

    n = 3
    names = ["ZZ1", "ZZ2", "ZZ3"]
    frame = gpd.GeoDataFrame(
        {"name": names, "area": ["test"] * n,
         "geometry": [sgeom.box(-1.0 + i, 51.0 + i, -0.9 + i, 51.1 + i)
                      for i in range(n)]},
        crs="EPSG:4326")

    # The erosion reader hands main() a dict and the script copies it
    # wholesale, so the fixture takes its keys from the published contract
    # rather than from the reader's internals - that way a new er_* column
    # needs no change here, and this test stays the same file on a branch
    # that adds one.
    er = {c: np.zeros(n) for c in bm.OUTPUT_COLUMNS
          if c.startswith("er_") and c != "er_score"}
    er["er_smp105"] = np.array([0.02, 0.0, 0.0])
    if "er_head" in er:
        er["er_head"] = np.array([0.02, 0.0, 0.0])
    if "er_basis" in er:
        er["er_basis"] = np.array(["ncerm", "none", "none"])

    stubs = {
        "load_districts": lambda: frame.copy(),
        "subsidence_score": lambda bng: (
            np.array([0.30, 0.45, 0.60]), np.array(["CLAY"] * n),
            np.array([0.4, 0.5, 0.6]), np.array(["TILL"] * n)),
        "weather_from_metoffice": lambda t: (
            np.array([0.30, 0.40, 0.50]),
            {"wind": np.full(n, 5.0), "wdr": np.full(n, 900.0),
             "rain10": np.full(n, 40.0), "precip": np.full(n, 900.0),
             "gust_rp50": np.full(n, 150.0)}),
        "flood_from_agencies": lambda nm: (
            np.array([0.2, 0.4, 0.6]), np.array([0.02, 0.05, 0.09]),
            np.array([0.05, 0.10, 0.20]), np.array([0.01, 0.02, 0.03]),
            np.array([0.03, 0.05, 0.08])),
        "groundwater_from_ea": lambda nm: (
            np.array([0.1, 0.2, 0.3]), np.array([0.02, 0.05, 0.09])),
        "load_country": lambda nm: np.array(["England"] * n),
        "erosion_from_ncerm": lambda nm: (
            np.array([0.5, 0.0, 0.0]), {k: v.copy() for k, v in er.items()}),
        "load_households": lambda nm: np.array([400.0, 800.0, 1600.0]),
        "sw_depth_severity": lambda nm, hi, lo, hh: (
            np.array([0.9, 1.0, 1.3]), np.array([0.2, 0.4, 0.8])),
        "theft_from_police": lambda nm, hh: np.array([0.006, 0.008, 0.011]),
        "frost_from_metoffice": lambda t: np.array([20.0, 45.0, 80.0]),
        "drought_from_haduk": lambda nm: np.array([90.0, 150.0, 240.0]),
        "fires_from_mhclg": lambda nm, hh: np.array([0.0010, 0.0012, 0.0015]),
        "children_from_census": lambda nm, hh: np.array([0.20, 0.28, 0.36]),
        "ct_value_from_bands": lambda nm: np.array([0.85, 1.00, 1.30]),
    }
    for name, fn in stubs.items():
        assert hasattr(bm, name), f"build_model has no {name} to stub"
        monkeypatch.setattr(bm, name, fn)

    # calibrate_frequency writes module globals; keep the suite order-free
    monkeypatch.setattr(bm, "FREQ_SCALE", dict(bm.FREQ_SCALE))
    monkeypatch.setattr(bm, "ABI_TARGET_FREQ", dict(bm.ABI_TARGET_FREQ))
    monkeypatch.setattr(bm, "FLOOD_SEV_BLEND", bm.FLOOD_SEV_BLEND)

    out = tmp_path / "districts_risk.geojson"
    perils = ("sub", "wx", "fl", "gw", "th", "eow", "fire", "ad")
    with _io.open(out, "w", encoding="utf-8") as fh:
        _json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": None,
             "properties": dict({"name": nm},
                                **{f"el_{k}": 1.0 for k in perils})}
            for nm in names]}, fh)
    monkeypatch.setattr(bm, "OUT", str(out))

    script = os.path.join(os.path.dirname(__file__), "..", "scripts",
                          "analytic_el_check.py")
    runpy.run_path(script, run_name="__main__")

    printed = capsys.readouterr().out
    assert f"districts scored={n} published={n} matched={n}" in printed
    assert "TOTAL" in printed, "the comparison table never printed"
    for k in perils:
        assert f"\n{k:6}" in printed, f"{k} missing from the audit table"
