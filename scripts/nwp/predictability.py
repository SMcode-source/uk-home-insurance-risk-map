"""How long is a weather forecast good for? Measured, not asserted.

Lorenz's experiment (1969, Tellus 21, 289-307). Take a real
atmospheric state, integrate it, then integrate it again from a start
differing by an amount too small to observe. Both runs obey the same
equations exactly, so any divergence is the pure sensitivity of the
equations to their starting point.

Two numbers come out - a doubling time, and the ceiling the error
grows to (how different two unrelated days are). Together they bound
the useful range of any forecast made by integrating these equations,
at any resolution, on any computer.

    python -u scripts/nwp/predictability.py --days 20
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from nwp.spectral import Sphere
    from nwp.shallow_water import ShallowWater, observed_shallow_water_state
    from nwp.fetch_initial import observed_state
else:
    from .spectral import Sphere
    from .shallow_water import ShallowWater, observed_shallow_water_state
    from .fetch_initial import observed_state

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def rms_wind(sph, u, v):
    return np.sqrt(sph.global_mean(u ** 2 + v ** 2))


def make_perturbations(sph, control_zeta, amplitudes, members, seed=20260910):
    """Perturbations shaped like the flow they perturb.

    White noise would sit at the truncation limit, where the filter
    removes it, and would flatter the model by growing slowly. Each
    perturbation instead takes the control's own vorticity spectrum,
    rescaled to a target RMS wind error.
    """
    rng = np.random.default_rng(seed)
    power = sph.spectrum(control_zeta)                 # per total wavenumber n
    shape = np.sqrt(np.maximum(power, 0.0))
    shape = shape / max(shape.max(), 1e-30)

    out, labels = [], []
    for amp in amplitudes:
        for k in range(members):
            r = (rng.normal(size=sph.spec_shape)
                 + 1j * rng.normal(size=sph.spec_shape))
            r = r * shape[None, :] * sph.mask
            r[0] = r[0].real                            # keep the field real
            r[:, 0] = 0                                 # no change to the mean
            U, V = sph.uv_from_vortdiv(r, np.zeros_like(r))
            c = np.sqrt(sph.coslat2)
            scale = amp / max(float(rms_wind(sph, U / c, V / c)), 1e-30)
            out.append(r * scale)
            labels.append((amp, k))
    return out, labels


def saturation_level(sph, date_a, date_b, level_hpa=500, verbose=True):
    """How different are two unrelated days?  This is the ceiling any
    error growth runs into: once a forecast is this wrong, it is no
    better than picking a day out of the archive at random."""
    ua, va, _, ta = observed_state(sph, date_a, level_hpa, verbose=verbose)
    ub, vb, _, tb = observed_state(sph, date_b, level_hpa, verbose=verbose)
    return float(rms_wind(sph, ua - ub, va - vb)), ta, tb


def fit_doubling_time(hours, err, lo, hi):
    """Least-squares exponential fit over the window where growth is
    genuinely exponential: above the noise, below saturation."""
    h, e = np.asarray(hours, float), np.asarray(err, float)
    sel = (e > lo) & (e < hi) & np.isfinite(e) & (e > 0)
    if sel.sum() < 4:
        return None, None, int(sel.sum())
    slope, _ = np.polyfit(h[sel], np.log(e[sel]), 1)
    if slope <= 0:
        return None, None, int(sel.sum())
    return float(np.log(2.0) / slope / 24.0), float(slope), int(sel.sum())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trunc", type=int, default=42,
                    help="spectral truncation (T42 ~ 300 km, the classic)")
    ap.add_argument("--days", type=float, default=40.0)
    ap.add_argument("--dt", type=float, default=600.0)
    ap.add_argument("--date", default="2026-01-15T12:00",
                    help="analysis time for the initial state")
    ap.add_argument("--compare-date", default="2026-02-15T12:00",
                    help="an unrelated day, for the saturation level")
    ap.add_argument("--level", type=int, default=500)
    ap.add_argument("--members", type=int, default=3)
    ap.add_argument("--amplitudes", default="0.001,0.01,0.1,1.0",
                    help="initial RMS wind errors, m/s")
    ap.add_argument("--damping-hours", type=float, default=12.0)
    ap.add_argument("--sample-hours", type=float, default=6.0)
    ap.add_argument("--out", default=os.path.join(ROOT, "data",
                                                  "nwp_predictability.json"))
    args = ap.parse_args(argv)

    amps = [float(x) for x in args.amplitudes.split(",")]
    sph = Sphere(args.trunc)
    model = ShallowWater(sph, damping_hours=args.damping_hours)

    print(f"T{args.trunc} shallow water on a {sph.nlat}x{sph.nlon} Gaussian "
          f"grid; dt = {args.dt:g} s", flush=True)
    print("initial state:", flush=True)
    control, info = observed_shallow_water_state(sph, args.date,
                                                 level_hpa=args.level)
    dt_max = model.courant_dt(info["phibar"])
    print(f"  {info['time']} at {info['level_hpa']} hPa; "
          f"mean height {info['mean_height_m']:.0f} m, "
          f"gravity-wave speed {info['gravity_wave_speed']:.0f} m/s",
          flush=True)
    print(f"  observed wind: rms {info['rms_wind']:.1f} m/s, "
          f"max {info['max_wind']:.1f} m/s", flush=True)
    print(f"  largest stable step {dt_max:.0f} s (using {args.dt:g})", flush=True)
    if args.dt > dt_max:
        raise SystemExit(f"dt {args.dt} exceeds the stability limit {dt_max:.0f}")

    print("\nsaturation level (two unrelated days):", flush=True)
    sat, ta, tb = saturation_level(sph, args.date, args.compare_date, args.level)
    print(f"  rms wind difference {ta} vs {tb}: {sat:.2f} m/s", flush=True)

    perts, labels = make_perturbations(sph, control[0], amps, args.members)
    nmem = len(perts)
    print(f"\n{nmem} perturbed members "
          f"({args.members} at each of {amps}) plus the control", flush=True)

    batch = []
    for arr, pert in ((control[0], True), (control[1], False), (control[2], False)):
        stack = [arr] + [arr + p if pert else arr.copy() for p in perts]
        batch.append(np.stack(stack))
    state = tuple(batch)

    hours, errs = [], []
    diags = []

    def record(t, st):
        u, v = model.wind(st)
        du = u[1:] - u[:1]
        dv = v[1:] - v[:1]
        e = np.sqrt(sph.global_mean(du ** 2 + dv ** 2))
        hours.append(t)
        errs.append(e.tolist())
        d = model.diagnostics(tuple(a[0] for a in st))
        diags.append(d)
        if int(t) % 240 == 0:
            spread = " ".join(f"{x:.3g}" for x in e[::args.members])
            print(f"    t = {t / 24:5.1f} d   rms error by amplitude: {spread}",
                  flush=True)

    t0 = datetime.now()
    model.run(state, days=args.days, dt=args.dt,
              sample_hours=args.sample_hours, callback=record)
    print(f"\nintegration took {(datetime.now() - t0).total_seconds() / 60:.1f} min",
          flush=True)

    hours = np.array(hours)
    errs = np.array(errs)                                # (time, member)

    d0, dN = diags[0], diags[-1]
    print("conservation over the run (control member):", flush=True)
    for k in ("mass", "energy", "enstrophy"):
        print(f"  {k:10s} {dN[k] / d0[k] - 1:+.3e} relative change", flush=True)

    print("\nerror growth by initial amplitude:", flush=True)
    results = []
    for i, amp in enumerate(amps):
        cols = [j for j, (a, _) in enumerate(labels) if a == amp]
        e = errs[:, cols].mean(axis=1)
        dbl, rate, npts = fit_doubling_time(hours, e, 2 * amp, 0.35 * sat)
        # time to reach half of saturation: a forecast this wrong is
        # no longer telling you anything about the day in question
        half = sat / 2.0
        idx = np.argmax(e >= half) if (e >= half).any() else -1
        t_half = hours[idx] / 24.0 if idx > 0 else None
        results.append({
            "initial_rms_error_ms": amp,
            "doubling_time_days": dbl,
            "fit_points": npts,
            "days_to_half_saturation": t_half,
            "final_error_ms": float(e[-1]),
            "final_fraction_of_saturation": float(e[-1] / sat),
        })
        dbl_s = f"{dbl:.2f} d" if dbl else "  n/a"
        th_s = f"{t_half:5.1f} d" if t_half else "  >run"
        print(f"  start {amp:>7.3g} m/s -> doubling {dbl_s}, "
              f"half-saturation at {th_s}, "
              f"end {e[-1]:.2f} m/s ({100 * e[-1] / sat:.0f}% of saturation)",
              flush=True)

    good = [r for r in results if r["doubling_time_days"]]
    dbl_mean = float(np.mean([r["doubling_time_days"] for r in good])) if good else None

    print("\nwhat that implies for a one-year forecast:", flush=True)
    if dbl_mean:
        n_doublings = 365.0 / dbl_mean
        needed = sat / 2.0 / (2.0 ** n_doublings)
        print(f"  mean doubling time {dbl_mean:.2f} days", flush=True)
        print(f"  365 days is {n_doublings:.0f} doublings", flush=True)
        print(f"  to still be useful at one year, the initial state would "
              f"have to be known to {needed:.3g} m/s", flush=True)
        print("  (the wind is observed to about 1 m/s, and molecular "
              "thermal motion alone is far larger than that number)",
              flush=True)

    out = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "model": {
            "equations": "shallow water on the rotating sphere, "
                         "vorticity-divergence spectral form",
            "truncation": args.trunc,
            "grid": [sph.nlat, sph.nlon],
            "dt_seconds": args.dt,
            "damping_hours": args.damping_hours,
            "days": args.days,
        },
        "initial_state": info,
        "saturation_rms_ms": sat,
        "saturation_pair": [ta, tb],
        "conservation": {k: dN[k] / d0[k] - 1 for k in
                         ("mass", "energy", "enstrophy")},
        "mean_doubling_time_days": dbl_mean,
        "results": results,
        "hours": hours.tolist(),
        "rms_error_by_member": errs.tolist(),
        "member_labels": [{"amplitude": a, "member": k} for a, k in labels],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nwrote {args.out}", flush=True)
    return out


if __name__ == "__main__":
    main()
