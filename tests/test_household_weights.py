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
