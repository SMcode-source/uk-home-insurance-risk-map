"""River/sea depth severity (scores_real.rs_depth_severity).

The river/sea leg carries its own depth-damage multiplier from the EA
RoFRS depth layers, built on the same core as surface water's. These
tests pin what is new: the multiplier touches the ZONE frequency only
(not the 0.05% background), it is conditioned on the depth file's own
envelope, it is England-only, and the climate run is expressed on the
present-day scale.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_model as bm  # noqa: E402
import scores_real as sr  # noqa: E402

HEADER = ("name,e_high,e_low,d02_high,d02_low,d03_high,d03_low,d06_high,"
          "d06_low,d09_high,d09_low,d12_high,d12_low,basis")


@pytest.fixture(autouse=True)
def _reset_reference():
    sr._RS_DEPTH_REF = None
    yield
    sr._RS_DEPTH_REF = None


def fields(**over):
    f = dict(sub=0.5, sub_rel=1.0, wx=0.5, f_high=0.1, f_low=0.2,
             sw_high=0.1, sw_low=0.2, gw_frac=0.1, sw_sev=1.0, rs_sev=1.0,
             er=0.0, th=0.009, eow=1.0, fire=0.002, ad=0.009,
             ct_th=1.0, ct_eow=1.0, ct_fire=1.0, ct_ad=1.0)
    f.update(over)
    return {k: np.array([v], dtype=float) for k, v in f.items()}


def _mu(**over):
    return float(bm.marginal_params(fields(**over))["sev_fl"]["mu"][0])


def test_rs_multiplier_raises_flood_severity_through_the_zone_only():
    assert _mu(rs_sev=1.8) > _mu(rs_sev=0.6)
    # outside every RoFRS band only the background remains, and it has no
    # mapped depth: the multiplier must not reach it
    assert abs(_mu(f_high=0.0, f_low=0.0, rs_sev=0.6)
               - _mu(f_high=0.0, f_low=0.0, rs_sev=1.8)) < 1e-12
    # the multiplier moves severity, never frequency
    a = bm.marginal_params(fields(rs_sev=0.6))
    b = bm.marginal_params(fields(rs_sev=1.8))
    assert np.array_equal(a["p_fl"], b["p_fl"])


def _write(tmp_path, rows, country):
    (tmp_path / "rs_depth.csv").write_text("\n".join([HEADER] + rows))
    (tmp_path / "country.csv").write_text(
        "name,country,share\n"
        + "".join(f"{n},{c},1.0\n" for n, c in country.items()))


def test_normalised_monotone_and_england_only(tmp_path, monkeypatch):
    _write(tmp_path, [
        # envelope 10%, half of it >=1%; almost none of it deep
        "SHALLOW,0.05,0.10,0.02,0.05,0.005,0.01,0.0,0.001,0.0,0.0,0.0,0.0,postcode",
        # same envelope, most of it over 0.6 m
        "DEEP,0.05,0.10,0.05,0.09,0.05,0.08,0.04,0.07,0.03,0.05,0.02,0.03,postcode",
        # no envelope at all -> flat
        "DRY,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,postcode",
        # zero-filled outside England, as the fetcher writes it
        "WELSH,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,postcode",
    ], {"SHALLOW": "England", "DEEP": "England", "DRY": "England",
        "WELSH": "Wales"})
    monkeypatch.setattr(sr, "DATA", str(tmp_path))
    names = np.array(["SHALLOW", "DEEP", "DRY", "WELSH"])
    hh = np.array([1000.0, 1000.0, 1000.0, 1000.0])
    mult, depth = sr.rs_depth_severity(names, hh)
    assert mult[1] > mult[0]
    assert depth[1] > depth[0]
    assert mult[2] == 1.0 and mult[3] == 1.0
    assert np.isnan(depth[3])
    assert abs(float(np.average(mult[:2], weights=hh[:2])) - 1.0) < 1e-9


def test_missing_file_is_flat(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "DATA", str(tmp_path))
    mult, depth = sr.rs_depth_severity(np.array(["A", "B"]),
                                       np.array([1.0, 1.0]))
    assert np.all(mult == 1.0) and np.all(np.isnan(depth))


def test_climate_is_on_the_present_day_scale(tmp_path, monkeypatch):
    """A uniformly deeper future must come out above 1.0, not be
    renormalised back to it."""
    _write(tmp_path, [
        "A,0.05,0.10,0.02,0.05,0.005,0.01,0.0,0.001,0.0,0.0,0.0,0.0,postcode",
        "B,0.05,0.10,0.03,0.06,0.01,0.02,0.005,0.01,0.0,0.0,0.0,0.0,postcode",
    ], {"A": "England", "B": "England"})
    (tmp_path / "rs_depth_cc.csv").write_text("\n".join([HEADER,
        "A,0.05,0.10,0.05,0.09,0.04,0.08,0.03,0.06,0.02,0.04,0.01,0.02,postcode",
        "B,0.05,0.10,0.05,0.10,0.05,0.09,0.04,0.08,0.03,0.06,0.02,0.04,postcode"]))
    monkeypatch.setattr(sr, "DATA", str(tmp_path))
    names, hh = np.array(["A", "B"]), np.array([1.0, 1.0])
    now, _ = sr.rs_depth_severity(names, hh)
    fut, _ = sr.rs_depth_severity(names, hh, climate=True)
    assert abs(now.mean() - 1.0) < 1e-9
    assert np.all(fut > now)
