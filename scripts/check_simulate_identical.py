"""Capture or compare a simulate() fingerprint, to prove an optimisation
changed nothing.

    python scripts/check_simulate_identical.py save <file.npz>
    python scripts/check_simulate_identical.py check <file.npz>

The copula sampler is the hot path and the obvious place to optimise, but
it is also the least forgiving: a reordered floating-point expression
shifts the last bit, which propagates through 20,000 simulated years into
premiums and rating groups. "The tests still pass" does not prove an
optimisation was neutral - the property tests have tolerances. This does:
it re-runs the real simulate() over a multi-batch frame and demands the
results match to the LAST BIT.

Deliberately multi-batch (200 districts at BATCH=80) so the per-batch RNG
offset, which is what makes the loop safe to parallelise, is exercised
rather than assumed.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm  # noqa: E402

N_DISTRICTS = 200
N_SIM = 2000
BATCH = 80


def fingerprint():
    rng = np.random.default_rng(1234)
    n = N_DISTRICTS
    df = pd.DataFrame({
        "sub_score": rng.uniform(0.05, 1.0, n),
        "wx_score": rng.uniform(0.05, 1.0, n),
        "fl_score": rng.uniform(0.0, 1.0, n),
        "gw_score": rng.uniform(0.0, 1.0, n),
        "er_score": rng.uniform(0.0, 0.8, n),
        "f_high": rng.uniform(0.0, 0.4, n),
        "f_low": rng.uniform(0.0, 0.6, n),
        "sw_high": rng.uniform(0.0, 0.3, n),
        "sw_low": rng.uniform(0.0, 0.5, n),
        "gw_frac": rng.uniform(0.0, 0.5, n),
        "sw_sev": rng.uniform(0.6, 2.5, n),
        "er_frac": rng.uniform(0.0, 0.05, n),
        "households": rng.uniform(200, 40000, n),
    })
    df["f_low"] = np.maximum(df["f_low"], df["f_high"])
    df["sw_low"] = np.maximum(df["sw_low"], df["sw_high"])

    n_sim, batch = bm.N_SIM, bm.BATCH
    bm.N_SIM, bm.BATCH = N_SIM, BATCH
    try:
        sim, year = bm.simulate(df)
    finally:
        bm.N_SIM, bm.BATCH = n_sim, batch
    out = {f"sim__{k}": np.asarray(v) for k, v in sim.items()}
    out.update({f"year__{k}": np.asarray(v) for k, v in year.items()})
    return out


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("save", "check"):
        raise SystemExit(__doc__)
    mode, path = sys.argv[1], sys.argv[2]
    got = fingerprint()

    if mode == "save":
        np.savez(path, **got)
        print(f"saved {len(got)} arrays -> {path}")
        return

    ref = np.load(path)
    missing = sorted(set(ref.files) - set(got))
    added = sorted(set(got) - set(ref.files))
    if missing or added:
        print(f"KEY MISMATCH  missing={missing}  added={added}")
        raise SystemExit(1)

    bad = []
    for k in sorted(got):
        a, b = ref[k], got[k]
        if a.shape != b.shape:
            bad.append((k, "shape", a.shape, b.shape))
        elif not np.array_equal(a, b, equal_nan=True):
            d = np.abs(a.astype(float) - b.astype(float))
            bad.append((k, "value", float(np.nanmax(d)),
                        int((d > 0).sum())))
    if bad:
        print(f"NOT BIT-IDENTICAL: {len(bad)} of {len(got)} arrays differ")
        for k, kind, x, y in bad[:12]:
            print(f"  {k:24s} {kind}  max|d|={x}  n_diff={y}")
        raise SystemExit(1)
    print(f"BIT-IDENTICAL across all {len(got)} arrays "
          f"({N_DISTRICTS} districts x {N_SIM} years, {BATCH}/batch)")


if __name__ == "__main__":
    main()
