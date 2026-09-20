"""A global shallow-water model on the rotating sphere.

The shallow-water equations are Navier-Stokes for a rotating fluid
after four reductions: hydrostatic balance, one constant-density layer,
incompressibility, and molecular viscosity replaced by scale-selective
hyperdiffusion. Gone: vertical structure, thermodynamics, moisture,
convection. Left: nonlinear vorticity advection on a rotating sphere,
Rossby waves, and the gravity waves that balance mass against wind.

This is the system of the first numerical forecast (Charney, Fjortoft
and von Neumann, ENIAC, 1950) and the standard dynamical-core test bed
(Williamson et al. 1992, J. Comput. Phys. 102, 211-224).

It is NOT a forecast model - one layer with no thermodynamics produces
no temperature, rain or gust, so nothing this project prices. What it
can settle is how fast a small initial error grows, which no amount of
extra physics would improve.

Prognostic form:
    dzeta/dt = -div[(zeta+f) v]
    ddiv/dt  =  curl[(zeta+f) v] - laplacian(Phi + (u^2+v^2)/2)
    dPhi/dt  = -div[Phi v]

Products are formed on the grid and transformed back. Time stepping is
RK4 on the nonlinear terms, then an exact integrating factor for the
hyperdiffusion.
"""

import numpy as np

from .spectral import GRAVITY, OMEGA, RADIUS, Sphere


