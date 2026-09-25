"""Surface-water masks count a pixel only when its alpha reaches MIN_ALPHA.

EA: 25% coverage (fitted to the EA's counts). NRW: its old rule, kept on
NRW's own counts. The depth masks must apply the frequency masks' rule
or the depth bands stop nesting inside the frequency envelope.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_surface_water as fs  # noqa: E402
import fetch_sw_depth as sd  # noqa: E402

HIGH = (85, 91, 157)            # EA High anchor
LOW = (195, 224, 255)           # EA Low anchor


def _image(pixels, size=2):
    """RGBA image: pixels[i] = (rgb, alpha) in raster order, rest clear."""
    a = np.zeros((size, size, 4), dtype=np.uint8)
    for i, (rgb, al) in enumerate(pixels):
        a[i // size, i % size, :3] = rgb
        a[i // size, i % size, 3] = al
    return Image.fromarray(a, "RGBA")


def test_thresholds_per_source():
    al = np.array([16, 17, 24, 25, 26, 63, 64, 102, 255])
    assert fs.MIN_ALPHA["ea_color"] == 64                  # 25% of 255
    assert al[fs.covered(al, "ea_color")].tolist() == [64, 102, 255]
    assert al[fs.covered(al, "wms_cql")].tolist() == [17, 24, 25, 26, 63, 64, 102, 255]


def test_ea_frequency_mask_drops_faint_pixels(monkeypatch):
    img = _image([(HIGH, 40), (HIGH, 200), (LOW, 40), (LOW, 200)])
    monkeypatch.setattr(fs, "http_image", lambda url: img)
    m = fs.masks_for_tile(dict(kind="ea_color", tile=2), (0, 0, 26, 26))
    assert m["high"].tolist() == [[False, True], [False, False]]
    assert m["low"].tolist() == [[False, True], [False, True]]


def test_nrw_keeps_its_own_rule(monkeypatch):
    img = _image([(LOW, 13), (LOW, 19), (LOW, 102), (LOW, 164)])
    monkeypatch.setattr(fs, "http_image", lambda url: img)
    region = dict(fs.REGIONS["wales"], tile=2)
    m = fs.masks_for_tile(region, (0, 0, 40, 40))
    assert m["low"].tolist() == [[False, True], [True, True]]


def test_depth_masks_share_the_frequency_rule(monkeypatch):
    img = _image([(HIGH, 40), (HIGH, 200), (LOW, 63), (LOW, 64)])
    monkeypatch.setattr(fs, "http_image", lambda url: img)
    monkeypatch.setattr(sd, "http_image", lambda url: img)
    freq = fs.masks_for_tile(dict(kind="ea_color", tile=2), (0, 0, 26, 26))
    depth = sd.masks_for_tile("rofsw_0_2m_depth", (0, 0, 26, 26))
    for band in ("high", "low"):
        assert depth[band].tolist() == freq[band].tolist()
