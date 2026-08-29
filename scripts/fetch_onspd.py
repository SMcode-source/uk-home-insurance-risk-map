"""UK unit-postcode centroids - the one open source that includes NI.

WHY THIS EXISTS. The published map is Great Britain only: 2,099 English,
442 Scottish and 195 Welsh districts, and zero BT. That is not a
modelling choice, it is inherited from the geometry. Source #1
(missinglink/uk-postcode-polygons) is documented in DATA_SOURCES.md as
"GB only, no BT/Northern Ireland", and Code-Point Open (#23), which is
the better source for GB at 1 m straight from OS, also stops at the
Irish Sea. ONSPD is the only open dataset carrying all four countries in
one file, so it is what Northern Ireland has to come from.

It adds 80 districts and 267 sectors - 2.9% and 2.6% of each grain.

*** THE NORTHERN IRELAND COORDINATE TRAP ***

ONSPD's east1m/north1m columns are NOT on the same grid for the whole
file. For GB they are British National Grid (EPSG:27700). For Northern
Ireland they are IRISH Grid (EPSG:29903), and nothing in the column name
says so. Measured on BT1 1AA, which ONSPD gives as 334316, 374675:

    read as BNG          -> 53.2650 N, 2.9862 W  = Runcorn, Cheshire
    read as Irish Grid   -> 54.6024 N, 5.9223 W  = Belfast
    true Belfast                                   54.5996 N, 5.9264 W

So the naive read puts Belfast 244 km away, on the wrong island, in a
part of England that already has its own postcodes. It would not throw.
It would produce a plausible-looking map with NI silently smeared over
Cheshire, and the first symptom would be a subsidence number nobody
could explain.

This script therefore NEVER reads east1m/north1m. It uses lat/long,
which ONSPD supplies in WGS84 for every country, and reprojects. The
guard below asserts that no emitted point lands outside the UK bounding
box, so if a future ONSPD release changes the lat/long convention the
run fails instead of publishing Belfast into the Mersey.

VALIDATION. Using lat/long for GB as well as NI keeps one code path and
removes the seam, but only if it is as precise as Code-Point Open's
native 1 m eastings. That is checked, not assumed: --check-cpo compares
every GB postcode present in both sources and reports the distance
distribution. ONSPD's GB grid references derive from Code-Point Open in
the first place, so they should agree to well under a metre.

Source: ONS Open Geography Portal, ONS Postcode Directory (May 2026),
item 6fff67d204fd4f339591ed667a6e3642. ONS geography licences apply
(OGL, with Royal Mail and OS terms for the postcode data).

Output: data/postcode_centroids.csv
        (postcode, sector, district, area, country, easting, northing)
        eastings/northings are EPSG:27700 for ALL FOUR COUNTRIES.

Usage:
  fetch_onspd.py                 # download if needed, then build
  fetch_onspd.py --check-cpo     # also cross-check GB against Code-Point Open
"""

import argparse
import csv
import io
import os
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CACHE = os.path.join(ROOT, "data", "cache")
ZIP = os.path.join(CACHE, "onspd_full.zip")
CPO = os.path.join(CACHE, "codepoint_open.zip")
OUT = os.path.join(ROOT, "data", "postcode_centroids.csv")

ITEM = "6fff67d204fd4f339591ed667a6e3642"      # ONSPD May 2026
URL = f"https://www.arcgis.com/sharing/rest/content/items/{ITEM}/data"

# Great Britain plus Northern Ireland, generously bounded. Anything
# outside this in EPSG:27700 means the coordinate convention moved.
UK_BOX = (-250_000, -20_000, 800_000, 1_300_000)

CTRY = {"E": "England", "W": "Wales", "S": "Scotland", "N": "Northern Ireland"}


