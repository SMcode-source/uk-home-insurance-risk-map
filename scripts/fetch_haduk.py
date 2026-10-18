"""Download HadUK-Grid DAILY gridded observations from CEDA (needs a token).

Gate 0 of the temperature-driven subsidence/freeze work. Two indices come
out of this data and they want opposite things from it:

  subsidence  an INTEGRAL. Clay shrink-swell tracks soil moisture deficit,
              which integrates potential evapotranspiration over months.
              Daily matters here only because Hargreaves-Samani PET uses
              the daily range (tasmax - tasmin) as a radiation proxy - the
              signal that separates a hot SUNNY summer, which cracks
              foundations, from a hot cloudy one, which does not.
  freeze      an EVENT DETECTOR. Pipes burst on the THAW after a spell
              deep enough to reach pipework in unheated voids, so what
              matters is runs of consecutive tasmin < 0, their accumulated
              severity, and how fast tasmax comes back up. A count of
              air-frost days - what the model uses today - cannot see any
              of that.

Both therefore need tasmin, tasmax and rainfall at DAILY resolution. The
model's existing frost/rain/precip layers are 1991-2020 CLIMATOLOGIES from
the Met Office Climate Data Portal (fetch_metoffice.py); they have no
year-to-year variation at all, which is exactly the gap this closes.

Period: 1960 on. That is not a round number chosen for tidiness - it is
how many severe freeze winters you get. 1990+ yields roughly four (2010,
2011, 2018, 2021); 1960+ adds 1963, 1979, 1982, 1986, 1987 and 1991,
which is the difference between FITTING the freeze event rate and
guessing it. Pre-1990 winters inform the HAZARD rate only; no claims
record reaches back that far.

Resolution: MEASURED 2026-08-29 against the 2,736 published districts,
because the choice is not a matter of taste - it decides whether a
per-district index exists at all.

    res    full 1960-2025 set   districts resolved   households sharing
                (3 variables)    (of 2,736)          a cell with another
    12 km        1.5 GB              1,175                 84%
     5 km        8.0 GB              2,131                 40%
     1 km        174 GB              2,694                  0%

12 km is a NATIONAL index and nothing finer: 84% of households sit in a
cell shared with another district, and one cell holds 89 of them. 5 km
is the working choice - it resolves 2,131 districts and fits. 1 km is
the only resolution that separates every district, and at 174 GB it did
not fit the disk it was measured on (113 GB free); it is also the least
worth having, since HadUK-Grid is interpolated from a station network
whose density, not the grid, sets the real resolution.

Per-file: 0.64 MB at 12 km, 3.36 MB at 5 km, 73.4 MB at 1 km - so 5 km
is 5.3x the volume of 12 km, not the ~14x this note claimed before
anyone measured it.

  1. log in at https://services.ceda.ac.uk/account/token/
  2. create an access token (they expire after ~72 h - fine, this is a
     one-shot bulk download, but see the expiry check below)
  3. save it as the only line of  %USERPROFILE%\\.ceda_token
     (or set the CEDA_TOKEN environment variable)

This script never prints the token and nothing here should either. It
DOES decode the token's public `exp` claim to say how long it has left,
because the classic failure mode is silent: an expired token 302s to a
login page and you end up with thousands of 8 KB HTML files saved under
.nc names, discovered only when xarray refuses to open them. Every
download is checked for the NetCDF/HDF5 magic bytes before it is written.

Resume-safe: existing validated files are skipped, so rerun after any
interruption (this machine sleeps mid-run).

Usage:
  fetch_haduk.py                          # 12km, tasmin+tasmax+rainfall, 1960-
  fetch_haduk.py --res 5km --from 1991    # relativity pass
  fetch_haduk.py --vars snowLying         # Gate 3's snow driver
  fetch_haduk.py --dry-run                # enumerate only, no token needed
"""

import argparse
import base64
import concurrent.futures
import datetime
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEST = os.path.join(ROOT, "data", "haduk")
BASE = ("https://dap.ceda.ac.uk/badc/ukmo-hadobs/data/insitu/MOHC/HadOBS/"
        "HadUK-Grid")
DEFAULT_VARS = ("tasmin", "tasmax", "rainfall")
MIN_YEAR = 1960
WORKERS = 4          # polite parallelism; CEDA is shared infrastructure
RETRIES = 6

HREF = re.compile(r'href="([^"?][^"]*)"')
# HadUK-Grid daily files are one calendar month each:
#   tasmin_hadukgrid_uk_12km_day_20101201-20101231.nc
DAYFILE = re.compile(r"_day_(\d{4})(\d{2})\d{2}-\d{8}\.nc$")
# Classic NetCDF is "CDF\x01"/"CDF\x02"; netCDF4 is HDF5, "\x89HDF".
NC_MAGIC = (b"CDF\x01", b"CDF\x02", b"\x89HDF")


def token():
    tok = os.environ.get("CEDA_TOKEN", "").strip()
    if not tok:
        path = os.path.join(os.path.expanduser("~"), ".ceda_token")
        if os.path.exists(path):
            with open(path) as fh:
                tok = fh.read().strip()
    if not tok:
        raise SystemExit(
            "no CEDA token. Create one at "
            "https://services.ceda.ac.uk/account/token/ and save it as "
            "the only line of ~/.ceda_token (or set CEDA_TOKEN).")
    return tok


