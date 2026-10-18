"""Guards on the SEPA polygon paging in fetch_flood_postcodes.py.

On 2026-09-25 the tolerance SEPA generalises its polygons to went from
100 m to 5 m (a 100 m simplification moved 32% of the coastal flags).
Full-detail coastal features are big enough that SEPA answers a
1,000-feature page with HTTP 500, so a 500 now halves the page. The
old stop test - "fewer than 1,000 features came back" - would then end
every layer after its first shrunken page and write the rest of
Scotland as "no flood risk" with no error at all. These tests pin both
halves: the page shrinks, and a shrunken page does not end the layer.
"""
import importlib.util
import io
import json
import os
import urllib.error

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_spec = importlib.util.spec_from_file_location(
    "fetch_flood_postcodes",
    os.path.join(ROOT, "scripts", "fetch_flood_postcodes.py"))
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)

N_FEATURES = 1_300          # more than one page, not a multiple of it
MAX_OK_PAGE = 300           # the fake server 500s on anything bigger


def _square(i):
    x0 = 300_000 + 100 * i
    return {"type": "Polygon", "coordinates": [[
        [x0, 700_000], [x0 + 50, 700_000], [x0 + 50, 700_050],
        [x0, 700_050], [x0, 700_000]]]}


class FakeSEPA:
    def __init__(self, flag):
        self.requests = []
        self.flag = flag

    def __call__(self, url, timeout=None):
        q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))
        off, rec = int(q["resultOffset"]), int(q["resultRecordCount"])
        self.requests.append((off, rec))
        assert int(q["maxAllowableOffset"]) == fp.SEPA_TOLERANCE_M
        if rec > MAX_OK_PAGE:
            raise urllib.error.HTTPError(url, 500, "too big", {}, None)
        ids = range(off, min(off + rec, N_FEATURES))
        body = {"type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": _square(i),
                              "properties": {}} for i in ids],
                }
        if self.flag:
            body["exceededTransferLimit"] = off + rec < N_FEATURES
        return io.BytesIO(json.dumps(body).encode())


@pytest.mark.parametrize("flag", [True, False],
                         ids=["with-transfer-flag", "page-size-only"])
def test_a_server_error_halves_the_page_and_every_feature_is_read(
        monkeypatch, flag):
    """SEPA sends exceededTransferLimit today; the page-size fallback
    must be right on its own too, since it was the rule that broke."""
    fake = FakeSEPA(flag)
    monkeypatch.setattr(fp.urllib.request, "urlopen", fake)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    monkeypatch.setitem(fp.ff.REGIONS, "scotland",
                        {"bands": {"high": [("svc", 1)], "low": []}})
    # one Scottish postcode inside every square, one outside all of them
    xs = [300_025 + 100 * i for i in range(N_FEATURES)] + [100_000]
    pc = pd.DataFrame({"country": ["Scotland"] * len(xs)})
    x = np.array(xs, dtype=float)
    y = np.full(len(xs), 700_025.0)
    hi, lo = np.zeros(len(xs), bool), np.zeros(len(xs), bool)
    fp.vector_scotland(pc, x, y, hi, lo)

    assert hi[:N_FEATURES].all(), (
        f"only {int(hi.sum())} of {N_FEATURES} polygons were read - the "
        "layer ended early after the page shrank")
    assert not hi[-1]
    first_ok = next(i for i, (_, r) in enumerate(fake.requests)
                    if r <= MAX_OK_PAGE)
    assert max(r for _, r in fake.requests[first_ok:]) <= MAX_OK_PAGE, (
        "the page grew back past what the server accepts")
    offsets = [o for o, r in fake.requests if r <= MAX_OK_PAGE]
    assert offsets == sorted(set(offsets)), "a page was read twice"


def test_a_persistent_failure_refuses_rather_than_truncating(monkeypatch):
    def down(url, timeout=None):
        raise urllib.error.URLError("unreachable")
    monkeypatch.setattr(fp.urllib.request, "urlopen", down)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    try:
        fp.sepa_page("svc", 1, 0, 1000)
    except SystemExit as e:
        assert "partial Scotland" in str(e)
    else:
        raise AssertionError("sepa_page returned on a dead service")
