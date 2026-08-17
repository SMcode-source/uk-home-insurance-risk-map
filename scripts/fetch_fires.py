"""Dwelling fires per year per postcode district, for the fire peril.

Three sources, one per nation, each open (OGL) and each at the finest
geography that nation publishes (see DATA_SOURCES.md #27):

  England  - MHCLG (Home Office until Apr 2025) fire statistics
             incident-level "low level geography" datasets: one row per
             attended incident with LSOA code. Filter
             INCIDENT_TYPE == "Primary fire - dwelling" (dwellings are
             not split by motive at incident level; deliberate dwelling
             fires are insured and spatially informative, so all are
             kept). Two ODS files cover 2017/18 to present; 2025/26 is
             in progress with "Not known" LSOAs, so only COMPLETE
             financial years are counted (2017/18-2024/25, 8 years).
  Wales    - StatsWales "Primary fires by detailed location, motive,
             Fire and Rescue Authority and financial year"
             (bce9f348-...): Dwellings x All motives x 3 FRAs. The new
             stats.gov.wales platform has no plain download URL - the
             fetch replays the two-POST form flow (chooser=data, then
             the download form) and follows the redirect it returns.
             FRA -> local authority is the statutory 1996 three-way
             split, hardcoded below by LA name.
  Scotland - statistics.gov.scot "Fire - Type of Incident" cube CSV:
             Dwelling Fire x All accident status x 32 Council Areas
             (electoral-ward rows exist but wards aren't in the
             postcode lookup; council level is already 32x finer than
             theft's flat-Scotland fallback). Published to 2022/23.

Cross-checks at assembly time (2026-08-17): latest-year national sums
reconcile with Home Office FIRE0201 - Wales 1,432 = exact, Scotland
4,305 vs 4,304 (revision noise), England parsed from the same files
FIRE0201 summarises.

Counts are annualised PER GEOGRAPHY over that geography's own complete
window (England 8 yrs, Wales 8 yrs, Scotland 6 yrs 2017/18-2022/23),
then apportioned to postcode districts by postcode share via the same
ONS postcode->LSOA21/LAD lookup fetch_households.py uses (terminated
postcodes excluded there for exposure; here they are HARMLESS either
way because apportionment shares cancel within a geography, so the
lookup is read the same way for consistency). English incident LSOAs
that are 2011-vintage codes retired in 2021 fail the join - they are
counted, reported, and dropped (expected low single-digit %%).

The ODS files are parsed by streaming content.xml directly
(ElementTree.iterparse) - pandas' odf engine needs >10 min for even a
peek at these files; the stream does each in well under that. Parsed
LSOA counts are cached per file in data/cache/, so a mid-run sleep
costs one file, not the run.

Output: data/fires.csv, one row per GB postcode district:
    name      district (e.g. YO8)
    fires_yr  annualised dwelling fires apportioned to the district

Usage:
    python -u scripts/fetch_fires.py
"""

import collections
import csv
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

CACHE = os.path.join("data", "cache")
OUT = os.path.join("data", "fires.csv")

# --- England: incident-level low level geography datasets (ODS) ---
ENGLAND_FILES = {
    # complete financial years to keep from each file
    "fires_llg_201718_202223.ods": (
        "https://assets.publishing.service.gov.uk/media/"
        "6a5e77e94763c49e9be69412/"
        "Low_level_geography_dataset_201718_to_202223.ods",
        {"2017/18", "2018/19", "2019/20", "2020/21", "2021/22", "2022/23"},
    ),
    "fires_llg_202324_present.ods": (
        "https://assets.publishing.service.gov.uk/media/"
        "6a5e77c54763c49e9be69411/"
        "Low_level_geography_dataset_202324_to_present.ods",
        {"2023/24", "2024/25"},
    ),
}
ENGLAND_YEARS = 8
DWELLING_TYPE = "Primary fire - dwelling"

