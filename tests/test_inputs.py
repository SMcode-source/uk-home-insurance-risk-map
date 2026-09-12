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


# An AREA-basis depth table is two independent rasterisations - the five
# depth layers and the extent layer, each painted at 13 m/px - so a unit
# can carry a deepest-band share slightly above the envelope it is
# conditioned on. That is rounding between two renderings, not a wrong
# table, and _band_shares already absorbs it by raising the envelope to
# the band. How big it gets depends on the GRAIN, because the same
# absolute rasterisation error is a larger share of a smaller polygon:
# counting only overshoots past half a point, districts show 0 rows out
# of 5,472 (the largest is 0.29 pp) and sectors 38 out of 20,796, the
# largest 14.7 pp (HANDOFF 2026-09-12). A single absolute tolerance
# therefore cannot be right at both grains. What IS the same at both is
# that the disagreement stays RARE: a table built against different
# geometry would not overshoot in a fifth of a percent of rows, it would
# overshoot everywhere. So the guard is on the rate, with a ceiling on
# any one row to catch a table that is wrong in a different way.
OVERSHOOT_RATE = 0.01        # districts 0.00%, sectors 0.18%
OVERSHOOT_MAX = 0.25         # districts 0.0029, sectors 0.147
OVERSHOOT_IGNORE = 0.005     # below this it is not worth counting


@pytest.mark.parametrize("suffix", ["", "_cc"])
def test_depth_bands_nest_and_sit_inside_the_envelope(suffix):
    depth, cols = _read(f"sw_depth{suffix}.csv")
    env, _ = _read(f"sw_fractions{suffix}.csv")
    basis = {r.get("basis", "area") for r in depth.values()}
    assert len(basis) == 1, f"mixed basis in sw_depth{suffix}.csv: {basis}"
    area_basis = basis == {"area"}
    if area_basis and os.path.exists(
            os.path.join(DATA, f"sw_fractions_area{suffix}.csv")):
        # the depth layers are area measurements; condition them on the
        # area-share envelope, not the postcode-share one the frequency
        # uses (scores_real.sw_depth_severity does the same)
        env, _ = _read(f"sw_fractions_area{suffix}.csv")

    rows = over = 0
    worst = (0.0, None)
    for name, r in depth.items():
        for band in ("high", "low"):
            vals = [float(r[f"{c}_{band}"]) for c in DEPTH_COLS]
            for a, b in zip(vals, vals[1:]):
                assert b <= a + TOL, f"{name} {band}: depth bands do not nest {vals}"
            if name not in env:
                continue
            rows += 1
            cap = float(env[name][f"sw_{band}"])
            excess = vals[0] - cap
            if not area_basis:
                # a postcode table is sampled once, against one envelope,
                # so there is no second rasterisation to disagree with
                assert excess <= TOL, (
                    f"{name} {band}: deepest-band share {vals[0]} exceeds the "
                    f"envelope {cap} it is conditioned on")
                continue
            if excess > OVERSHOOT_IGNORE:
                over += 1
                worst = max(worst, (excess, f"{name} {band}"))

    if area_basis and rows:
        rate = over / rows
        assert rate <= OVERSHOOT_RATE, (
            f"{over} of {rows} rows ({100 * rate:.2f}%) have a deepest-band "
            f"share above their envelope - rasterisation noise is rare, so "
            f"this reads as a depth table built against different geometry "
            f"than sw_fractions_area{suffix}.csv")
        assert worst[0] <= OVERSHOOT_MAX, (
            f"{worst[1]} overshoots its envelope by {worst[0]:.3f}, past "
            f"anything two 13 m/px rasterisations of the same polygon can "
            f"disagree by")


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
