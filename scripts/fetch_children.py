"""Households with dependent children per postcode district, for the
accidental-damage peril's child-attributable slice.

AD is behavioural and has NO open incident-level driver (unlike fire).
What IS documented is that children cause 8%% of AD claims (Aviva,
Apr 2026 - DATA_SOURCES.md #28), so the frequency gets a flat base plus
a slice scaled by each district's share of households with dependent
children - the same flat-base-plus-documented-slice shape as escape of
water's freeze share. The census is the only open, current, GB-complete
source for that share:

  England & Wales - Census 2021 table TS003 (household composition) at
             LSOA 2021 grain via the NOMIS API (dataset NM_2023_1,
             geography TYPE151). Categories 5, 8, 10, 13 are the four
             "with dependent children" families (married, cohabiting,
             lone parent, other); 0 is all households. The API caps
             anonymous pulls at 25k rows, so pages are fetched with
             recordoffset until short.
  Scotland - Census 2022 table UV113 (household composition -
             households) at Output Area 2022 grain, from the
             scotlandscensus.gov.uk output-area bulk zip. Dependent-
             children columns are matched by header text ("dependent
             child" but not "non-dependent" - the non-dependent
             columns would otherwise match). "-" cells are zero.
             OA2022 does not exist in the ONSPD, so postcodes join via
             NRS's own Census_2022_Index Postcode_To_OA.csv, which
             also carries per-postcode household counts - those weight
             the apportionment where present (86%% of live postcodes);
             zero-count postcodes fall back to equal shares.

Both censuses define "dependent child" the same way (under 16, or
16-18 in full-time education living at home), so the shares are
comparable across the border.

Output: data/children.csv, one row per GB postcode district:
    name         district (e.g. YO8)
    hh_total     census households apportioned to the district
    hh_depchild  of which, households with dependent children

The model derives share = hh_depchild / hh_total; keeping both counts
committed makes conservation checkable (national sums must match the
census totals to the household).

Usage:
    python -u scripts/fetch_children.py
"""

import collections
import csv
import io
import os
import sys
import urllib.request
import zipfile

CACHE = os.path.join("data", "cache")
OUT = os.path.join("data", "children.csv")

# --- England & Wales: NOMIS census 2021 TS003 at LSOA 2021 ---
NOMIS_URL = ("https://www.nomisweb.co.uk/api/v01/dataset/NM_2023_1.data.csv"
             "?date=latest&geography=TYPE151"
             "&c2021_hhcomp_15=0,5,8,10,13&measures=20100"
             "&select=geography_code,c2021_hhcomp_15,obs_value")
NOMIS_PAGE = 25000            # anonymous row cap per request
DEPCHILD_CELLS = {"5", "8", "10", "13"}

# --- Scotland: census 2022 UV113 at Output Area 2022 ---
SCOT_ZIP_URL = ("https://www.scotlandscensus.gov.uk/media/"
                "zz85kfinmf97whklasd98gfkadft5hj4f_Topic2H_20241120_1747/"
                "Census-2022-Output-Area-v1.zip")
SCOT_TABLE = "UV113 - Household composition - Households.csv"
NRS_INDEX_URL = ("https://www.nrscotland.gov.uk/media/utrbt5ze/"
                 "census_2022_index.zip")
NRS_PC_TO_OA = "Census_2022_Index/Postcode_To_OA.csv"


def cached(name, url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"  downloading {name} ...", flush=True)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=900) as r:
            body = r.read()
        with open(path, "wb") as fh:
            fh.write(body)
    return path


def england_wales_lsoa():
    """-> {lsoa21cd: (total_hh, depchild_hh)} for England & Wales."""
    cache_csv = os.path.join(CACHE, "children_ew_lsoa.csv")
    if not os.path.exists(cache_csv):
        print("  downloading TS003 pages from NOMIS ...", flush=True)
        rows = []
        offset = 0
        while True:
            url = (f"{NOMIS_URL}&recordlimit={NOMIS_PAGE}"
                   f"&recordoffset={offset}")
            with urllib.request.urlopen(url, timeout=900) as r:
                page = list(csv.reader(
                    io.TextIOWrapper(r, encoding="utf-8-sig")))
            body = page[1:] if page and page[0] and \
                page[0][0].upper() == "GEOGRAPHY_CODE" else page
            rows.extend(body)
            print(f"    offset {offset}: {len(body)} rows", flush=True)
            if len(body) < NOMIS_PAGE:
                break
            offset += NOMIS_PAGE
        with open(cache_csv, "w", newline="") as fh:
            csv.writer(fh).writerows(rows)
    out = {}
    with open(cache_csv, newline="") as fh:
        for code, cell, value in csv.reader(fh):
            total, dep = out.get(code, (0, 0))
            v = int(value)
            if cell == "0":
                total += v
            elif cell in DEPCHILD_CELLS:
                dep += v
            out[code] = (total, dep)
    bad = [c for c, (t, d) in out.items() if d > t]
    assert not bad, f"dependent-children exceed total households: {bad[:5]}"
    return out


