"""Guards on England's multi-pass RoFRS read (fetch_flood_postcodes.py).

The EA's WMS drops a polygon from some renders depending on where the
request box falls (TN23 9: the same High polygon drew or vanished as the
box's west edge moved, at every box size). England is therefore read on
RS_PASSES shifted grids and combined by majority, with a vanished polygon
- a cluster of postcodes only a minority of passes banded - kept. These
pin that combination, that scattered edge noise is not kept, and that the
passes really are different grids.
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


def test_a_band_most_passes_drew_survives_the_pass_that_dropped_it():
    got = fp.combine_passes([[0, 4, 3], [2, 0, 3], [2, 4, 0]])
    assert got.tolist() == [2, 4, 3]


def test_a_band_only_one_pass_drew_is_an_edge_unless_rescued():
    codes = [[0, 4], [0, 0], [3, 0]]
    assert fp.combine_passes(codes).tolist() == [0, 0]
    assert fp.combine_passes(codes, np.array([True, False])).tolist() == [3, 0]


def test_disagreeing_bands_take_the_majority_ties_going_higher():
    got = fp.combine_passes([[3, 3, 2, 0], [3, 4, 4, 2], [4, 4, 0, 4]])
    assert got.tolist() == [3, 4, 4, 4]


def test_unsampled_and_unavailable_are_not_hidden():
    got = fp.combine_passes([[4, 5], [-1, 5], [4, 5]])
    assert got.tolist() == [-1, 5]


def test_a_vanished_polygon_is_kept_and_scattered_edges_are_not():
    # a cluster of RS_RESCUE_N postcodes 40 m apart that only pass 2 drew,
    # and as many scattered singletons 5 km apart
    n = fp.RS_RESCUE_N
    x = np.r_[np.arange(n) * 40.0, 10_000 + np.arange(n) * 5_000.0]
    y = np.zeros(2 * n)
    codes = np.zeros((3, 2 * n), dtype=int)
    codes[2] = 4
    rescue = fp.dropout_clusters(codes, x, y)
    assert rescue.tolist() == [True] * n + [False] * n
    got = fp.combine_passes(codes, rescue)
    assert got.tolist() == [4] * n + [0] * n


def test_a_cluster_needs_the_same_pattern():
    # neighbours banded by different single passes are edge noise, not one
    # vanished polygon
    n = fp.RS_RESCUE_N
    x = np.arange(n) * 40.0
    codes = np.zeros((3, n), dtype=int)
    for i in range(n):
        codes[i % 3, i] = 4
    assert not fp.dropout_clusters(codes, x, np.zeros(n)).any()


def test_a_cluster_one_short_is_not_kept():
    n = fp.RS_RESCUE_N - 1
    codes = np.zeros((3, n), dtype=int)
    codes[1] = 3
    assert not fp.dropout_clusters(codes, np.arange(n) * 40.0, np.zeros(n)).any()


def test_the_passes_are_different_grids(monkeypatch):
    """Each pass must move every tile edge: a pass on the same grid would
    reproduce the same dropouts and add nothing."""
    boxes = {}

    def fake_url(base, layer, bbox):
        boxes.setdefault(current[0], []).append(bbox)
        return "u"

    monkeypatch.setattr(fp, "rofrs_url", fake_url)
    monkeypatch.setattr(fp, "http_rgba", lambda url: None)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    pc = pd.DataFrame({"country": ["England"] * 3})
    x = np.array([300_000.0, 450_000.0, 520_000.0])
    y = np.array([200_000.0, 400_000.0, 180_000.0])
    current = [None]
    for k, sh in enumerate(fp.RS_PASSES):
        current[0] = k
        fp.rofrs_pass(pc, x, y, sh)
    T = fp.RS_PX * fp.RS_TILE
    edges = [{round(b[0] % T, 3) for b in boxes[k]} for k in boxes]
    assert len(fp.RS_PASSES) >= 3
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            assert not edges[i] & edges[j], "two passes share tile edges"
    # every pass still covers every postcode
    for k in boxes:
        for xi, yi in zip(x, y):
            assert any(b[0] <= xi < b[2] and b[1] <= yi < b[3] for b in boxes[k])
