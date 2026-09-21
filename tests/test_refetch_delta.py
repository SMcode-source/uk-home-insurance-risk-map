"""Guards on the refetch size guard itself.

scripts/check_refetch_delta.py is the control that catches a refetch
which came back wrong in a way every shape test accepts. On 2026-09-21
it died partway through a real run:

    ok    sw_fractions.csv: ...
    ok    sw_fractions_cc.csv: ...
    ValueError: could not convert string to float: 'postcode'

sw_depth.csv gained a `basis` column at the 2026-09-20 publish and the
guard assumed every column but the key was a number. The failure mode
is worse than a crash: it had already passed the two tables it could
read, so a reader skimming the log sees two ticks and an exception and
has no way to tell that the two tables the guard exists for - the depth
pair, whose basis is exactly what can silently revert - were never
compared at all.

So: the numeric columns are found from the data, and a text column is
compared for equality.
"""
import importlib.util
import os

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_spec = importlib.util.spec_from_file_location(
    "check_refetch_delta",
    os.path.join(ROOT, "scripts", "check_refetch_delta.py"))
crd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crd)


HEADER = "name,d02_high,d02_low,basis"


def _table(rows):
    return "\n".join([HEADER] + rows) + "\n"


def _check(tmp_path, monkeypatch, old_rows, new_rows):
    """Run check() over a synthetic pair, with the committed side faked."""
    path = tmp_path / "sw_depth.csv"
    path.write_text(_table(new_rows), encoding="utf-8")
    monkeypatch.setattr(crd, "_committed", lambda p: _table(old_rows))
    return crd.check(str(path))


def test_a_text_column_does_not_crash_the_guard(tmp_path, monkeypatch):
    rows = ["AB10,0.100000,0.200000,postcode",
            "AB11,0.300000,0.400000,postcode"]
    ok, head = _check(tmp_path, monkeypatch, rows, rows)
    assert ok, head
    assert "postcode" not in head.split(":")[0]


def test_a_basis_flip_fails_even_though_every_number_is_plausible(
        tmp_path, monkeypatch):
    """The reversion the 2026-09-20 publish spent its day closing off:
    same columns, same shape, shares that are still shares, and a
    denominator that went back to area share."""
    old = ["AB10,0.100000,0.200000,postcode",
           "AB11,0.300000,0.400000,postcode"]
    new = ["AB10,0.100100,0.200100,area",
           "AB11,0.300100,0.400100,area"]
    ok, head = _check(tmp_path, monkeypatch, old, new)
    assert not ok, head
    assert "basis" in head and "postcode" in head and "area" in head


def test_the_numeric_gates_still_bite_with_a_text_column_present(
        tmp_path, monkeypatch):
    """Dropping the text column from the maths must not drop the maths."""
    old = ["AB10,0.100000,0.200000,postcode",
           "AB11,0.300000,0.400000,postcode"]
    new = ["AB10,0.500000,0.600000,postcode",
           "AB11,0.700000,0.800000,postcode"]
    ok, head = _check(tmp_path, monkeypatch, old, new)
    assert not ok, head


@pytest.mark.parametrize("table", ["sw_fractions.csv", "sw_fractions_cc.csv",
                                   "sw_depth.csv", "sw_depth_cc.csv"])
def test_the_guard_reads_every_table_sw_refetch_hands_it(table):
    """End to end on the real committed tables. Unchanged on disk, so
    the comparison is trivially clean - the point is that check()
    RETURNS rather than raising, which is what it did not do for the
    depth pair."""
    path = os.path.join(ROOT, "data", table)
    if not os.path.exists(path):
        pytest.skip(f"{table} not present")
    ok, head = crd.check(path)
    assert ok, head
    assert "units" in head
