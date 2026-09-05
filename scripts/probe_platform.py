"""Where does a local build stop matching a CI build? Hash the stages.

A local (Windows) build of identical committed inputs differs from the
CI (Linux) build in the Met Office weather columns - `wdr_idx` on 360
districts, scattered over 88 postcode areas, mostly by one unit in the
last place and once by 10.7 (L5). That is the signature of a last-bit
difference upstream of `_idw`'s k=4 nearest-neighbour query: a near-tie
in distance picks a different fourth neighbour, everything else moves by
a rounding boundary.

This prints a hash at every stage so two platforms can be compared line
by line: the district representative points, then per layer the
neighbour INDICES, the DISTANCES, and the interpolated VALUES. The first
line that differs is where the platforms part company.

    .venv/Scripts/python.exe -u scripts/probe_platform.py
"""
import hashlib
import os
import platform
import sys

import numpy as np
import pyproj
import scipy
import shapely
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scores_real as sr                 # noqa: E402
from build_model import load_districts   # noqa: E402


def h(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


print(f"platform  {platform.system()} {platform.machine()}  python {platform.python_version()}")
print(f"numpy {np.__version__}  scipy {scipy.__version__}  shapely {shapely.__version__} "
      f"(GEOS {shapely.geos_version_string})  pyproj {pyproj.__version__} "
      f"(PROJ {pyproj.proj_version_str})")

gdf = load_districts()
bng = gdf.to_crs(27700)
pts = bng.geometry.representative_point()
targets = np.column_stack([pts.x.values, pts.y.values])
print(f"districts {len(gdf)}  names {h(np.array(gdf['name'].values, dtype='U12'))}")
print(f"targets   {h(targets)}   (representative points, EPSG:27700)")
print(f"targets@1m {h(np.round(targets, 0))}   (same, rounded to the metre)")
print(f"area      {h(bng.geometry.area.values)}")

for name in ("wind", "wdr", "rain10", "precip"):
    grid, vals = sr._load_grid(name)
    dist, idx = cKDTree(grid).query(targets, k=4)
    raw = sr._idw(grid, vals, targets)
    print(f"{name:<8} grid {h(grid)}  idx {h(idx)}  dist {h(dist)}  value {h(raw)}")

g = sr._load_gusts()
if g is not None:
    gpts, _, rp50 = g
    dist, idx = cKDTree(gpts).query(targets, k=4)
    print(f"gust     grid {h(gpts)}  idx {h(idx)}  dist {h(dist)}  "
          f"value {h(sr._idw(gpts, rp50, targets))}")