def download():
    if os.path.exists(ZIP):
        print(f"  cached: {ZIP} ({os.path.getsize(ZIP) / 1e6:.0f} MB)")
        return
    os.makedirs(CACHE, exist_ok=True)
    part = ZIP + ".partial"
    print("  downloading ONSPD (~247 MB)...", flush=True)
    t0 = time.time()
    req = urllib.request.Request(URL, headers={"User-Agent": "uk-risk-map/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as fh:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            fh.write(b)
    os.replace(part, ZIP)
    print(f"  done in {time.time() - t0:.0f}s", flush=True)


def split_postcode(pcds):
    """'BT1 1AA' -> ('BT', 'BT1', 'BT1 1'). None if not a real unit."""
    out, _, inw = pcds.strip().upper().partition(" ")
    if not out or not inw:
        return None
    area = "".join(c for c in out if c.isalpha())
    if not area:
        return None
    return area, out, f"{out} {inw[0]}"


def require_ostn15():
    """Refuse to run on the fallback datum shift.

    EPSG:4326 -> EPSG:27700 has two very different implementations. The
    right one is OSTN15, a transformation GRID, accurate to ~0.1 m. If
    that grid is not installed pyproj does not fail - it quietly drops to
    a 7-parameter Helmert and keeps going, and every coordinate comes out
    about 1.75 m off. Measured: with the grid missing, 24.5% of GB
    postcodes disagreed with Code-Point Open by more than 2 m; median
    1.75 m. That is a systematic shift in one direction, not noise, and
    it would be baked into every polygon this feeds.

    It does not change which 1 km climate cell or which geology polygon a
    sector lands in, so it is not a correctness emergency. It is a silent
    downgrade of the exact accuracy this rebuild exists to improve, and a
    fresh CI runner has no grid by default - so it fails loudly instead.

    Fix:  .venv/Scripts/pyproj.exe sync --file uk_os_OSTN15_NTv2_OSGBtoETRS
    """
    from pyproj.transformer import TransformerGroup

    tg = TransformerGroup(4326, 27700, always_xy=True)
    missing = [o.name for o in tg.unavailable_operations
               if "OSTN15" in o.name or "(9)" in o.name]
    if missing:
        raise SystemExit(
            "the OSTN15 transformation grid is not installed, so pyproj "
            "would silently fall back to a ~1.75 m Helmert shift.\n"
            "  fix: .venv/Scripts/pyproj.exe sync "
            "--file uk_os_OSTN15_NTv2_OSGBtoETRS\n"
            f"  missing: {missing[0]}\nNothing was written.")


def build(check_cpo):
    import pyproj

    require_ostn15()
    zf = zipfile.ZipFile(ZIP)
    member = next(n for n in zf.namelist()
                  if n.startswith("Data/ONSPD_") and n.endswith("_UK.csv"))
    print(f"  reading {member}", flush=True)

    to_bng = pyproj.Transformer.from_crs(4326, 27700, always_xy=True)
    x0, y0, x1, y1 = UK_BOX

    rows = []
    seen = terminated = no_fix = 0
    by_country = {}
    with zf.open(member) as fh:
        rdr = csv.reader(io.TextIOWrapper(fh, "latin-1"))
        hdr = next(rdr)
        ix = {c: i for i, c in enumerate(hdr)}
        for col in ("pcds", "doterm", "lat", "long", "ctry25cd"):
            if col not in ix:
                raise SystemExit(
                    f"ONSPD column '{col}' missing - the release changed "
                    f"its schema. Columns: {hdr}")
        for row in rdr:
            seen += 1
            if row[ix["doterm"]].strip():
                terminated += 1
                continue
            parts = split_postcode(row[ix["pcds"]])
            if parts is None:
                continue
            lat, lon = row[ix["lat"]].strip(), row[ix["long"]].strip()
            # ONSPD parks postcodes with no grid reference at (99.999, 0)
            if not lat or not lon or float(lat) > 90:
                no_fix += 1
                continue
            e, n = to_bng.transform(float(lon), float(lat))
            if not (x0 <= e <= x1 and y0 <= n <= y1):
                raise SystemExit(
                    f"{row[ix['pcds']]} reprojects to {e:.0f},{n:.0f}, which "
                    f"is outside the UK. ONSPD's lat/long convention has "
                    f"changed - see the coordinate trap note above. Nothing "
                    f"was written.")
            ctry = CTRY.get(row[ix["ctry25cd"]][:1], "Unknown")
            by_country[ctry] = by_country.get(ctry, 0) + 1
            area, district, sector = parts
            rows.append((row[ix["pcds"]].strip(), sector, district, area,
                         ctry, round(e, 1), round(n, 1)))

    print(f"  {seen:,} postcodes, {terminated:,} terminated, "
          f"{no_fix:,} with no grid reference")
    print(f"  {len(rows):,} live postcodes kept")
    for c in sorted(by_country, key=lambda k: -by_country[k]):
        print(f"     {c:<18}{by_country[c]:>9,}")

    ni = [r for r in rows if r[4] == "Northern Ireland"]
    print(f"  Northern Ireland: {len(ni):,} postcodes, "
          f"{len({r[2] for r in ni})} districts, "
          f"{len({r[1] for r in ni})} sectors")

    if check_cpo:
        cross_check_cpo(rows)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["postcode", "sector", "district", "area", "country",
                    "easting", "northing"])
        w.writerows(rows)
    print(f"  wrote {OUT} ({os.path.getsize(OUT) / 1e6:.0f} MB)")


def cross_check_cpo(rows):
    """Is ONSPD lat/long as good as Code-Point Open's native 1 m eastings?

    Only meaningful for GB - Code-Point Open has no NI to compare against,
    which is the whole reason ONSPD is being used.
    """
    if not os.path.exists(CPO):
        print("  --check-cpo: codepoint_open.zip not cached, skipping")
        return
    import numpy as np

    cpo = {}
    with zipfile.ZipFile(CPO) as zf:
        for name in zf.namelist():
            low = name.lower()
            if "/csv/" not in low or not low.endswith(".csv"):
                continue
            with zf.open(name) as fh:
                for r in csv.reader(io.TextIOWrapper(fh, "latin-1")):
                    if len(r) > 3 and r[2] and r[3]:
                        # no header row; postcode is space-padded to 7
                        pc = r[0].strip().upper()
                        pc = f"{pc[:-3].strip()} {pc[-3:]}"
                        try:
                            cpo[pc] = (float(r[2]), float(r[3]))
                        except ValueError:
                            pass
    if not cpo:
        print("  --check-cpo: no rows parsed from Code-Point Open, skipping")
        return

    d = []
    for pc, _s, _d, _a, ctry, e, n in rows:
        if ctry == "Northern Ireland":
            continue
        c = cpo.get(pc)
        if c:
            d.append(((e - c[0]) ** 2 + (n - c[1]) ** 2) ** 0.5)
    if not d:
        print("  --check-cpo: no overlapping postcodes, skipping")
        return
    d = np.array(d)
    print(f"  --check-cpo: {len(d):,} GB postcodes in both sources")
    print(f"     median {np.median(d):.2f} m   p99 "
          f"{np.percentile(d, 99):.2f} m   max {d.max():.1f} m")
    if np.median(d) > 2.0:
        print("     WARNING: ONSPD lat/long disagrees with Code-Point Open by "
              "more than 2 m at the median. Prefer CPO for GB.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check-cpo", action="store_true",
                    help="cross-check GB centroids against Code-Point Open")
    args = ap.parse_args()
    download()
    build(args.check_cpo)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
