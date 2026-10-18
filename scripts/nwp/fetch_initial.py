"""Real initial conditions: NCEP/NCAR Reanalysis 1, free, no key.

NOAA PSL over OPeNDAP, 2.5 degree global, four times daily, 1948 to
now, public domain.

Two notes. (1) netCDF4 speaks OPeNDAP but its bundled libcurl fails on
this machine's TLS chain, while urllib on the system trust store
works - so this parses the `.ascii` DODS response, which the server
returns already unpacked. (2) Only the wind is taken. A one-layer model
cannot swallow both the observed geopotential and the observed wind,
because in the real baroclinic atmosphere they are not in
shallow-water balance and forcing both in launches a spurious
gravity-wave shock. The wind carries the vorticity, so the wind is
kept and the mass field is derived from it by the balance equation.
"""

import os
import re
import ssl
import urllib.request
from datetime import datetime, timedelta

import numpy as np

BASE = ("https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/"
        "pressure/{var}.{year}.nc")
EPOCH = datetime(1800, 1, 1)
UA = {"User-Agent": "uk-home-insurance-risk-map (github.com/SMcode-source)"}
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250,
          200, 150, 100, 70, 50, 30, 20, 10]

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.abspath(os.path.join(HERE, "..", "..", "data", "cache", "ncep"))


def _get(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def _parse_dods_ascii(text, var):
    """Pull the numeric block for `var` out of a DODS .ascii response.

    The payload looks like

        uwnd.uwnd[1][1][73][144]
        [0][0][0], -11.9, -11.8, ...
        [0][0][1], ...

    one line per row of the last-but-one dimension.  Returns the rows as
    a 2-D array in the order they appear.
    """
    marker = re.search(rf"^{re.escape(var)}\.{re.escape(var)}\[", text,
                       flags=re.M)
    if marker is None:
        raise ValueError(f"no data block for {var!r} in the DODS response; "
                         f"first 300 chars: {text[:300]!r}")
    rows = []
    for line in text[marker.end():].splitlines()[1:]:
        line = line.strip()
        if not line:
            if rows:
                break
            continue
        if not line.startswith("["):
            break
        _, _, values = line.partition(",")
        rows.append([float(x) for x in values.split(",")])
    if not rows:
        raise ValueError(f"empty data block for {var!r}")
    return np.array(rows)


def _time_index(year, when):
    """Index of the reanalysis step nearest `when`, checked against the
    file's own time axis rather than assumed from the 6-hourly spacing."""
    url = BASE.format(var="uwnd", year=year) + ".ascii?time"
    text = _get(url)
    nums = re.search(r"time\[\d+\]\s*\n(.*)", text, flags=re.S)
    vals = np.array([float(x) for x in nums.group(1).replace("\n", ",").split(",")
                     if x.strip()])
    target = (when - EPOCH).total_seconds() / 3600.0
    i = int(np.argmin(np.abs(vals - target)))
    actual = EPOCH + timedelta(hours=float(vals[i]))
    return i, actual


def fetch_level(when, level_hpa=500, cache=True, verbose=True):
    """Observed u, v (m/s) and geopotential height (m) on the 2.5-degree
    grid at one pressure level and one analysis time."""
    if isinstance(when, str):
        when = datetime.fromisoformat(when)
    if level_hpa not in LEVELS:
        raise ValueError(f"{level_hpa} hPa is not a reanalysis level: {LEVELS}")
    lev = LEVELS.index(level_hpa)

    os.makedirs(CACHE, exist_ok=True)
    tag = f"ncep_{when:%Y%m%d%H}_{level_hpa}"
    path = os.path.join(CACHE, tag + ".npz")
    if cache and os.path.exists(path):
        if verbose:
            print(f"  cached: {path}")
        z = np.load(path)
        return {k: z[k] for k in z.files} | {"time": str(z["time"])}

    ti, actual = _time_index(when.year, when)
    if verbose:
        print(f"  NCEP/NCAR R1 {level_hpa} hPa at {actual:%Y-%m-%d %H:%M} UTC "
              f"(time index {ti})", flush=True)

    out = {}
    for var in ("uwnd", "vwnd", "hgt"):
        url = (BASE.format(var=var, year=when.year)
               + f".ascii?{var}[{ti}:{ti}][{lev}:{lev}][0:72][0:143]")
        if verbose:
            print(f"    fetching {var} ...", flush=True)
        out[var] = _parse_dods_ascii(_get(url), var)
        if out[var].shape != (73, 144):
            raise ValueError(f"{var}: expected (73, 144), got {out[var].shape}")

    lat = np.linspace(90.0, -90.0, 73)          # as served, north first
    lon = np.linspace(0.0, 357.5, 144)
    res = {"lat": lat, "lon": lon, "u": out["uwnd"], "v": out["vwnd"],
           "z": out["hgt"], "time": f"{actual:%Y-%m-%dT%H:%M}",
           "level_hpa": np.array(level_hpa)}
    if cache:
        np.savez_compressed(path, **res)
    return res


def to_gaussian(sph, field, lat, lon):
    """Bilinear interpolation from the 2.5-degree lat/lon grid onto the
    model's Gaussian grid, periodic in longitude."""
    from scipy.interpolate import RegularGridInterpolator

    order = np.argsort(lat)
    lat_s = lat[order]
    f = field[order]
    lon_w = np.concatenate([lon, [360.0]])
    f = np.concatenate([f, f[:, :1]], axis=1)      # wrap
    interp = RegularGridInterpolator((lat_s, lon_w), f, bounds_error=False,
                                     fill_value=None)
    glat = np.degrees(sph.lat)
    glon = np.degrees(sph.lon) % 360.0
    pts = np.stack(np.meshgrid(glat, glon, indexing="ij"), axis=-1)
    return interp(pts)


def observed_state(sph, when, level_hpa=500, verbose=True):
    """Observed wind interpolated to the model grid, plus the observed
    height for reference.  Returns (u, v, z) in grid space."""
    raw = fetch_level(when, level_hpa=level_hpa, verbose=verbose)
    u = to_gaussian(sph, raw["u"], raw["lat"], raw["lon"])
    v = to_gaussian(sph, raw["v"], raw["lat"], raw["lon"])
    z = to_gaussian(sph, raw["z"], raw["lat"], raw["lon"])
    return u, v, z, raw["time"]