# --- Wales: stats.gov.wales dataset UUID and form flow ---
WALES_BASE = "https://stats.gov.wales/en-GB/bce9f348-d9aa-4490-8b6a-57aa6dee2afb"
WALES_YEARS = {"2017-18", "2018-19", "2019-20", "2020-21",
               "2021-22", "2022-23", "2023-24", "2024-25"}
# Statutory FRA composition (unchanged since 1996), by ONS LA name.
WALES_FRA = {
    "North Wales": {"Isle of Anglesey", "Gwynedd", "Conwy", "Denbighshire",
                    "Flintshire", "Wrexham"},
    "Mid & West Wales": {"Powys", "Ceredigion", "Pembrokeshire",
                         "Carmarthenshire", "Swansea", "Neath Port Talbot"},
    "South Wales": {"Bridgend", "Vale of Glamorgan", "Cardiff",
                    "Rhondda Cynon Taf", "Merthyr Tydfil", "Caerphilly",
                    "Blaenau Gwent", "Torfaen", "Monmouthshire", "Newport"},
}

# --- Scotland: statistics.gov.scot cube ---
SCOTLAND_URL = ("https://statistics.gov.scot/downloads/cube-table?uri="
                "http%3A%2F%2Fstatistics.gov.scot%2Fdata%2F"
                "fire---type-of-incident")
SCOTLAND_YEARS = {"2017/2018", "2018/2019", "2019/2020", "2020/2021",
                  "2021/2022", "2022/2023"}

TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def cached(name, url, data=None, headers=None):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"  downloading {name} ...", flush=True)
        req = urllib.request.Request(url, data=data, headers=headers or {})
        with urllib.request.urlopen(req, timeout=900) as r:
            body = r.read()
        with open(path, "wb") as fh:
            fh.write(body)
    return path


def ods_rows(path):
    """Yield rows (lists of cell strings) from every sheet of an ODS.

    Streams content.xml - the files are too slow for pandas' odf engine.
    Honours number-columns-repeated (capped at 32: ODS pads the final
    cell of a row to the sheet width, 16k) AND number-rows-repeated:
    incident data sorted by area/type compresses IDENTICAL consecutive
    rows, so ignoring row repeats silently dropped 39% of the dwelling
    fires on the first run - each yielded row therefore comes with its
    repeat count, (row, n).
    """
    z = zipfile.ZipFile(path)
    with z.open("content.xml") as fh:
        row = None
        row_rep = 1
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = el.tag
            if ev == "start" and tag == f"{{{TABLE}}}table-row":
                row = []
                row_rep = int(el.get(
                    f"{{{TABLE}}}number-rows-repeated", "1"))
            elif ev == "end" and tag == f"{{{TABLE}}}table-cell":
                if row is not None:
                    val = "".join(
                        (p.text or "") for p in el.iter(f"{{{TEXT}}}p"))
                    rep = int(el.get(
                        f"{{{TABLE}}}number-columns-repeated", "1"))
                    row.extend([val] * min(rep, 32))
                el.clear()
            elif ev == "end" and tag == f"{{{TABLE}}}table-row":
                if row and any(c for c in row):
                    yield row, row_rep
                row = None
                el.clear()
            elif ev == "end" and tag == f"{{{TABLE}}}table":
                el.clear()


