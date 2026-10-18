"""MIDAS stations vs ERA5 grid, seen the way the model sees them.

Interpolates both gust point sets to the 2,736 district centroids with
scores_real's own _idw and compares raw and through _stretch (the model
uses the stretched rank surface, weight 0.20 inside wx_score). This is
the surface-level half of the ERA5 -> MIDAS evidence (2026-08-10);
compare_rebuild.py is the premium-level half.

  python scripts/compare_gust_surfaces.py [era5.csv] [midas.csv]

Defaults compare data/gusts.csv against data/gusts_midas.csv — after the
2026-08-10 swap those are the same surface, so pass the ERA5 fallback
output explicitly to reproduce the decision evidence.
"""

import csv
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from scores_real import _idw, _stretch      # noqa: E402
from build_model import load_districts      # noqa: E402


def load_pts(path):
    xs, ys, rp50 = [], [], []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            xs.append(float(row["x"]))
            ys.append(float(row["y"]))
            rp50.append(float(row["gust_rp50"]))
    return np.column_stack([xs, ys]), np.array(rp50)


def main(a_path, b_path):
    gdf = load_districts().to_crs(27700)
    cent = np.column_stack([gdf.geometry.centroid.x, gdf.geometry.centroid.y])
    names = gdf["name"].to_numpy()

    a_pts, a_v = load_pts(a_path)
    b_pts, b_v = load_pts(b_path)
    print(f"A ({os.path.basename(a_path)}): {len(a_v)} points, "
          f"rp50 {a_v.min():.0f}-{a_v.max():.0f} km/h")
    print(f"B ({os.path.basename(b_path)}): {len(b_v)} points, "
          f"rp50 {b_v.min():.0f}-{b_v.max():.0f} km/h")

    a = _idw(a_pts, a_v, cent)
    b = _idw(b_pts, b_v, cent)
    print(f"district level: A mean {a.mean():.1f} "
          f"({a.min():.0f}-{a.max():.0f}), B mean {b.mean():.1f} "
          f"({b.min():.0f}-{b.max():.0f})")
    print(f"raw correlation {np.corrcoef(a, b)[0, 1]:.3f}; stretched "
          f"{np.corrcoef(_stretch(a), _stretch(b))[0, 1]:.3f}")

    d = _stretch(b) - _stretch(a)
    order = np.argsort(np.abs(d))[::-1]
    print("biggest movers (stretched, B - A):")
    for i in order[:10]:
        print(f"  {names[i]:6s} {d[i]:+.2f}  ({a[i]:.0f} -> {b[i]:.0f} km/h)")

    dist, _ = cKDTree(b_pts).query(cent)
    print(f"nearest B-point distance: median {np.median(dist) / 1e3:.0f} km, "
          f"p95 {np.percentile(dist, 95) / 1e3:.0f} km, "
          f"max {dist.max() / 1e3:.0f} km ({names[dist.argmax()]})")


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "gusts.csv")
    b = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "data", "gusts_midas.csv")
    main(a, b)
