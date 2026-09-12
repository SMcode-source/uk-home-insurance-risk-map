"""Refuse a refetch that moved more than a refetch should.

A refetch of an unchanged product against unchanged geometry should
reproduce its table almost exactly. When it does not, the interesting
cases are silent: every value still looks like a plausible share, every
nesting identity still holds, and the file is simply wrong.

That is not hypothetical. On 2026-09-12 `fetch_surface_water.py`'s merge
seeded every unit from the existing CSV and then added the freshly
fetched value on top, so re-running England against a file that already
held England double-counted it. 77% of district values rose, median
+0.08 share, mean `sw_low` 0.156 -> 0.285, nineteen units pinned at 1.0.
`tests/test_inputs.py` passed on it: doubling a small share leaves a
share, and the depth-envelope guard is a ceiling, so a too-large
envelope makes it pass MORE easily. It was caught by reading the
artifact before the commit job ran, which is not a control.

So: compare what came back against what it replaces, and fail loudly if
the move is bigger than a refetch can explain. The expected move is the
OSTN15 datum shift, which is 2-7 m - tens of 13 m pixels per district,
about 1e-5 of a fraction - so the thresholds below are generous by three
orders of magnitude and still catch a doubling.

    python scripts/check_refetch_delta.py data/sw_depth.csv ...

Each argument is a path whose committed version is read from git (HEAD)
and compared against the file on disk. A genuinely revised upstream
product WILL trip this, and that is the point: --accept-large turns it
into a warning once a human has looked at the numbers it printed.
"""

import os
import subprocess
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# A value has "moved" once it shifts by more than this. Rasterisation of
# the same tiles on a datum 2-7 m away lands far below it.
EPS = 0.01
# and no more than this share of values may move that far
MAX_MOVED = 0.01
# nor may the mean level of any column shift by more than this, relative
MAX_LEVEL = 0.02


def _read(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}, []
    cols = lines[0].split(",")
    out = {}
    for ln in lines[1:]:
        parts = ln.split(",")
        out[parts[0]] = parts[1:]
    return out, cols[1:]


def _committed(path):
    rel = os.path.relpath(os.path.abspath(path), ROOT).replace(os.sep, "/")
    try:
        return subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                              check=True, capture_output=True,
                              text=True).stdout
    except subprocess.CalledProcessError:
        return ""


def check(path):
    """Return (ok, headline) for one table."""
    name = os.path.basename(path)
    if not os.path.exists(path):
        return True, f"{name}: not present, nothing to check"
    old_text = _committed(path)
    if not old_text:
        return True, f"{name}: not committed yet, nothing to compare"

    old, old_cols = _read(old_text)
    with open(path, encoding="utf-8") as fh:
        new, new_cols = _read(fh.read())

    if old_cols != new_cols:
        return False, (f"{name}: columns changed, {old_cols} -> {new_cols}")
    gone = set(old) - set(new)
    if gone:
        return False, (f"{name}: {len(gone)} units vanished from the refetch, "
                       f"e.g. {sorted(gone)[:5]}")

    shared = [u for u in new if u in old]
    a = np.array([[float(x) for x in old[u]] for u in shared])
    b = np.array([[float(x) for x in new[u]] for u in shared])
    d = np.abs(b - a)
    moved = float((d > EPS).mean())
    lvl = []
    for j, col in enumerate(new_cols):
        m_old = a[:, j].mean()
        if m_old > 1e-9:
            lvl.append((abs(b[:, j].mean() - m_old) / m_old, col,
                        m_old, b[:, j].mean()))
    worst = max(lvl) if lvl else (0.0, "-", 0.0, 0.0)

    head = (f"{name}: {len(shared)} units, {100 * moved:.2f}% of values "
            f"moved > {EPS}, max |delta| {d.max():.5f}; worst column level "
            f"{worst[1]} {worst[2]:.5f} -> {worst[3]:.5f} "
            f"({100 * worst[0]:+.2f}%)")
    ok = moved <= MAX_MOVED and worst[0] <= MAX_LEVEL
    return ok, head


def main(argv):
    accept = "--accept-large" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        raise SystemExit(__doc__)

    bad = []
    for p in paths:
        ok, head = check(p)
        print(("  ok  " if ok else "  FAIL") + "  " + head, flush=True)
        if not ok:
            bad.append(head)

    if bad and not accept:
        print(f"\n{len(bad)} table(s) moved more than a refetch of an "
              f"unchanged product can explain.", flush=True)
        print("Look at the numbers above before doing anything else. If the "
              "upstream product really was revised, rerun with "
              "--accept-large.", flush=True)
        return 1
    if bad:
        print(f"\n{len(bad)} table(s) moved a lot; accepted by "
              f"--accept-large.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
