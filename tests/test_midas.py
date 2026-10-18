"""The MIDAS Open gust processor, tested without any MIDAS data.

gusts_from_midas.py exists AHEAD of its data — CEDA needs a human to
register before anything can be downloaded — so its selftest is the only
thing standing between "written" and "works". It builds a synthetic
BADC-CSV station tree and checks the parts a format drift would break
silently: header/data framing, knots -> km/h, hourly rows collapsing to
daily maxima, the years-of-coverage gate, and that a 1-in-50-year gust
always exceeds the 98th percentile.
"""

import os
import subprocess
import sys


def test_midas_processor_selftest():
    script = os.path.join(os.path.dirname(__file__), "..", "scripts",
                          "gusts_from_midas.py")
    proc = subprocess.run(
        [sys.executable, script, "--selftest"],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, (
        f"selftest failed:\n{proc.stdout}\n{proc.stderr}")
    assert "selftest ok" in proc.stdout
