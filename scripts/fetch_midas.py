"""Download MIDAS Open uk-mean-wind-obs from CEDA (needs an access token).

CEDA's directory listings are anonymous but every file GET 302s to
"Unauthenticated" without credentials. The supported programmatic route
is a bearer token, which the ACCOUNT HOLDER generates:

  1. log in at https://services.ceda.ac.uk/account/token/
  2. create an access token (they expire after ~72 h - fine, this is a
     one-shot bulk download)
  3. save it as the only line of  %USERPROFILE%\\.ceda_token
     (or set the CEDA_TOKEN environment variable)

This script never prints the token and nothing here should either.

Scope: the latest dataset-version, qc-version-1 yearly files from
MIN_YEAR on (the processor's Gumbel gate needs 20 good years; 1970+
leaves headroom without doubling the volume), plus the dataset-level
station-metadata capability file. Layout under data/midas/ mirrors the
archive, which is exactly what gusts_from_midas.py walks.

Resume-safe: existing validated files are skipped, so rerun after any
interruption (this machine sleeps mid-run). Every downloaded file is
checked to START like BADC-CSV — an expired token yields tiny HTML
bodies, and the classic failure is 15,000 copies of a login page saved
under .csv names, discovered only at parse time.
"""

import concurrent.futures
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEST = os.path.join(ROOT, "data", "midas", "uk-mean-wind-obs")
BASE = "https://dap.ceda.ac.uk/badc/ukmo-midas-open/data/uk-mean-wind-obs"
MIN_YEAR = 1970
WORKERS = 4          # polite parallelism; CEDA is not BGS but is shared
RETRIES = 6

HREF = re.compile(r'href="([^"?][^"]*)"')


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


def get(url, tok=None, tries=RETRIES):
    req = urllib.request.Request(url)
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:            # noqa: BLE001 - retried, then raised
            last = e
            time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"{url}: {last}")


def listing(url):
    return HREF.findall(get(url).decode("utf-8", "replace"))


def crawl(version):
    """All qcv-1 yearly files for MIN_YEAR+, as (url, relative path)."""
    root = f"{BASE}/{version}"
    files = [(f"{root}/midas-open_uk-mean-wind-obs_{version.replace('dataset-version-', 'dv-')}_station-metadata.csv",
              "station-metadata.csv")]
    counties = [h for h in listing(root + "/") if h.endswith("/") and h != "../"]
    for county in counties:
        for station in listing(f"{root}/{county}"):
            if not station.endswith("/") or station == "../":
                continue
            qdir = f"{root}/{county}{station}qc-version-1/"
            for name in listing(qdir):
                m = re.search(r"_qcv-1_(\d{4})\.csv$", name)
                if m and int(m.group(1)) >= MIN_YEAR:
                    files.append((qdir + name,
                                  os.path.join(county.strip("/"),
                                               station.strip("/"), name)))
        print(f"  crawled {county.strip('/')}: {len(files)} files so far",
              flush=True)
    return files


def fetch_one(job, tok):
    url, rel = job
    path = os.path.join(DEST, rel)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return "skip"
    body = get(url, tok)
    # An expired/wrong token gets an HTML page or "Unauthenticated", not
    # BADC-CSV. Refuse to write it - a poisoned tree parses as zero
    # stations much later, with no hint why.
    if not body.lstrip()[:60].startswith(b"Conventions,G,BADC-CSV"):
        raise RuntimeError(
            f"{rel}: response is not BADC-CSV ({body[:40]!r}) - "
            f"token expired or unauthorised?")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(body)
    return "new"


def main():
    tok = token()
    versions = [h.strip("/") for h in listing(BASE + "/")
                if h.startswith("dataset-version-")]
    version = sorted(versions)[-1]
    print(f"dataset version: {version}", flush=True)

    # fail fast on a bad token: one known-small file before crawling
    probe = crawl_probe = (
        f"{BASE}/{version}/midas-open_uk-mean-wind-obs_"
        f"{version.replace('dataset-version-', 'dv-')}_station-metadata.csv")
    body = get(crawl_probe, tok)
    if not body.lstrip()[:60].startswith(b"Conventions,G,BADC-CSV"):
        raise SystemExit("token rejected (probe file came back as "
                         f"{body[:40]!r}). Recreate it and retry.")
    print("token accepted", flush=True)

    files = crawl(version)
    print(f"{len(files)} files to mirror (>= {MIN_YEAR})", flush=True)

    done = skipped = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for res in pool.map(lambda j: fetch_one(j, tok), files):
            done += 1
            skipped += (res == "skip")
            if done % 500 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(files)} "
                      f"({skipped} already present, {rate:.0f}/s)",
                      flush=True)
    print(f"complete: {done} files ({skipped} were already present) "
          f"under {DEST}", flush=True)
    print("next: .venv/Scripts/python scripts/gusts_from_midas.py "
          "data/midas/uk-mean-wind-obs", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