def scotland_oa():
    """-> {oa2022: (total_hh, depchild_hh)} from UV113."""
    path = cached("scot_census_oa_topic2h.zip", SCOT_ZIP_URL)
    with zipfile.ZipFile(path).open(SCOT_TABLE) as fh:
        reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
        header = None
        for row in reader:
            if len(row) > 3 and row[0] == "" and "All households" in row[1]:
                header = row
                break
        assert header, f"UV113 header not found in {SCOT_TABLE}"
        dep_cols = [i for i, h in enumerate(header)
                    if "dependent child" in h.lower()
                    and "non-dependent" not in h.lower()]
        assert len(dep_cols) == 8, \
            f"UV113 dependent-child columns changed: {len(dep_cols)}"
        total_col = header.index("All households")
        out = {}
        for row in reader:
            if not row or not row[0].startswith("S00"):
                continue
            def num(x):
                return 0 if x.strip() in ("-", "") else int(x)
            out[row[0]] = (num(row[total_col]),
                           sum(num(row[i]) for i in dep_cols))
    bad = [c for c, (t, d) in out.items() if d > t]
    assert not bad, f"dependent-children exceed total households: {bad[:5]}"
    return out


def ew_postcodes():
    """Yield (district, lsoa21cd) per live England/Wales postcode from
    the same cached ONS lookup fetch_households.py uses."""
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
            term_i = cols.get("doterm")
            for row in reader:
                if len(row) <= max(pc_i, area_i):
                    continue
                pc, area = row[pc_i].strip(), row[area_i].strip()
                if not pc or not (area.startswith("E") or
                                  area.startswith("W")):
                    continue
                if term_i is not None and (row[term_i] or "").strip():
                    continue
                # sector-model branch: key on "OUTWARD D", the same seam
                # fetch_households.py and fetch_fires.py carry here. The
                # inward code is ALWAYS the last three characters, however
                # the column pads ("YO25 6QP", "S1  1AA", fixed-width pcd7).
                compact = pc.replace(" ", "")
                if len(compact) < 5:
                    continue
                out, inward = compact[:-3], compact[-3:]
                yield f"{out.upper()} {inward[0]}", area


def scot_postcodes():
    """Yield (district, oa2022, hh_weight) per Scottish postcode from
    NRS's frozen Postcode_To_OA index (weight 0 handled by caller)."""
    path = cached("nrs_census_2022_index.zip", NRS_INDEX_URL)
    with zipfile.ZipFile(path).open(NRS_PC_TO_OA) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
        for r in reader:
            pc = r["Postcode"].strip()
            if not pc:
                continue
            # sector-model branch: key on "OUTWARD D" (see ew_postcodes).
            compact = pc.replace(" ", "")
            if len(compact) < 5:
                continue
            out, inward = compact[:-3], compact[-3:]
            yield (f"{out.upper()} {inward[0]}",
                   r["OutputArea2022Code"].strip(),
                   int(r["HouseholdCount"] or 0))


def main():
    print("England & Wales: TS003 LSOA counts...", flush=True)
    ew = england_wales_lsoa()
    t = sum(v[0] for v in ew.values())
    d = sum(v[1] for v in ew.values())
    print(f"  {len(ew):,} LSOAs, {t:,} households, "
          f"{d:,} with dependent children ({d / t:.1%})", flush=True)

    print("Scotland: UV113 OA counts...", flush=True)
    sco = scotland_oa()
    ts = sum(v[0] for v in sco.values())
    ds = sum(v[1] for v in sco.values())
    print(f"  {len(sco):,} OAs, {ts:,} households, "
          f"{ds:,} with dependent children ({ds / ts:.1%})", flush=True)

    district = collections.defaultdict(lambda: [0.0, 0.0])

    print("England & Wales postcode apportionment...", flush=True)
    per_lsoa_pc = collections.Counter()
    ew_pairs = []
    for out, area in ew_postcodes():
        per_lsoa_pc[area] += 1
        ew_pairs.append((out, area))
    matched = 0
    for out, area in ew_pairs:
        counts = ew.get(area)
        if counts:
            district[out][0] += counts[0] / per_lsoa_pc[area]
            district[out][1] += counts[1] / per_lsoa_pc[area]
            matched += 1
    print(f"  {matched:,} of {len(ew_pairs):,} postcodes joined",
          flush=True)

    print("Scotland postcode apportionment...", flush=True)
    # household-count weights where the OA has any; equal shares where
    # the frozen index zero-fills (PO boxes, new builds)
    per_oa = collections.defaultdict(lambda: [0, 0])   # [hh_wt, n_pc]
    sco_rows = []
    for out, oa, hh in scot_postcodes():
        per_oa[oa][0] += hh
        per_oa[oa][1] += 1
        sco_rows.append((out, oa, hh))
    matched = 0
    for out, oa, hh in sco_rows:
        counts = sco.get(oa)
        if not counts:
            continue
        hh_wt, n_pc = per_oa[oa]
        w = (hh / hh_wt) if hh_wt else (1 / n_pc)
        district[out][0] += counts[0] * w
        district[out][1] += counts[1] * w
        matched += 1
    print(f"  {matched:,} of {len(sco_rows):,} postcodes joined",
          flush=True)

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "hh_total", "hh_depchild"])
        for name in sorted(district):
            tot, dep = district[name]
            w.writerow([name, round(tot, 2), round(dep, 2)])
    gt = sum(v[0] for v in district.values())
    gd = sum(v[1] for v in district.values())
    print(f"wrote {OUT}: {len(district):,} districts, "
          f"{gt:,.0f} households, {gd:,.0f} with dependent children "
          f"({gd / gt:.1%})", flush=True)
    # conservation: apportionment must not create or destroy households
    exp = t + ts
    assert abs(gt - exp) / exp < 0.02, \
        f"household conservation broke: {gt:,.0f} vs census {exp:,.0f}"
    shares = sorted((v[1] / v[0], k) for k, v in district.items()
                    if v[0] > 500)
    print("lowest shares:", ", ".join(f"{n} {s:.1%}" for s, n in shares[:3]))
    print("highest shares:", ", ".join(f"{n} {s:.1%}"
                                       for s, n in shares[-3:]))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