def england_lsoa_counts():
    """-> {lsoa_code: dwelling fires over ENGLAND_YEARS complete years}"""
    counts = collections.Counter()
    for name, (url, keep_years) in ENGLAND_FILES.items():
        cache_csv = os.path.join(CACHE, name.replace(".ods", "_lsoa.csv"))
        if os.path.exists(cache_csv):
            with open(cache_csv) as fh:
                for code, n in csv.reader(fh):
                    counts[code] += int(n)
            print(f"  {name}: cached", flush=True)
            continue
        path = cached(name, url)
        file_counts = collections.Counter()
        kept = dropped_year = 0
        cols = None
        for row, n in ods_rows(path):
            if cols is None or "LSOA_CODE" in row:
                if "LSOA_CODE" in row and "INCIDENT_TYPE" in row:
                    cols = (row.index("LSOA_CODE"),
                            row.index("FINANCIAL_YEAR"),
                            row.index("INCIDENT_TYPE"))
                continue
            if len(row) <= max(cols):
                continue
            if row[cols[2]] != DWELLING_TYPE:
                continue
            if row[cols[1]] not in keep_years:
                dropped_year += n
                continue
            file_counts[row[cols[0]]] += n
            kept += n
        with open(cache_csv, "w", newline="") as fh:
            w = csv.writer(fh)
            for code, n in sorted(file_counts.items()):
                w.writerow([code, n])
        counts.update(file_counts)
        print(f"  {name}: {kept:,} dwelling fires kept, "
              f"{dropped_year:,} outside complete years", flush=True)
    return counts


def wales_fra_counts():
    """-> {fra name: annual dwelling fires} via the stats.gov.wales
    two-POST form flow (see module docstring)."""
    cache_csv = os.path.join(CACHE, "fires_wales.csv")
    if not os.path.exists(cache_csv):
        print("  downloading fires_wales.csv (form flow) ...", flush=True)
        import http.cookiejar
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        opener.open(f"{WALES_BASE}/start", timeout=120).read()
        opener.open(f"{WALES_BASE}/filtered",
                    urllib.parse.urlencode({"chooser": "data"}).encode(),
                    timeout=300).read()
        form = urllib.parse.urlencode({
            "view_type": "unfiltered", "format": "csv",
            "view_choice": "raw", "extended": "no",
            "download_language": "en-GB", "selected_filter_options": "[]",
        }).encode()
        body = opener.open(f"{WALES_BASE}/download", form, timeout=600).read()
        if not body.lstrip()[:40].startswith(b"Data values"):
            raise RuntimeError("stats.gov.wales flow changed: "
                               f"got {body[:80]!r}")
        with open(cache_csv, "wb") as fh:
            fh.write(body)
    fras = collections.defaultdict(float)
    years = set()
    with open(cache_csv, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r["Location type"] == "Dwellings"
                    and r["Motive"] == "All motives"
                    and r["Fire and Rescue Authority area"] in WALES_FRA
                    and r["Financial year"] in WALES_YEARS):
                fras[r["Fire and Rescue Authority area"]] += \
                    float(r["Data values"])
                years.add(r["Financial year"])
    assert years == WALES_YEARS, f"Wales years missing: {WALES_YEARS - years}"
    return {fra: total / len(WALES_YEARS) for fra, total in fras.items()}


def scotland_lad_counts():
    """-> {S12... council ladcd: annual dwelling fires}"""
    path = cached("fires_scotland.csv", SCOTLAND_URL)
    lads = collections.defaultdict(float)
    years = set()
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r["Type of Fire"] == "Dwelling Fire"
                    and r["Accident Status"] == "All"
                    and r["FeatureType"] == "Council Area"
                    and r["DateCode"] in SCOTLAND_YEARS):
                lads[r["FeatureCode"]] += float(r["Value"])
                years.add(r["DateCode"])
    assert years == SCOTLAND_YEARS, \
        f"Scotland years missing: {SCOTLAND_YEARS - years}"
    return {lad: total / len(SCOTLAND_YEARS) for lad, total in lads.items()}


