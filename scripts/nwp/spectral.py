"""Spherical-harmonic transforms on a Gaussian grid.

The machinery a global atmospheric model runs on: fields live both as
grid values (where products are cheap) and as spectral coefficients
(where derivatives are exact and the Laplacian is diagonal).

Conventions, asserted in tests/test_spectral.py:
  mu = sin(lat) on Gauss-Legendre nodes; (1/2) int Pbar_n^m^2 dmu = 1;
  f = sum_m sum_n f_n^m Pbar_n^m(mu) e^(i m lambda), truncated at n <= T;
  H_n^m = (1-mu^2) dPbar/dmu, built by exact recurrence.

Grid sizes follow the dealiasing rule nlon >= 3T+1, so the quadratic
products the model forms on the grid transform back cleanly. All
transforms take a leading batch axis, so an ensemble is one matmul.
"""

import numpy as np

# WGS84-ish mean Earth radius and rotation rate, the values the
# Williamson et al. (1992) shallow-water test suite specifies.
RADIUS = 6.37122e6          # m
OMEGA = 7.292e-5            # rad/s
GRAVITY = 9.80616           # m/s^2


def _epsilon(n, m):
    """The recurrence coefficient eps_n^m = sqrt((n^2-m^2)/(4n^2-1))."""
    n = np.asarray(n, dtype=float)
    out = np.zeros_like(n)
    ok = n > 0
    out[ok] = np.sqrt((n[ok] ** 2 - m ** 2) / (4 * n[ok] ** 2 - 1))
    return out


def legendre_basis(mu, trunc):
    """Pbar and H = (1-mu^2) dPbar/dmu, shape (T+2, T+2, nlat).

    Indexed [m, n, k].  Degrees up to T+1 are computed because the
    derivative recurrence for degree T reaches one degree higher.
    """
    T = int(trunc)
    nlat = mu.size
    P = np.zeros((T + 2, T + 2, nlat))
    sq = np.sqrt(np.maximum(1.0 - mu ** 2, 0.0))

    # sectoral: Pbar_m^m
    P[0, 0] = 1.0
    for m in range(1, T + 2):
        P[m, m] = np.sqrt((2 * m + 1) / (2 * m)) * sq * P[m - 1, m - 1]

    # first off-diagonal, then the three-term recurrence
    #   mu Pbar_n^m = eps_{n+1}^m Pbar_{n+1}^m + eps_n^m Pbar_{n-1}^m
    for m in range(T + 2):
        if m + 1 <= T + 1:
            P[m, m + 1] = np.sqrt(2 * m + 3) * mu * P[m, m]
        for n in range(m + 2, T + 2):
            e_n = np.sqrt((n ** 2 - m ** 2) / (4 * n ** 2 - 1))
            e_p = np.sqrt(((n - 1) ** 2 - m ** 2) / (4 * (n - 1) ** 2 - 1))
            P[m, n] = (mu * P[m, n - 1] - e_p * P[m, n - 2]) / e_n

    # H_n^m = -n eps_{n+1}^m Pbar_{n+1}^m + (n+1) eps_n^m Pbar_{n-1}^m
    H = np.zeros_like(P)
    for m in range(T + 1):
        for n in range(m, T + 1):
            e_np1 = np.sqrt(((n + 1) ** 2 - m ** 2) / (4 * (n + 1) ** 2 - 1))
            term = -n * e_np1 * P[m, n + 1]
            if n > m:
                e_n = np.sqrt((n ** 2 - m ** 2) / (4 * n ** 2 - 1))
                term = term + (n + 1) * e_n * P[m, n - 1]
            H[m, n] = term
    return P, H


