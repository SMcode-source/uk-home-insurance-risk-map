"""scripts/doc_figures.py catches, and repairs, stale "current" figures.

On synthetic files, not the repo's: the real check runs on main only
(tests.yml), and a guard whose only exercise is the event it guards
against is untested by construction.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import doc_figures  # noqa: E402

PERILS = dict(el_eow=40.0, el_fire=28.0, el_th=20.0, el_fl=20.0,
              el_sub=20.0, el_wx=10.0, el_ad=10.0, el_gw=2.0)


def _geojson(path, rows):
    feats = [{"type": "Feature", "geometry": None, "properties": r} for r in rows]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)


def _repo(tmp_path, gw_text="£2.00", share_text="**26.67%**", total="150.00"):
    (tmp_path / "data").mkdir()
    row = dict(PERILS, el_total=sum(PERILS.values()), el_er=3.0)
    _geojson(tmp_path / "data" / "districts_risk.geojson",
             [dict(row, premium=150.0, households=1),
              dict(row, premium=170.0, households=3)])
    _geojson(tmp_path / "data" / "sectors_risk.geojson",
             [dict(premium=166.0, households=1)])
    rows = [("Escape of water", "£40.00", share_text), ("Fire", "£28.00", "18.67%"),
            ("Theft", "£20.00", "13.33%"), ("Flood", "£20.00", "13.33%"),
            ("Subsidence", "£20.00", "13.33%"), ("Storm", "£10.00", "6.67%"),
            ("Accidental damage", "£10.00", "6.67%"),
            ("Groundwater", gw_text, "1.33%")]
    table = "\n".join(f"| {a} | {b} | {c} | x | y | z |" for a, b, c in rows)
    (tmp_path / "LIMITATIONS.md").write_text(
        f"EL per policy and share of the **£{total} priced** total.\n\n"
        "| peril | EL | share | driver | resolution | coverage |\n|---|---|---|---|---|---|\n"
        + table + "\n| *Coastal erosion* | *£3.00* | *—* | *a* | *b* | *c* |\n",
        encoding="utf-8")
    (tmp_path / "HANDOFF.md").write_text(
        "**The current premium is £165.0000 — £165.00 at 2dp, districts;\n"
        "£166.0000 at sector grain; loss cost £150.00.** More text.\n",
        encoding="utf-8")


def test_current_figures_pass(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(doc_figures, "ROOT", str(tmp_path))
    assert doc_figures.check_or_fix(fix=False) == []


def test_stale_figures_are_caught_then_fixed(tmp_path, monkeypatch):
    _repo(tmp_path, gw_text="£1.34", share_text="**25.83%**", total="152.00")
    monkeypatch.setattr(doc_figures, "ROOT", str(tmp_path))
    found = doc_figures.check_or_fix(fix=False)
    assert "LIMITATIONS.md Groundwater: EL £1.34 != £2.00" in found
    assert "LIMITATIONS.md Escape of water: share 25.83% != 26.67%" in found
    assert "LIMITATIONS.md total £152.00 != £150.00" in found
    # households 1 and 3: (150 + 3*170) / 4 = 165.0 - that one is current
    assert not any("current premium (a)" in p for p in found)

    doc_figures.check_or_fix(fix=True)
    assert doc_figures.check_or_fix(fix=False) == []
    lim = (tmp_path / "LIMITATIONS.md").read_text(encoding="utf-8")
    assert "| Escape of water | £40.00 | **26.67%** |" in lim   # bold kept
    assert "| *Coastal erosion* | *£3.00* | *—* |" in lim        # untouched


def test_a_missing_row_or_line_is_reported_not_passed(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(doc_figures, "ROOT", str(tmp_path))
    p = tmp_path / "LIMITATIONS.md"
    p.write_text(p.read_text(encoding="utf-8").replace("| Theft |", "| Burglary |"),
                 encoding="utf-8")
    (tmp_path / "HANDOFF.md").write_text("no premium line here\n", encoding="utf-8")
    found = doc_figures.check_or_fix(fix=False)
    assert "LIMITATIONS.md §3 has no row for Theft" in found
    assert any("HANDOFF.md: the 'The current premium" in p for p in found)
