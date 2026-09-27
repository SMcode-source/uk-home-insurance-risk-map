"""Guards on the NRW FRAW polygon read in fetch_flood_postcodes.py.

Wales moved from 100 m WMS masks to FRAW's own polygons on
exp/wales-vector: the masks buffered every polygon (alpha > 16 at 40%
opacity) and inflated the >=1% zone - 46 postcodes against 3 in a box
round Grangetown. The polygons come from a GeoServer whose only common
sort key (mm_id) is not unique, so paging on it skipped 248 river
features; the read is by bounding box instead, each box fetched whole
and split in four when it comes back at the cap or errors. A missing
feature writes its postcodes as "no flood risk" with nothing looking
wrong, so these pin: a capped box and an erroring box are both split
until whole, a polygon crossing a box edge counts once, the higher of
rivers and sea wins, and a count that does not match refuses rather
than truncates.
"""
import importlib.util
import io
import json
import os
import urllib.error
import urllib.parse

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_spec = importlib.util.spec_from_file_location(
    "fetch_flood_postcodes",
    os.path.join(ROOT, "scripts", "fetch_flood_postcodes.py"))
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)

N = 200                 # squares; more than the cap in every tile
BOX = (0, 0, 4000, 4000)
SPAN = (1900, 3800, 2100, 3850)   # a river High polygon across a tile edge


def _xy(i):
    return (i % 20) * 200 + 10, (i // 20) * 360 + 10


def _rect(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _features(layer):
    """Rivers: square i is High if i % 3 == 0, Medium if 1, Low if 2,
    plus SPAN. Sea: square i is High where i % 3 == 2, so there the
    higher band (sea High over river Low) must win."""
    sea = "SEA" in layer
    out = []
    for i in range(N):
        if sea and i % 3 != 2:
            continue
        x0, y0 = _xy(i)
        risk = "High" if sea else ("High", "Medium", "Low")[i % 3]
        out.append((f"{layer.split(':')[1]}.{i}", (x0, y0, x0 + 50, y0 + 50),
                    risk))
    if not sea:
        out.append((f"{layer.split(':')[1]}.span", SPAN, "High"))
    return out


class FakeNRW:
    """Answers resultType=hits with numberMatched and GetFeature with the
    features whose box meets the request box, first `count` of them.
    The sea layer 500s on any box wider than 1500 m."""

    def __init__(self, drop=None):
        self.drop = drop
        self.boxes = []

    def __call__(self, url, timeout=None):
        q = {k: v[0] for k, v in
             urllib.parse.parse_qs(url.split("?", 1)[1]).items()}
        layer = q["typeNames"]
        bx = [float(v) for v in q["bbox"].split(",")[:4]]
        hit = [f for f in _features(layer)
               if f[1][0] <= bx[2] and f[1][2] >= bx[0]
               and f[1][1] <= bx[3] and f[1][3] >= bx[1]]
        if q.get("resultType") == "hits":
            return io.BytesIO(
                f'<wfs:FeatureCollection numberMatched="{len(hit)}" '
                'numberReturned="0"/>'.encode())
        self.boxes.append((layer, tuple(bx)))
        if "SEA" in layer and bx[2] - bx[0] > 1500:
            raise urllib.error.HTTPError(url, 500, "too big", {}, None)
        hit = [f for f in hit if f[0] != self.drop][:int(q["count"])]
        body = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": fid, "geometry": _rect(*b),
             "properties": {"risk": r}} for fid, b, r in hit]}
        return io.BytesIO(json.dumps(body).encode())


@pytest.fixture
def small(monkeypatch):
    monkeypatch.setitem(fp.ff.REGIONS, "wales",
                        dict(fp.ff.REGIONS["wales"], bbox=BOX))
    monkeypatch.setattr(fp, "FRAW_TILE_M", 2000)
    monkeypatch.setattr(fp, "FRAW_CAP", 30)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)


def _postcodes():
    xs = [_xy(i)[0] + 25 for i in range(N)] + [3990, 2050]
    ys = [_xy(i)[1] + 25 for i in range(N)] + [3990, 3825]
    pc = pd.DataFrame({"country": ["Wales"] * len(xs)})
    return pc, np.array(xs, float), np.array(ys, float)


def test_every_feature_is_read_and_the_higher_band_wins(monkeypatch, small):
    fake = FakeNRW()
    monkeypatch.setattr(fp.urllib.request, "urlopen", fake)
    pc, x, y = _postcodes()
    hi, lo = np.zeros(len(x), bool), np.zeros(len(x), bool)
    band = fp.vector_wales(pc, x, y, hi, lo)

    i = np.arange(N)
    want = np.where(i % 3 == 0, 3, np.where(i % 3 == 1, 2, 3))
    assert (band[:N] == want).all()
    assert band[N] == 0 and not lo[N]            # the dry corner
    assert band[N + 1] == 3 and hi[N + 1]        # inside SPAN only
    assert hi[:N].all() and lo[:N].all()
    # both ways of splitting were exercised: rivers by the cap, sea by 500s
    for layer in fp.FRAW_LAYERS:
        widths = {b[2] - b[0] for l_, b in fake.boxes if l_ == layer}
        assert min(widths) < 2000, f"{layer} never split"


def test_a_box_that_comes_back_short_refuses(monkeypatch, small):
    """A server that silently leaves a feature out of every box must be
    caught by the count, not written as dry."""
    monkeypatch.setattr(fp.urllib.request, "urlopen",
                        FakeNRW(drop="NRW_FLOOD_RISK_FROM_RIVERS.7"))
    pc, x, y = _postcodes()
    hi, lo = np.zeros(len(x), bool), np.zeros(len(x), bool)
    with pytest.raises(SystemExit, match="partial Wales"):
        fp.vector_wales(pc, x, y, hi, lo)


def test_a_persistent_failure_refuses_rather_than_truncating(monkeypatch,
                                                             small):
    def down(url, timeout=None):
        raise urllib.error.URLError("unreachable")
    monkeypatch.setattr(fp.urllib.request, "urlopen", down)
    with pytest.raises(SystemExit, match="partial Wales"):
        fp.fraw_tile(fp.FRAW_LAYERS[0], BOX)
    with pytest.raises(SystemExit, match="partial Wales"):
        fp.fraw_matched(fp.FRAW_LAYERS[0], BOX)
