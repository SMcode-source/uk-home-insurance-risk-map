"""Guards on the household weighting of the postcode-share flood fractions
(fetch_flood_postcodes.weighted_counts / WEIGHT_BY_HOUSEHOLDS).

A unit's share is of its homes: each postcode weighs its Census
households. These pin that the weighted count is what the shrinkage
downstream expects (n times the household-weighted share), that a unit
with no households keeps its postcode count, that nesting survives, and
that switching the weighting off gives back the plain postcode counts
the published tables were built on.
"""
import importlib.util
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_spec = importlib.util.spec_from_file_location(
    "fetch_flood_postcodes",
    os.path.join(ROOT, "scripts", "fetch_flood_postcodes.py"))
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)

COLS = ["in_high", "in_low"]


def frame():
    # unit A: a flooded 1-household postcode and a dry 9-household one;
    # unit B: two business postcodes, one flooded, no households at all
    return (pd.DataFrame({"unit": ["A", "A", "B", "B"],
                          "in_high": [1, 0, 1, 0],
                          "in_low": [1, 1, 1, 0]}),
            np.array([1.0, 9.0, 0.0, 0.0]))


def test_the_share_is_of_homes_not_postcodes(monkeypatch):
    monkeypatch.setattr(fp, "WEIGHT_BY_HOUSEHOLDS", True)
    df, w = frame()
    got = fp.weighted_counts(df, "unit", COLS, w)
    assert got.loc["A", "n"] == 2
    # 1 of 10 households flooded: the count is n x 0.1
    assert np.isclose(got.loc["A", "in_high"], 0.2)
    assert np.isclose(got.loc["A", "in_low"], 2.0)


def test_a_unit_with_no_households_keeps_its_postcode_count(monkeypatch):
    monkeypatch.setattr(fp, "WEIGHT_BY_HOUSEHOLDS", True)
    df, w = frame()
    got = fp.weighted_counts(df, "unit", COLS, w)
    assert got.loc["B", "in_high"] == 1 and got.loc["B", "in_low"] == 1


def test_nesting_survives_the_weighting(monkeypatch):
    monkeypatch.setattr(fp, "WEIGHT_BY_HOUSEHOLDS", True)
    rng = np.random.default_rng(0)
    n = 400
    low = rng.random(n) < 0.3
    high = low & (rng.random(n) < 0.5)
    top = high & (rng.random(n) < 0.5)
    df = pd.DataFrame({"unit": rng.integers(0, 20, n), "in_high": high,
                       "in_low": low, "in_top": top})
    w = rng.integers(0, 40, n).astype(float)
    got = fp.weighted_counts(df, "unit", ["in_high", "in_low", "in_top"], w)
    assert (got.in_top <= got.in_high + 1e-9).all()
    assert (got.in_high <= got.in_low + 1e-9).all()


def test_off_gives_the_plain_postcode_counts(monkeypatch):
    monkeypatch.setattr(fp, "WEIGHT_BY_HOUSEHOLDS", False)
    df, w = frame()
    got = fp.weighted_counts(df, "unit", COLS, w)
    assert got.loc["A", "in_high"] == 1 and got.loc["A", "in_low"] == 2


def test_scotland_carries_englands_high_share_of_homes(monkeypatch):
    monkeypatch.setattr(fp, "WEIGHT_BY_HOUSEHOLDS", True)
    country = np.array(["England", "England", "Scotland", "Wales"])
    in_high = np.array([1, 1, 1, 1])
    in_top = np.array([1.0, 0.0, 0.0, 1.0])
    # England: the High postcode holds 1 household, the Medium one 3, so
    # a quarter of zone homes are High though half the zone postcodes are
    top = fp.top_with_scotland(country, in_high, in_top, np.array([1, 3, 5, 5]))
    assert np.isclose(top[2], 0.25)
    assert top[0] == 1 and top[1] == 0 and top[3] == 1
    # unweighted, the postcode share
    assert np.isclose(fp.top_with_scotland(country, in_high, in_top)[2], 0.5)


def test_a_households_depth_table_conditions_on_the_callers_envelope(
        tmp_path, monkeypatch):
    """basis = "households" must be read like "postcode" - conditioned on
    the caller's own envelope - and never fall into the area branch,
    which would divide by sw_fractions_area.csv whenever it exists."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import scores_real as sr
    head = ("name,d02_high,d02_low,d03_high,d03_low,d06_high,d06_low,"
            "d09_high,d09_low,d12_high,d12_low,basis")
    body = ["SHALLOW,0.004,0.010,0.001,0.002,0.0,0.0,0.0,0.0,0.0,0.0,{b}",
            "DEEP,0.20,0.38,0.18,0.35,0.15,0.30,0.10,0.20,0.05,0.10,{b}"]
    (tmp_path / "country.csv").write_text(
        "name,country,share\nSHALLOW,England,1.0\nDEEP,England,1.0\n")
    # an area envelope ten times smaller: reading it would change the answer
    (tmp_path / "sw_fractions_area.csv").write_text(
        "name,sw_high,sw_low\nSHALLOW,0.001,0.002\nDEEP,0.02,0.04\n")
    monkeypatch.setattr(sr, "DATA", str(tmp_path))
    names = np.array(["SHALLOW", "DEEP"])
    hi, lo, hh = np.array([0.01, 0.20]), np.array([0.02, 0.40]), np.array([1e3, 1e3])
    got = {}
    for b in ("postcode", "households"):
        (tmp_path / "sw_depth.csv").write_text(
            "\n".join([head] + [r.format(b=b) for r in body]))
        got[b] = sr.sw_depth_severity(names, hi, lo, hh)[0]
    assert np.allclose(got["postcode"], got["households"])
