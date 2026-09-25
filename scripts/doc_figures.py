"""The figures the repo's Markdown states as CURRENT, checked against the model.

The site injects every figure it shows (`__PREM_MEAN__` and friends), so
a page cannot go stale. LIMITATIONS.md and HANDOFF.md cannot be
injected, and twice they went stale by a full publish without anything
noticing: LIMITATIONS §3's per-peril table still read groundwater at
£1.34 two publishes after it moved, and HANDOFF's "current premium"
line quoted the 2026-09-01 figure after four more publishes. Dated
entries ("PUBLISHED 2026-09-06: ...") are history and are never checked;
only these two statements claim to be current:

  LIMITATIONS.md §3  the "£X priced" total and each peril's EL and share
  HANDOFF.md         "The current premium is £A — £B at 2dp, districts;
                      £C at sector grain; loss cost £D."

Every figure is household-weighted over data/districts_risk.geojson
(the sector headline over data/sectors_risk.geojson), the same weighting
build_site.py uses for __PREM_MEAN__.

Usage:
  doc_figures.py          print the current figures
  doc_figures.py --check  exit 1 if either file disagrees (tests.yml, main)
  doc_figures.py --fix    rewrite the checked figures in place

--check runs on main only, as its own step in tests.yml, NOT under
tests/: rebuild.yml runs tests/ as the pre-flight on exp/ branches,
whose model output differs from main's by design, and a doc check there
would block every experiment.
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# LIMITATIONS §3 row label -> geojson column. Order is the table's.
PERILS = [("Escape of water", "el_eow"), ("Fire", "el_fire"),
          ("Theft", "el_th"), ("Flood", "el_fl"), ("Subsidence", "el_sub"),
          ("Storm", "el_wx"), ("Accidental damage", "el_ad"),
          ("Groundwater", "el_gw")]
UNPRICED = ("Coastal erosion", "el_er")


def hh_mean(path, cols):
    with open(path, encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    w = [p.get("households", 0) for p in feats]
    tot = sum(w)
    return {c: sum(p[c] * x for p, x in zip(feats, w)) / tot for c in cols}


def figures():
    cols = ["premium", "el_total"] + [c for _, c in PERILS] + [UNPRICED[1]]
    d = hh_mean(os.path.join(ROOT, "data", "districts_risk.geojson"), cols)
    s = hh_mean(os.path.join(ROOT, "data", "sectors_risk.geojson"), ["premium"])
    d["sector_premium"] = s["premium"]
    return d


def limitations_expected(f):
    """{label: (EL text, share text)} as the table prints them."""
    total = f["el_total"]
    out = {lab: (f"£{f[c]:.2f}", f"{100 * f[c] / total:.2f}%") for lab, c in PERILS}
    out[UNPRICED[0]] = (f"£{f[UNPRICED[1]]:.2f}", None)
    return out


ROW = re.compile(r"^\| (\*?)(?P<label>[A-Za-z ]+?)\1 \| (\*?)(?P<el>£[\d.]+)\3 \| "
                 r"(?P<share>[^|]*?) \|", re.M)
TOTAL = re.compile(r"share of the \*\*£(?P<total>[\d.]+) priced\*\* total")
HEAD = re.compile(r"The current premium is £(?P<a>[\d.]+) — £(?P<b>[\d.]+) at "
                  r"2dp, districts;\s+£(?P<c>[\d.]+) at sector grain; loss cost "
                  r"£(?P<d>[\d.]+)\.")


def check_or_fix(fix):
    f = figures()
    exp = limitations_expected(f)
    problems = []
    # "Priced total" means el_total, the eight insured perils; erosion is
    # carried and unpriced. If that identity breaks, the table's shares
    # are over the wrong denominator and no cell-by-cell check notices.
    parts = sum(f[c] for _, c in PERILS)
    if abs(parts - f["el_total"]) > 0.01:
        problems.append(f"el_total £{f['el_total']:.2f} is not the sum of the "
                        f"eight perils £{parts:.2f} - the table's denominator moved")

    p = os.path.join(ROOT, "LIMITATIONS.md")
    text = open(p, encoding="utf-8", newline="").read()
    m = TOTAL.search(text)
    want_total = f"{f['el_total']:.2f}"
    if not m:
        problems.append("LIMITATIONS.md: the '£X priced total' sentence is missing")
    elif m.group("total") != want_total:
        problems.append(f"LIMITATIONS.md total £{m.group('total')} != £{want_total}")
        text = text[:m.start("total")] + want_total + text[m.end("total"):]
    seen = set()

    def row(mo):
        lab = mo.group("label")
        if lab not in exp:
            return mo.group(0)
        seen.add(lab)
        el, share = exp[lab]
        raw = mo.group("share")
        bold = "**" if raw.startswith("**") else ""
        cur_share = raw.strip("*")
        new_el, new_share = mo.group("el"), raw
        if new_el != el:
            problems.append(f"LIMITATIONS.md {lab}: EL {new_el} != {el}")
            new_el = el
        if share is not None and cur_share != share:
            problems.append(f"LIMITATIONS.md {lab}: share {cur_share} != {share}")
            new_share = bold + share + bold
        o = mo.start()
        s = mo.group(0)
        return (s[:mo.start("el") - o] + new_el + s[mo.end("el") - o:mo.start("share") - o]
                + new_share + s[mo.end("share") - o:])
    text = ROW.sub(row, text)
    for lab in exp:
        if lab not in seen:
            problems.append(f"LIMITATIONS.md §3 has no row for {lab}")
    if fix:
        open(p, "w", encoding="utf-8", newline="").write(text)

    p = os.path.join(ROOT, "HANDOFF.md")
    text = open(p, encoding="utf-8", newline="").read()
    want = {"a": f"{f['premium']:.4f}", "b": f"{f['premium']:.2f}",
            "c": f"{f['sector_premium']:.4f}", "d": f"{f['el_total']:.2f}"}
    m = HEAD.search(text)
    if not m:
        problems.append("HANDOFF.md: the 'The current premium is ...' line is missing")
    else:
        for k in "dcba":            # right to left, so offsets stay valid
            if m.group(k) != want[k]:
                problems.append(f"HANDOFF.md current premium ({k}) £{m.group(k)} != £{want[k]}")
                text = text[:m.start(k)] + want[k] + text[m.end(k):]
        if fix:
            open(p, "w", encoding="utf-8", newline="").write(text)
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")     # the £ on a cp1252 console
    args = sys.argv[1:]
    if not args:
        f = figures()
        print(f"premium districts £{f['premium']:.4f}, sectors £{f['sector_premium']:.4f}; "
              f"priced loss cost £{f['el_total']:.2f}")
        for lab, (el, share) in limitations_expected(f).items():
            print(f"  {lab:18s} {el:>8s}  {share or '-'}")
        return
    fix = args == ["--fix"]
    if args not in (["--check"], ["--fix"]):
        raise SystemExit(__doc__)
    problems = check_or_fix(fix)
    for p in problems:
        print(("fixed: " if fix else "STALE: ") + p)
    if problems and not fix:
        raise SystemExit(f"{len(problems)} stale figure(s) - run "
                         "scripts/doc_figures.py --fix and commit")
    if not problems:
        print("LIMITATIONS.md §3 and HANDOFF.md's current premium match the model")


if __name__ == "__main__":
    main()
