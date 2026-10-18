"""Guards on the spectral transforms and the shallow-water core.

A subtly wrong dynamical core still draws plausible weather maps, so
nothing here trusts the picture. Each test asserts an identity the
continuous mathematics guarantees exactly: basis orthonormality, exact
grid/spectral round-trips, the analytic vorticity of solid-body
rotation, and Williamson case 2 - a steady solution of the full
nonlinear equations that must not move.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nwp.spectral import Sphere, legendre_basis            # noqa: E402
from nwp.shallow_water import (ShallowWater,               # noqa: E402
                               williamson_case2, williamson_case6)

T = 21          # small truncation: these are identities, not resolution tests


@pytest.fixture(scope="module")
def sph():
    return Sphere(trunc=T)


def test_grid_satisfies_the_dealiasing_rule(sph):
    assert sph.nlon >= 3 * sph.trunc + 1
    assert 2 * sph.nlat >= 3 * sph.trunc + 1


def test_gauss_weights_integrate_the_sphere(sph):
    # sum of weights = integral of 1 over mu in [-1, 1]
    assert sph.gauss_w.sum() == pytest.approx(2.0, abs=1e-12)
    assert sph.global_mean(np.ones(sph.grid_shape)) == pytest.approx(1.0, abs=1e-12)


def test_legendre_functions_are_orthonormal(sph):
    """(1/2) integral Pbar_n^m Pbar_n'^m dmu = delta, evaluated by the
    Gauss quadrature the transforms actually use."""
    for m in (0, 1, 5, T):
        P = sph.P[m, m:]                       # (n, k)
        gram = 0.5 * (P * sph.gauss_w) @ P.T
        assert np.allclose(gram, np.eye(gram.shape[0]), atol=1e-11), m


def test_zonal_H_basis_is_exactly_the_derivative(sph):
    """For m = 0 the normalised function is sqrt(2n+1) P_n(mu), whose
    derivative numpy gives exactly as a polynomial - so this compares
    the recurrence against an exact answer, not a difference quotient."""
    mu = np.linspace(-0.999, 0.999, 501)
    P, H = legendre_basis(mu, T)
    for n in (0, 1, 2, 7, T):
        leg = np.polynomial.legendre.Legendre.basis(n)
        exact = np.sqrt(2 * n + 1) * leg.deriv()(mu) * (1 - mu ** 2)
        assert np.allclose(P[0, n], np.sqrt(2 * n + 1) * leg(mu), atol=1e-11), n
        assert np.allclose(H[0, n], exact, atol=1e-9), n


def test_tesseral_H_basis_matches_the_derivative_it_stands_for(sph):
    """For m > 0, differentiate scipy's own associated Legendre with a
    five-point stencil - independent of the recurrence under test."""
    from scipy.special import lpmv

    def pbar(m, n, x):
        # (1/2) int Pbar^2 dmu = 1, and undo scipy's Condon-Shortley phase
        from scipy.special import gammaln
        c = np.exp(0.5 * (np.log(2 * n + 1) + gammaln(n - m + 1)
                          - gammaln(n + m + 1)))
        return (-1.0) ** m * c * lpmv(m, n, x)

    x = np.linspace(-0.9, 0.9, 61)
    h = 1e-3
    for m, n in ((1, 1), (1, 4), (2, 7), (4, 12), (4, T), (T, T)):
        d = (pbar(m, n, x - 2 * h) - 8 * pbar(m, n, x - h)
             + 8 * pbar(m, n, x + h) - pbar(m, n, x + 2 * h)) / (12 * h)
        exact = d * (1 - x ** 2)
        _, H = legendre_basis(x, T)
        assert np.allclose(H[m, n], exact, rtol=1e-5, atol=1e-7), (m, n)


def test_spectral_round_trip_is_the_identity(sph):
    rng = np.random.default_rng(0)
    coef = (rng.normal(size=sph.spec_shape)
            + 1j * rng.normal(size=sph.spec_shape)) * sph.mask
    coef[0] = coef[0].real                     # m=0 is real for a real field
    back = sph.analyse(sph.synth(coef))
    assert np.allclose(back, coef, atol=1e-12)


def test_grid_round_trip_for_a_band_limited_field(sph):
    rng = np.random.default_rng(1)
    coef = (rng.normal(size=sph.spec_shape)
            + 1j * rng.normal(size=sph.spec_shape)) * sph.mask
    coef[0] = coef[0].real
    f = sph.synth(coef)
    assert np.allclose(sph.synth(sph.analyse(f)), f, atol=1e-12)


def test_solid_body_rotation_has_the_analytic_vorticity(sph):
    """u = u0 cos(lat) is solid-body rotation: zeta = 2 u0 sin(lat)/a
    exactly, and the divergence is exactly zero."""
    u0 = 40.0
    lat = sph.lat[:, None] * np.ones(sph.nlon)
    u = u0 * np.cos(lat)
    v = np.zeros_like(u)
    c = np.cos(lat)
    zeta, div = sph.vortdiv_from_uv(u * c, v * c)
    zeta_g = sph.synth(zeta)
    assert np.allclose(zeta_g, 2 * u0 * np.sin(lat) / sph.radius, atol=1e-16)
    assert np.max(np.abs(sph.synth(div))) < 1e-18


def test_wind_and_vorticity_divergence_are_inverse(sph):
    rng = np.random.default_rng(2)
    zeta = (rng.normal(size=sph.spec_shape)
            + 1j * rng.normal(size=sph.spec_shape)) * sph.mask * 1e-5
    div = (rng.normal(size=sph.spec_shape)
           + 1j * rng.normal(size=sph.spec_shape)) * sph.mask * 1e-6
    zeta[0] = zeta[0].real
    div[0] = div[0].real
    zeta[:, 0] = 0                             # the n=0 mode carries no wind
    div[:, 0] = 0
    U, V = sph.uv_from_vortdiv(zeta, div)
    z2, d2 = sph.vortdiv_from_uv(U, V)
    assert np.allclose(z2, zeta, atol=1e-18)
    assert np.allclose(d2, div, atol=1e-18)


def test_transforms_are_batch_transparent(sph):
    """An ensemble transformed together must equal each member alone."""
    rng = np.random.default_rng(3)
    coef = (rng.normal(size=(4,) + sph.spec_shape)
            + 1j * rng.normal(size=(4,) + sph.spec_shape)) * sph.mask
    batch = sph.synth(coef)
    for i in range(4):
        assert np.allclose(batch[i], sph.synth(coef[i]), atol=1e-14)


def test_steady_state_stays_steady(sph):
    """Williamson case 2 is an exact steady solution of the nonlinear
    equations.  Integrate two days and the state must come back.  (Two,
    not five: this runs in every CI job in the repo.)"""
    model = ShallowWater(sph, damping_hours=24.0)
    init = williamson_case2(sph)
    dt = 300.0
    final = model.run(init, days=2.0, dt=dt, sample_hours=24.0)

    h0 = sph.synth(init[2])
    h1 = sph.synth(final[2])
    l2 = np.sqrt(sph.global_mean((h1 - h0) ** 2)) / np.sqrt(sph.global_mean(h0 ** 2))
    assert l2 < 1e-5, f"steady state drifted: relative L2 height error {l2:.2e}"

    u0, v0 = model.wind(init)
    u1, v1 = model.wind(final)
    assert np.max(np.abs(u1 - u0)) < 0.05
    assert np.max(np.abs(v1 - v0)) < 0.05


def test_invariants_are_conserved_on_a_dynamic_flow(sph):
    """The Rossby-Haurwitz wave is not steady, so this checks the
    conservative form of the scheme rather than a fixed point."""
    model = ShallowWater(sph, damping_hours=24.0)
    init = williamson_case6(sph)
    d0 = model.diagnostics(init)
    final = model.run(init, days=2.0, dt=300.0, sample_hours=24.0)
    d1 = model.diagnostics(final)

    # Mass is conserved by the flux form to round-off; nothing removes it.
    assert abs(d1["mass"] / d0["mass"] - 1) < 1e-10

    # Energy leaves only through the hyperdiffusion, and the filter is
    # built to leave the energy-carrying large scales alone.
    assert abs(d1["energy"] / d0["energy"] - 1) < 5e-3

    # Enstrophy is the one that must fall. Two-dimensional turbulence
    # cascades enstrophy DOWNSCALE into the truncation, where the filter
    # exists to absorb it; a scheme whose enstrophy grows is one whose
    # small scales are feeding back, which is how these cores blow up.
    ratio = d1["enstrophy"] / d0["enstrophy"]
    assert ratio <= 1.0 + 1e-9, f"enstrophy grew ({ratio:.6f}): unstable"
    assert ratio > 0.97, f"enstrophy lost too fast ({ratio:.6f}): over-damped"