class Sphere:
    """A truncated spherical-harmonic basis and its Gaussian grid."""

    def __init__(self, trunc=42, radius=RADIUS, omega=OMEGA):
        self.trunc = T = int(trunc)
        self.radius = float(radius)
        self.omega = float(omega)

        nlat = int(np.ceil((3 * T + 1) / 2))
        if nlat % 2:
            nlat += 1
        nlon = 1
        while nlon < 3 * T + 1:
            nlon *= 2                      # power of two keeps the FFT fast
        self.nlat, self.nlon = nlat, nlon

        mu, w = np.polynomial.legendre.leggauss(nlat)
        self.mu, self.gauss_w = mu, w
        self.lat = np.arcsin(mu)
        self.lon = 2 * np.pi * np.arange(nlon) / nlon
        # column vector so it broadcasts against grid fields (nlat, nlon)
        self.coslat2 = (1.0 - mu ** 2)[:, None]            # cos^2(lat)

        P, H = legendre_basis(mu, T)
        self.P = P[:T + 1, :T + 1]
        self.H = H[:T + 1, :T + 1]

        m = np.arange(T + 1)
        n = np.arange(T + 1)
        self.m2d, self.n2d = np.meshgrid(m, n, indexing="ij")
        self.mask = self.n2d >= self.m2d                   # triangular
        self.im = 1j * self.m2d * self.mask

        # -Laplacian eigenvalue n(n+1)/a^2, and the inverse Laplacian
        nn = self.n2d * (self.n2d + 1)
        self.lap = -nn / self.radius ** 2
        with np.errstate(divide="ignore", invalid="ignore"):
            self.invlap_a = np.where(nn > 0, self.radius / np.maximum(nn, 1), 0.0)
        self.coriolis = 2 * self.omega * mu[:, None] * np.ones(nlon)

    # ---------------------------------------------------------------- shapes
    @property
    def spec_shape(self):
        return (self.trunc + 1, self.trunc + 1)

    @property
    def grid_shape(self):
        return (self.nlat, self.nlon)

    def zeros_spec(self, batch=()):
        return np.zeros(tuple(batch) + self.spec_shape, dtype=complex)

    # ------------------------------------------------------------ transforms
    def _fourier(self, f):
        """Grid -> Fourier coefficients F(m, mu), m = 0..T, batch-aware."""
        Fm = np.fft.rfft(f, axis=-1)[..., :self.trunc + 1] / self.nlon
        return np.moveaxis(Fm, -1, -2)                     # (..., m, k)

    def _inv_fourier(self, Fm):
        """Fourier coefficients F(m, mu) -> grid, batch-aware."""
        Fm = np.moveaxis(Fm, -1, -2)                       # (..., k, m)
        pad = np.zeros(Fm.shape[:-1] + (self.nlon // 2 + 1,), dtype=complex)
        pad[..., :self.trunc + 1] = Fm * self.nlon
        return np.fft.irfft(pad, n=self.nlon, axis=-1)

    def _legendre_apply(self, basis, data, adjoint):
        """The Legendre half of a transform, as a batched matrix product.

        Per zonal wavenumber m this is a dense (n, k) matrix on the
        batch, so np.matmul hands it to BLAS rather than einsum's
        generic loop - what makes an ensemble affordable on a laptop.
        """
        lead = data.shape[:-2]
        d = data.reshape((-1,) + data.shape[-2:])          # (B, m, X)
        d = np.ascontiguousarray(np.moveaxis(d, 0, 1))     # (m, B, X)
        mat = np.swapaxes(basis, 1, 2) if adjoint else basis
        out = np.moveaxis(np.matmul(d, mat), 1, 0)         # (B, m, Y)
        return out.reshape(lead + out.shape[1:])

    def analyse(self, f, basis=None):
        """Grid field -> spectral coefficients (default basis Pbar)."""
        basis = self.P if basis is None else basis
        Fm = self._fourier(f) * self.gauss_w
        return 0.5 * self._legendre_apply(basis, Fm, True) * self.mask

    def analyse_H(self, f):
        """Analyse against H, used for the meridional-derivative terms."""
        return self.analyse(f, basis=self.H)

    def synth(self, coef, basis=None):
        """Spectral coefficients -> grid field (default basis Pbar)."""
        basis = self.P if basis is None else basis
        Fm = self._legendre_apply(basis, coef * self.mask, False)
        return self._inv_fourier(Fm)

    def synth_H(self, coef):
        return self.synth(coef, basis=self.H)

    # -------------------------------------------------------------- calculus
    def uv_from_vortdiv(self, zeta, div):
        """Return U = u cos(lat), V = v cos(lat) on the grid.

        u = -(1/a) dpsi/dphi + (1/(a cos)) dchi/dlambda
        v =  (1/(a cos)) dpsi/dlambda + (1/a) dchi/dphi
        with psi = inverse-Laplacian(zeta), chi = inverse-Laplacian(div).
        """
        wz = self.invlap_a * zeta
        wd = self.invlap_a * div
        U = self.synth_H(wz) + self.synth(-self.im * wd)
        V = self.synth(-self.im * wz) + self.synth_H(-wd)
        return U, V

    def vortdiv_from_uv(self, U, V):
        """Inverse of uv_from_vortdiv: U, V on the grid -> zeta, div.

        Vorticity is the curl of the wind and divergence is its
        divergence, so both come from the same two flux operators below
        with the flux set to the wind itself.
        """
        return self.curl_of_flux(U, V), self.divergence_of_flux(U, V)

    def divergence_of_flux(self, A, B):
        """Spectral div of a flux whose components are A = F_lambda cos,
        B = F_phi cos, i.e. (1/(a(1-mu^2))) dA/dlambda + (1/a) dB/dmu."""
        a = self.radius
        return ((self.im / a) * self.analyse(A / self.coslat2)
                - (1.0 / a) * self.analyse_H(B / self.coslat2))

    def curl_of_flux(self, A, B):
        """Spectral vertical curl of the same flux:
        (1/(a(1-mu^2))) dB/dlambda - (1/a) dA/dmu."""
        a = self.radius
        return ((self.im / a) * self.analyse(B / self.coslat2)
                + (1.0 / a) * self.analyse_H(A / self.coslat2))

    # ------------------------------------------------------------- utilities
    def global_mean(self, f):
        """Area-weighted global mean of a grid field."""
        w = self.gauss_w / (2.0 * self.nlon)
        return np.einsum("...kj,k->...", f, w)

    def spectrum(self, coef):
        """Total power per total wavenumber n (m>0 counted twice)."""
        p = np.abs(coef) ** 2 * self.mask
        p = p[..., 0, :] + 2.0 * p[..., 1:, :].sum(axis=-2)
        return p
