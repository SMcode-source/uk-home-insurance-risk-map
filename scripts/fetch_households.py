"""Households per postcode district, for exposure weighting.

Postcode districts are not an ONS geography, so households are built up
from census small areas:

  1. ONS "Postcode to OA/LSOA/MSOA/LAD" best-fit lookup (Open Geography
     Portal, OGL) gives every live UK postcode and its census small area.
     The outward half of the postcode IS the district, so no spatial join
     is needed.
  2. Household counts per small area:
       England & Wales - Census 2021 TS041 by LSOA   (NOMIS NM_2059_1)
       Scotland        - Census 2011 QS406UK by data zone (NOMIS NM_1553_1),
                         the most recent UK-wide table NOMIS carries
  3. Each small area's households are shared equally between the postcodes
     in it, then summed by district.

Northern Ireland is skipped - the boundary set is GB-only.

Output: data/households.csv (name, households, postcodes)
"""

import collections
import csv
import io
import json
import os
import re
import urllib.request
import zipfile

LOOKUP_ITEM = "3770c5e8b0c24f1dbe6d2fc6b46a0b18"
LOOKUP_URL = f"https://www.arcgis.com/sharing/rest/content/items/{LOOKUP_ITEM}/data"
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"
EW_URL = (f"{NOMIS}/NM_2059_1.data.csv?geography=TYPE151&measures=20100"
          "&select=geography_code,obs_value")
SCO_URL = (f"{NOMIS}/NM_1553_1.data.csv?geography=TYPE298&cell=0&measures=20100"
           "&select=geography_code,obs_value")

# Scotland's Census 2022 (National Records of Scotland): households with at
# least one usual resident. Used because NOMIS has no 2011-data-zone join.
SCOTLAND_HOUSEHOLDS = 2_509_300

CACHE = os.path.join("data", "cache")
OUT = os.path.join("data", "households.csv")


def cached(name, url, binary=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"  downloading {name} ...", flush=True)
        with urllib.request.urlopen(url, timeout=900) as r:
            data = r.read()
        with open(path, "wb") as fh:
            fh.write(data)
    return open(path, "rb").read() if binary else \
        open(path, encoding="utf-8-sig").read()


PAGE = 25_000        # NOMIS caps a single response at 25,000 records


def nomis_paged(tag, url):
    """NOMIS truncates silently at 25k rows - page until exhausted."""
    rows, offset = [], 0
    while True:
        text = cached(f"hh_{tag}_{offset}.csv", f"{url}&RecordOffset={offset}")
        page = list(csv.DictReader(io.StringIO(text)))
        rows.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return rows


def small_area_households():
    """-> {small area code: households}

    England & Wales from Census 2021; Scotland from the UK-wide 2011 table
    (NOMIS carries no 2022 Scottish census). The 2011 table also contains
    English and Welsh areas - they are ignored, so nothing is double
    counted and E&W always uses the newer figures.
    """
    hh = {}
    for row in nomis_paged("ew", EW_URL):
        code = row["GEOGRAPHY_CODE"].strip()
        if code[:1] in ("E", "W"):
            hh[code] = int(float(row["OBS_VALUE"]))
    print(f"  England & Wales (2021): {len(hh):,} LSOAs", flush=True)

    n_sco = 0
    for row in nomis_paged("sco", SCO_URL):
        code = row["GEOGRAPHY_CODE"].strip()
        if code.startswith("S"):                 # Scottish data zones only
            hh[code] = int(float(row["OBS_VALUE"]))
            n_sco += 1
    print(f"  Scotland (2011): {n_sco:,} data zones", flush=True)
    return hh


def postcode_rows():
    """Yield (outward_code, small_area_code) for every live GB postcode."""
    raw = cached("onspd_lookup.zip", LOOKUP_URL, binary=True)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    print(f"  lookup zip: {len(members)} CSV(s)", flush=True)
    for member in members:
        with zf.open(member) as fh:
            # ONS ships these as Latin-1 (Welsh/Gaelic place names); the
            # columns we need are pure ASCII, so decode leniently.
            reader = csv.reader(io.TextIOWrapper(
                fh, encoding="utf-8-sig", errors="replace"))
            header = next(reader)
            cols = {h.strip().lower(): i for i, h in enumerate(header)}
            pc_i = next((cols[c] for c in ("pcds", "pcd7", "pcd")
                         if c in cols), None)
            area_i = next((cols[c] for c in
                           ("lsoa21cd", "lsoa11cd", "lsoa21nm", "oa21cd")
                           if c in cols), None)
            # ONSPD retains TERMINATED postcodes - 897,835 of 2,694,205
            # rows, 33%. Apportioning LSOA household counts across them
            # dilutes every live postcode and credits ~730k homes to
            # addresses that no longer exist; the distortion is worst
            # where postcode churn is highest (rural and remote), which
            # is exactly where it showed up when the fix was priced.
            # Found via the sector build: dead postcodes have no
            # Code-Point centroid, so dead sectors got no polygon and
            # 2.7% of exposure had nowhere to land.
            term_i = cols.get("doterm")
            if pc_i is None or area_i is None:
                print(f"    skipping {member}: columns {header[:6]}",
                      flush=True)
                continue
            for row in reader:
                if len(row) <= max(pc_i, area_i):
                    continue
                pc, area = row[pc_i].strip(), row[area_i].strip()
                if not pc or not area or area.startswith("N"):
                    continue
                if term_i is not None and (row[term_i] or "").strip():
                    continue          # terminated: not a home, see above
                out = pc.split()[0] if " " in pc else pc[:-3].strip()
                if out:
                    yield out.upper(), area


def main():
    print("household counts by small area...", flush=True)
    hh = small_area_households()

    print("postcode lookup...", flush=True)
    per_area = collections.Counter()          # postcodes per small area
    pairs = []
    for out, area in postcode_rows():
        per_area[area] += 1
        pairs.append((out, area))
    print(f"  {len(pairs):,} postcodes, {len(per_area):,} small areas",
          flush=True)

    # Scotland: the lookup uses 2011 data zones (S01006506+) but NOMIS only
    # carries the 2001 vintage (S01000001-S01006505) for the UK-wide census
    # table, so there is no join. Scotland's Census 2022 national total is
    # spread evenly across Scottish postcodes instead - within Scotland this
    # makes a district's households proportional to its postcode count.
    n_scottish = sum(1 for _, area in pairs if area.startswith("S"))
    sco_per_pc = SCOTLAND_HOUSEHOLDS / n_scottish if n_scottish else 0.0
    print(f"  Scotland: {SCOTLAND_HOUSEHOLDS:,} households (Census 2022) "
          f"spread over {n_scottish:,} postcodes "
          f"= {sco_per_pc:.1f}/postcode", flush=True)

    district_hh = collections.defaultdict(float)
    district_pc = collections.Counter()
    missing = 0
    for out, area in pairs:
        district_pc[out] += 1
        if area in hh:
            district_hh[out] += hh[area] / per_area[area]
        elif area.startswith("S"):
            district_hh[out] += sco_per_pc
        else:
            missing += 1
    if missing:
        print(f"  {missing:,} postcodes still had no household figure "
              f"({missing / len(pairs):.1%})", flush=True)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "households", "postcodes"])
        for name in sorted(district_hh):
            w.writerow([name, round(district_hh[name]), district_pc[name]])
    total = sum(district_hh.values())
    print(f"wrote {OUT}: {len(district_hh):,} districts, "
          f"{total:,.0f} households total", flush=True)


if __name__ == "__main__":
    main()
