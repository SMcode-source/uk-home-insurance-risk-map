"""OS Code-Point Open: current GB unit-postcode centroids (~1.7M).

Input to derive_sectors.py (postcode-sector polygons). Keyless download
from the OS Downloads API; OS OpenData licence — attribution:
"Contains OS data © Crown copyright and database right 2026".
DATA_SOURCES.md #23 has the quirks (headerless CSVs, padded postcodes,
quality-90 rows without coordinates).

The zip is kept as-is in data/cache/ (refetchable, so gitignored with
the rest of the cache) and read directly by the consumer — no point
exploding 120 per-area CSVs onto disk.
"""

import hashlib
import json
import os
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "data", "cache", "codepoint_open.zip")
# The listing endpoint publishes each file's md5 alongside its download
# URL, so the fetch verifies against OS's own checksum for the current
# release rather than a hash pinned to a stale one. (It is /downloads
# with a query, NOT /downloadFile - that guess 404s.)
LISTING = "https://api.os.uk/downloads/v1/products/CodePointOpen/downloads"

# ~1.7M live GB postcodes; a zip with far fewer lost data in transit.
MIN_ROWS = 1_500_000


def verify(path):
    """Row-count the archive — validate the FILE, not the fetch process
    (the lesson the truncated-geology bug taught this repo)."""
    rows = 0
    with zipfile.ZipFile(path) as zf:
        csvs = [n for n in zf.namelist()
                if n.startswith("Data/CSV/") and n.endswith(".csv")]
        if not csvs:
            raise SystemExit("zip has no Data/CSV/*.csv - wrong product?")
        for name in csvs:
            with zf.open(name) as fh:
                rows += sum(1 for _ in fh)
    print(f"  {len(csvs)} area files, {rows:,} postcodes")
    if rows < MIN_ROWS:
        raise SystemExit(f"only {rows:,} rows (< {MIN_ROWS:,}) - truncated?")
    return rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        print(f"{OUT} exists - verifying instead of refetching")
        verify(OUT)
        return
    with urllib.request.urlopen(LISTING, timeout=60) as r:
        entry = next(e for e in json.load(r)
                     if e["format"] == "CSV" and e["area"] == "GB")
    part = OUT + ".partial"
    for attempt in range(6):
        try:
            print(f"downloading {entry['fileName']} "
                  f"({entry['size'] / 1e6:.0f} MB, attempt {attempt + 1})",
                  flush=True)
            urllib.request.urlretrieve(entry["url"], part)
            break
        except Exception as e:
            print(f"  {e}; retrying", flush=True)
            time.sleep(15 * (attempt + 1))
    else:
        raise SystemExit("download failed 6 times")
    with open(part, "rb") as fh:
        got = hashlib.md5(fh.read()).hexdigest()
    if got != entry["md5"]:
        raise SystemExit(f"md5 mismatch: {got} != {entry['md5']} - "
                         f"truncated download, refusing")
    verify(part)
    os.replace(part, OUT)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