class ShallowWater:
    """Spectral shallow-water dynamical core."""

    def __init__(self, sphere=None, trunc=42, damping_hours=12.0,
                 damping_order=2):
        self.sph = sphere if sphere is not None else Sphere(trunc)
        s = self.sph
        self.damping_order = int(damping_order)
        self.damping_hours = float(damping_hours)

        # Damping as an e-folding time at the truncation limit, not a
        # diffusivity, so the number means the same at every resolution.
        nn = s.n2d * (s.n2d + 1.0)
        nmax = s.trunc * (s.trunc + 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            shape = np.where(nn > 0, (nn / nmax) ** self.damping_order, 0.0)
        self.damp_rate = shape / (self.damping_hours * 3600.0)

    # ------------------------------------------------------------ tendencies
    def tendencies(self, zeta, div, phi):
        s = self.sph
        zeta_g = s.synth(zeta)
        phi_g = s.synth(phi)
        U, V = s.uv_from_vortdiv(zeta, div)

        abs_vort = zeta_g + s.coriolis
        A = abs_vort * U
        B = abs_vort * V

        # kinetic energy per unit mass; u = U/cos, v = V/cos
        K = 0.5 * (U ** 2 + V ** 2) / s.coslat2

        dzeta = -s.divergence_of_flux(A, B)
        ddiv = s.curl_of_flux(A, B) - s.lap * s.analyse(phi_g + K)
        dphi = -s.divergence_of_flux(phi_g * U, phi_g * V)
        return dzeta, ddiv, dphi

    # --------------------------------------------------------------- stepping
    def step(self, state, dt):
        """One RK4 step plus the diffusion integrating factor."""
        z, d, p = state

        k1 = self.tendencies(z, d, p)
        k2 = self.tendencies(*[a + 0.5 * dt * b for a, b in zip(state, k1)])
        k3 = self.tendencies(*[a + 0.5 * dt * b for a, b in zip(state, k2)])
        k4 = self.tendencies(*[a + dt * b for a, b in zip(state, k3)])
        out = [a + (dt / 6.0) * (b + 2 * c + 2 * e + f)
               for a, b, c, e, f in zip(state, k1, k2, k3, k4)]

        decay = np.exp(-self.damp_rate * dt)
        out[0] = out[0] * decay
        out[1] = out[1] * decay
        return tuple(out)

    def run(self, state, days, dt, sample_hours=6.0, callback=None,
            progress=None):
        """Integrate, calling `callback(t_hours, state)` on each sample."""
        nsteps = int(round(days * 86400.0 / dt))
        every = max(1, int(round(sample_hours * 3600.0 / dt)))
        if callback is not None:
            callback(0.0, state)
        for i in range(1, nsteps + 1):
            state = self.step(state, dt)
            if not np.all(np.isfinite(state[0])):
                raise FloatingPointError(
                    f"model blew up at step {i} (t = {i * dt / 3600:.1f} h) - "
                    f"reduce dt (currently {dt:g} s)")
            if callback is not None and i % every == 0:
                callback(i * dt / 3600.0, state)
            if progress and i % (every * progress) == 0:
                print(f"    t = {i * dt / 86400:6.2f} d", flush=True)
        return state

    # ------------------------------------------------------------ diagnostics
    def diagnostics(self, state):
        """Mass, total energy and potential enstrophy - the three
        quantities the continuous equations conserve exactly."""
        s = self.sph
        zeta, div, phi = state
        zeta_g = s.synth(zeta)
        phi_g = s.synth(phi)
        U, V = s.uv_from_vortdiv(zeta, div)
        ke = 0.5 * phi_g * (U ** 2 + V ** 2) / s.coslat2
        pe = 0.5 * phi_g ** 2
        q = (zeta_g + s.coriolis) ** 2 / np.maximum(phi_g, 1e-6)
        return {
            "mass": float(s.global_mean(phi_g)),
            "energy": float(s.global_mean(ke + pe)),
            "enstrophy": float(s.global_mean(0.5 * q)),
        }

    def wind(self, state):
        """True u, v in m/s on the grid (undoing the cos(lat) factor)."""
        s = self.sph
        U, V = s.uv_from_vortdiv(state[0], state[1])
        c = np.sqrt(s.coslat2)
        return U / c, V / c

    def max_wind(self, state):
        u, v = self.wind(state)
        return float(np.max(np.sqrt(u ** 2 + v ** 2)))

    def courant_dt(self, phibar, safety=0.6):
        """Largest stable explicit step, set by the fastest gravity wave
        against the smallest resolved wavelength."""
        s = self.sph
        c = np.sqrt(max(phibar, 1.0))
        kmax = np.sqrt(s.trunc * (s.trunc + 1.0)) / s.radius
        return safety * 2.0 / (c * kmax)


# ------------------------------------------------------------------ test cases
def williamson_case2(sph, u0=None, phi0=2.94e4, alpha=0.0):
    """Williamson test case 2: steady-state nonlinear zonal geostrophic
    flow.  The exact solution is the initial state for all time, so any
    departure is entirely the numerics' fault.  This is the strongest
    check a shallow-water core gets."""
    if u0 is None:
        u0 = 2 * np.pi * sph.radius / (12 * 86400.0)
    lat = sph.lat[:, None]
    lon = sph.lon[None, :]
    coslat = np.cos(lat)
    sinlat = np.sin(lat)

    u = u0 * (coslat * np.cos(alpha) + sinlat * np.cos(lon) * np.sin(alpha))
    v = -u0 * np.sin(lon) * np.sin(alpha)
    term = (sinlat * np.cos(alpha) - coslat * np.cos(lon) * np.sin(alpha))
    phi = phi0 - (sph.radius * sph.omega * u0 + 0.5 * u0 ** 2) * term ** 2

    zeta, div = sph.vortdiv_from_uv(u * coslat, v * coslat)
    return zeta, div, sph.analyse(phi)


def williamson_case6(sph, omega_rh=7.848e-6, K=7.848e-6, R=4, h0=8000.0):
    """Williamson test case 6: Rossby-Haurwitz wave 4.  An analytic
    solution of the nondivergent barotropic equation, and a standard
    dynamic test - the wave should travel east keeping its shape for a
    fortnight before shallow-water divergence slowly distorts it."""
    a, Om, g = sph.radius, sph.omega, GRAVITY
    lat = sph.lat[:, None]
    lon = sph.lon[None, :]
    c, s_ = np.cos(lat), np.sin(lat)

    u = a * omega_rh * c + a * K * c ** (R - 1) * (R * s_ ** 2 - c ** 2) * np.cos(R * lon)
    v = -a * K * R * c ** (R - 1) * s_ * np.sin(R * lon)

    A = (omega_rh / 2 * (2 * Om + omega_rh) * c ** 2
         + 0.25 * K ** 2 * c ** (2 * R)
         * ((R + 1) * c ** 2 + (2 * R ** 2 - R - 2) - 2 * R ** 2 * c ** -2))
    B = (2 * (Om + omega_rh) * K / ((R + 1) * (R + 2)) * c ** R
         * ((R ** 2 + 2 * R + 2) - (R + 1) ** 2 * c ** 2))
    C = 0.25 * K ** 2 * c ** (2 * R) * ((R + 1) * c ** 2 - (R + 2))
    phi = g * h0 + a ** 2 * (A + B * np.cos(R * lon) + C * np.cos(2 * R * lon))

    zeta, div = sph.vortdiv_from_uv(u * c, v * c)
    return zeta, div, sph.analyse(phi)


def state_from_wind(sph, u, v, phi):
    """Build a model state from grid-space u, v (m/s) and geopotential."""
    c = np.sqrt(sph.coslat2)
    zeta, div = sph.vortdiv_from_uv(u * c, v * c)
    return zeta, div, sph.analyse(phi)


def balanced_geopotential(sph, zeta, phibar):
    """Solve the linear balance equation for the mass field that goes
    with a given nondivergent wind.

    Geostrophy is f k x v = -grad(Phi); taking the divergence of both
    sides with v = k x grad(psi) gives

        laplacian(Phi) = div( f grad(psi) ),   grad(psi) = (v, -u)

    which is an exact, well-posed elliptic problem in spectral space
    because the Laplacian is diagonal there.  Starting a one-layer model
    from an unbalanced state instead launches gravity waves of the same
    amplitude as the weather, which is what makes real initialisation a
    field of its own.

    `phibar` sets the layer's mean geopotential, i.e. its gravity-wave
    speed; the balance equation fixes only the departures from it.
    """
    U, V = sph.uv_from_vortdiv(zeta, np.zeros_like(zeta))
    f = sph.coriolis
    rhs = sph.divergence_of_flux(f * V, -f * U)
    phi = np.zeros_like(rhs)
    nz = sph.lap != 0
    phi[..., nz] = rhs[..., nz] / sph.lap[nz]
    phi[..., 0, 0] = phibar          # the n=0 mode is the layer depth
    return phi


def observed_shallow_water_state(sph, when, level_hpa=500, phibar=None,
                                 verbose=True):
    """A balanced model state built from observed winds at one level.

    Returns (state, info).  `phibar` defaults to g times the observed
    global-mean geopotential height at that level, so the model's
    gravity-wave speed is the one that level implies.
    """
    from .fetch_initial import observed_state

    u, v, z, stamp = observed_state(sph, when, level_hpa=level_hpa,
                                    verbose=verbose)
    c = np.sqrt(sph.coslat2)
    zeta, _ = sph.vortdiv_from_uv(u * c, v * c)
    div = np.zeros_like(zeta)
    zmean = float(sph.global_mean(z))
    if phibar is None:
        phibar = GRAVITY * zmean
    phi = balanced_geopotential(sph, zeta, phibar)
    info = {
        "time": stamp,
        "level_hpa": level_hpa,
        "mean_height_m": zmean,
        "phibar": float(phibar),
        "gravity_wave_speed": float(np.sqrt(phibar)),
        "max_wind": float(np.max(np.sqrt(u ** 2 + v ** 2))),
        "rms_wind": float(np.sqrt(sph.global_mean(u ** 2 + v ** 2))),
    }
    return (zeta, div, phi), info