def postcode_geographies():
    """Yield (district, lsoa21_or_datazone, ladcd, ladnm) per live GB
    postcode, from the same cached lookup fetch_households.py uses."""
    from fetch_households import LOOKUP_URL
    raw_path = cached("onspd_lookup.zip", LOOKUP_URL)
    zf = zipfile.ZipFile(raw_path)
    members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    for member in members:
        with zf.open(member) as fh:
            reader = csv.reader(io.TextIOWrapper(
                fh, encoding="utf-8-sig", errors="replace"))
            header = next(reader)
            cols = {h.strip().lower(): i for i, h in enumerate(header)}
            pc_i, area_i = cols["pcds"], cols["lsoa21cd"]
            lad_i, ladnm_i, term_i = (cols["ladcd"], cols["ladnm"],
                                      cols.get("doterm"))
            for row in reader:
                if len(row) <= max(pc_i, area_i, lad_i, ladnm_i):
                    continue
                pc, area = row[pc_i].strip(), row[area_i].strip()
                if not pc or area.startswith("N"):
                    continue
                if term_i is not None and (row[term_i] or "").strip():
                    continue
                out = pc.split()[0] if " " in pc else pc[:-3].strip()
                if out:
                    yield (out.upper(), area,
                           row[lad_i].strip(), row[ladnm_i].strip())


def main():
    print("England: incident-level LSOA counts...", flush=True)
    eng = england_lsoa_counts()
    print(f"  {sum(eng.values()):,} dwelling fires over {ENGLAND_YEARS} "
          f"years in {len(eng):,} LSOAs", flush=True)

    print("Wales: FRA counts...", flush=True)
    wal = wales_fra_counts()
    print("  " + ", ".join(f"{k} {v:.0f}/yr" for k, v in sorted(wal.items())),
          flush=True)

    print("Scotland: council counts...", flush=True)
    sco = scotland_lad_counts()
    print(f"  {sum(sco.values()):,.0f} dwelling fires/yr over "
          f"{len(sco)} councils", flush=True)

    fra_by_ladnm = {nm: fra for fra, names in WALES_FRA.items()
                    for nm in names}

    print("postcode lookup...", flush=True)
    per_key_pc = collections.Counter()    # postcodes per geography key
    pairs = []
    welsh_unmapped = set()
    for out, area, ladcd, ladnm in postcode_geographies():
        if area.startswith("E"):
            key = ("lsoa", area)
        elif ladcd.startswith("S"):
            key = ("lad", ladcd)
        elif ladcd.startswith("W"):
            fra = fra_by_ladnm.get(ladnm)
            if fra is None:
                welsh_unmapped.add(ladnm)
                continue
            key = ("fra", fra)
        else:
            continue
        per_key_pc[key] += 1
        pairs.append((out, key))
    assert not welsh_unmapped, f"unmapped Welsh LAs: {welsh_unmapped}"
    print(f"  {len(pairs):,} postcodes", flush=True)

    # annual fires per geography key
    rate = {}
    matched_eng = 0
    for code, n in eng.items():
        if ("lsoa", code) in per_key_pc:
            rate[("lsoa", code)] = n / ENGLAND_YEARS
            matched_eng += n
    dropped = sum(eng.values()) - matched_eng
    print(f"  England LSOAs joined: {matched_eng:,} fires kept, "
          f"{dropped:,} in retired 2011-vintage codes "
          f"({dropped / sum(eng.values()):.1%})", flush=True)
    sco_unjoined = [lad for lad in sco if ("lad", lad) not in per_key_pc]
    assert not sco_unjoined, \
        f"Scottish council codes not in lookup: {sco_unjoined}"
    for lad, v in sco.items():
        rate[("lad", lad)] = v
    for fra, v in wal.items():
        rate[("fra", fra)] = v

    district = collections.defaultdict(float)
    for out, key in pairs:
        f = rate.get(key)
        if f:
            district[out] += f / per_key_pc[key]

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "fires_yr"])
        for name in sorted(district):
            w.writerow([name, round(district[name], 4)])
    total = sum(district.values())
    print(f"wrote {OUT}: {len(district):,} districts, "
          f"{total:,.0f} dwelling fires/yr placed", flush=True)
    top = sorted(district.items(), key=lambda kv: -kv[1])[:5]
    print("highest districts:", ", ".join(f"{n} {v:.0f}" for n, v in top))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
