"""Guards on the committed hazard tables the model reads.

The postcode-share tables are built from ~1.4 million sampled points
with hierarchical shrinkage, and three things went wrong on the way to
the first depth-by-postcode build that no unit test of the decode
would have caught: depth bands that did not nest (antialiased edges),
depth shares above the surface-water envelope they are conditioned on,
and English priors leaking across the border because coverage was
keyed by postcode area instead of by `data/country.csv`. These tests
read the tables exactly as the model does and assert the identities
the severity code relies on, at whichever grain the checkout carries.
"""
import csv
import os

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")

DEPTH_COLS = ("d02", "d03", "d06", "d09", "d12")  # shallow -> deep
TOL = 1e-6


def _read(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} not present")
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["name"]: r for r in rows}, rows[0].keys() if rows else ()


def _country():
    with open(os.path.join(DATA, "country.csv"), newline="", encoding="utf-8") as fh:
        return {r["name"]: r["country"] for r in csv.DictReader(fh)}


@pytest.mark.parametrize("suffix", ["", "_cc"])
def test_depth_bands_nest_and_sit_inside_the_envelope(suffix):
    depth, cols = _read(f"sw_depth{suffix}.csv")
    env, _ = _read(f"sw_fractions{suffix}.csv")
    basis = {r.get("basis", "area") for r in depth.values()}
    assert len(basis) == 1, f"mixed basis in sw_depth{suffix}.csv: {basis}"
    tol = TOL
    if basis == {"area"}:
        # The area tables come from two rasterisations (13 m/px depth
        # layers against the envelope tiles), so the deepest band can
        # overshoot the envelope by rounding: EC4M by 0.29 pp in the
        # published tables. _band_shares raises the envelope to the band
        # (np.maximum.accumulate), so that is harmless; a postcode table
        # is sampled once and must be exact.
        tol = 0.005
        if os.path.exists(os.path.join(DATA, f"sw_fractions_area{suffix}.csv")):
            env, _ = _read(f"sw_fractions_area{suffix}.csv")
    for name, r in depth.items():
        for band in ("high", "low"):
            vals = [float(r[f"{c}_{band}"]) for c in DEPTH_COLS]
            for a, b in zip(vals, vals[1:]):
                assert b <= a + TOL, f"{name} {band}: depth bands do not nest {vals}"
            if name in env:
                cap = float(env[name][f"sw_{band}"])
                assert vals[0] <= cap + tol, (
                    f"{name} {band}: deepest-band share {vals[0]} exceeds the "
                    f"envelope {cap} it is conditioned on")


@pytest.mark.parametrize("suffix", ["", "_cc"])
def test_depth_by_postcode_is_zero_outside_england(suffix):
    depth, _ = _read(f"sw_depth{suffix}.csv")
    if {r.get("basis", "area") for r in depth.values()} != {"postcode"}:
        pytest.skip("area-share depth table: England-only coverage is by tile")
    country = _country()
    missing = [n for n in depth if n not in country]
    assert not missing, f"depth rows with no country: {missing[:5]}"
    leaked = [n for n, r in depth.items()
              if country[n] != "England"
              and any(float(r[f"{c}_{b}"]) > 0 for c in DEPTH_COLS for b in ("high", "low"))]
    assert not leaked, (
        f"{len(leaked)} units outside England carry a depth share (the EA "
        f"layers stop at the border; a nonzero value is a leaked prior): "
        f"{leaked[:8]}")


def test_present_and_climate_depth_tables_share_a_basis():
    a, _ = _read("sw_depth.csv")
    b, _ = _read("sw_depth_cc.csv")
    ba = {r.get("basis", "area") for r in a.values()}
    bb = {r.get("basis", "area") for r in b.values()}
    assert ba == bb, f"sw_depth.csv is {ba} but sw_depth_cc.csv is {bb}"
    assert set(a) == set(b)