def token_expiry(tok):
    """Public `exp` claim, or None if this is not a readable JWT.

    Only the expiry is ever surfaced. The token itself is never printed.
    """
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
        return datetime.datetime.fromtimestamp(exp, datetime.timezone.utc)
    except Exception:                     # noqa: BLE001 - shape is advisory
        return None


def check_token_age(tok):
    exp = token_expiry(tok)
    if exp is None:
        print("  token: not a readable JWT, will find out by trying",
              flush=True)
        return
    left = (exp - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if left <= 0:
        raise SystemExit(
            f"CEDA token EXPIRED {-left / 86400:.1f} days ago "
            f"(exp {exp:%Y-%m-%d %H:%M UTC}). CEDA tokens last ~72 h. "
            "Generate a new one at https://services.ceda.ac.uk/account/token/ "
            "and overwrite ~/.ceda_token. Nothing was downloaded.")
    print(f"  token: valid for {left / 3600:.1f} more hours", flush=True)
    if left < 3600:
        print("  WARNING: under an hour left. A long fetch will die "
              "part-way - it is resume-safe, but regenerate first.",
              flush=True)


def get(url, tok=None, tries=RETRIES):
    req = urllib.request.Request(url)
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:            # noqa: BLE001 - retried, then raised
            last = e
            time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"{url}: {last}")


def listing(url):
    return HREF.findall(get(url).decode("utf-8", "replace"))


def latest_version():
    """Newest vN.N.N.ceda release. Directory listings are anonymous."""
    vs = [h.strip("/") for h in listing(BASE + "/")
          if h.startswith("v") and h.endswith(".ceda/")]
    if not vs:
        raise SystemExit(f"no versioned HadUK-Grid directories under {BASE}")
    # "v1.3.2.ceda" -> (1, 3, 2); string sort would put v1.10 before v1.3
    return sorted(vs, key=lambda s: [int(p)
                                     for p in s.lstrip("v").split(".")[:3]])[-1]


def crawl(version, res, variables, year_from, year_to):
    """(url, relative path) for every daily file in range."""
    jobs = []
    for var in variables:
        root = f"{BASE}/{version}/{res}/{var}/day/"
        try:
            subs = [h for h in listing(root)
                    if h.startswith("v") and h.endswith("/")]
        except RuntimeError as exc:
            print(f"  {var}: no daily directory ({exc}) - skipped", flush=True)
            continue
        if not subs:
            print(f"  {var}: no dated release under {root} - skipped",
                  flush=True)
            continue
        rel = sorted(subs)[-1]
        n0 = len(jobs)
        for name in listing(root + rel):
            m = DAYFILE.search(name)
            if m and year_from <= int(m.group(1)) <= year_to:
                jobs.append((root + rel + name,
                             os.path.join(res, var, name)))
        print(f"  {var}: {len(jobs) - n0} files "
              f"({year_from}-{year_to}, release {rel.strip('/')})", flush=True)
    return jobs


def fetch_one(job, tok):
    url, rel = job
    path = os.path.join(DEST, rel)
    # A previously-poisoned HTML file is small; a real monthly grid is not.
    # Re-validate rather than trusting mere existence.
    if os.path.exists(path) and os.path.getsize(path) > 2048:
        with open(path, "rb") as fh:
            head = fh.read(8)
        if any(head.startswith(m) for m in NC_MAGIC):
            return "skip"
    body = get(url, tok)
    if not any(body.startswith(m) for m in NC_MAGIC):
        raise RuntimeError(
            f"{rel}: not NetCDF ({body[:16]!r}, {len(body)} bytes) - "
            "token expired or unauthorised? Nothing further was written.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(body)
    os.replace(tmp, path)                 # never leave a half file in place
    return "new"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--res", default="12km",
                    choices=["1km", "5km", "12km", "25km", "60km"])
    ap.add_argument("--vars", nargs="+", default=list(DEFAULT_VARS))
    ap.add_argument("--from", dest="year_from", type=int, default=MIN_YEAR)
    ap.add_argument("--to", dest="year_to", type=int, default=9999)
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate and size the job without a token")
    args = ap.parse_args()

    version = latest_version()
    print(f"HadUK-Grid {version}, {args.res}, {' '.join(args.vars)}",
          flush=True)
    jobs = crawl(version, args.res, args.vars, args.year_from, args.year_to)
    if not jobs:
        raise SystemExit("nothing to fetch - check --res / --vars / --from")
    have = sum(1 for _, rel in jobs
               if os.path.exists(os.path.join(DEST, rel)))
    print(f"{len(jobs)} files total, {have} already present, "
          f"{len(jobs) - have} to download", flush=True)
    if args.dry_run:
        print("dry run: nothing downloaded", flush=True)
        return

    tok = token()
    check_token_age(tok)
    # Fail fast on one file before launching the pool, so a bad token
    # costs one request rather than four threads of login pages.
    print(f"  probe: {os.path.basename(jobs[0][1])}", flush=True)
    fetch_one(jobs[0], tok)
    print("  token accepted", flush=True)

    done = skipped = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for res in pool.map(lambda j: fetch_one(j, tok), jobs):
            done += 1
            skipped += (res == "skip")
            if done % 100 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(jobs)} "
                      f"({skipped} already present, {rate:.1f}/s)", flush=True)
    mb = sum(os.path.getsize(os.path.join(DEST, rel)) for _, rel in jobs) / 1e6
    print(f"complete: {done} files ({skipped} already present), "
          f"{mb:.0f} MB under {DEST}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
