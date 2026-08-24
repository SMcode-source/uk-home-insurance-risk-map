"""Non-domestic premises per postcode district, from the VOA's
NDR stock-of-properties LSOA tables (DATA_SOURCES.md #29).

Purpose: the police.uk "Burglary" category includes commercial
break-ins, so district burglary rates carry shops and offices in the
numerator while only households sit in the denominator. Dividing by
(households + non-domestic premises) instead attributes each district
its residential share - the "proper fix" the theft section promised,
replacing crude duty the p99.9 winsorisation cap was doing for
commercial cores (the cap itself stays, as a backstop for
tiny-denominator districts).

Source: ndr_stock_oa_2025.zip from the VOA "Non-domestic rating:
stock of properties 2025" release (OGL v3, no registration).
SOP_OA_counts_all.csv carries counts by year at LSOA grain for
England & Wales; the 2025 column is the 31 March 2025 snapshot.
Counts are rounded to the nearest 10 and small counts are suppressed
(non-numeric cells) - suppressed cells are treated as 0, which
under-counts by at most a handful of premises in the emptiest LSOAs.

Scotland is deliberately absent: VOA covers England & Wales only, and
the theft peril overrides Scotland with a flat national housebreaking
rate anyway, so a commercial correction there would adjust nothing.

The LSOA vintage is not documented in the CSV itself, so the
apportionment matches the file's codes against BOTH the 2011 and 2021
LSOA columns of the ONS postcode lookup and uses whichever vintage
covers more premises - and then asserts the winner covers >=97% of
them, so a boundary-revision drift fails loudly instead of silently
dropping premises.
"""

import collections
import csv
import io
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
sys.path.insert(0, HERE)

NDR_URL = ("https://assets.publishing.service.gov.uk/media/"
           "684fd3ad928e5ebb68e3fa39/ndr_stock_oa_2025.zip")
NDR_MEMBER = "ndr_stock_oa_2025/SOP_OA_counts_all.csv"
YEAR = "2025"


def cached(name, url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        return path
    import urllib.request
    print(f"  downloading {name}...", flush=True)
    urllib.request.urlretrieve(url, path)
    return path


def lsoa_premises():
    """{lsoa_code: premises count} for E&W at 31 March 2025."""
    path = cached("ndr_stock_oa_2025.zip", NDR_URL)
    counts, suppressed = {}, 0
    with zipfile.ZipFile(path).open(NDR_MEMBER) as fh:
        reader = csv.DictReader(io.TextIOWrapper(
            fh, encoding="utf-8-sig", errors="replace"))
        for row in reader:
            if row["geography"] != "LSOA":
                continue
            cell = (row[YEAR] or "").strip()
            try:
                n = float(cell)
            except ValueError:
                suppressed += 1     # '[c]' etc: fewer than 5 premises
                n = 0.0
            counts[row["area_code"].strip()] = n
    print(f"  {len(counts):,} LSOAs, {sum(counts.values()):,.0f} premises "
          f"({suppressed} suppressed cells treated as 0)", flush=True)
    return counts


def postcode_lsoa_pairs():
    """Yield (district, lsoa11cd, lsoa21cd) per live E&W postcode from
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
            pc_i = cols["pcds"]
            l11_i, l21_i = cols.get("lsoa11cd"), cols["lsoa21cd"]
            term_i = cols.get("doterm")
            for row in reader:
                if len(row) <= max(i for i in (pc_i, l11_i, l21_i)
                                   if i is not None):
                    continue
                pc = row[pc_i].strip()
                l21 = row[l21_i].strip()
                if not pc or not (l21.startswith("E") or
                                  l21.startswith("W")):
                    continue
                if term_i is not None and (row[term_i] or "").strip():
                    continue          # terminated: not an address
                out = pc.split()[0] if " " in pc else pc[:-3].strip()
                if not out:
                    continue
                l11 = row[l11_i].strip() if l11_i is not None else ""
                yield out.upper(), l11, l21


def main():
    print("NDR stock: LSOA premises counts...", flush=True)
    prem = lsoa_premises()
    total = sum(prem.values())

    print("postcode apportionment...", flush=True)
    pc_11 = collections.Counter()      # postcodes per LSOA, each vintage
    pc_21 = collections.Counter()
    pairs = []
    for out, l11, l21 in postcode_lsoa_pairs():
        pc_11[l11] += 1
        pc_21[l21] += 1
        pairs.append((out, l11, l21))

    cover_11 = sum(v for k, v in prem.items() if k in pc_11)
    cover_21 = sum(v for k, v in prem.items() if k in pc_21)
    vintage = 11 if cover_11 >= cover_21 else 21
    covered = max(cover_11, cover_21)
    print(f"  vintage match: 2011 covers {cover_11 / total:.1%}, "
          f"2021 covers {cover_21 / total:.1%} of premises "
          f"-> using LSOA20{vintage}", flush=True)
    assert covered / total >= 0.97, (
        f"best LSOA vintage covers only {covered / total:.1%} of premises "
        "- boundary revision? Inspect area codes before trusting output")

    district = collections.defaultdict(float)
    for out, l11, l21 in pairs:
        code = l11 if vintage == 11 else l21
        per_pc = pc_11 if vintage == 11 else pc_21
        n = prem.get(code)
        if n:
            district[out] += n / per_pc[code]

    placed = sum(district.values())
    print(f"  {placed:,.0f} of {total:,.0f} premises placed "
          f"({placed / total:.1%}) across {len(district):,} districts",
          flush=True)
    # premises in LSOAs with no live postcode (fully commercial islands
    # do exist) are the remainder; they belong to no household district.
    assert placed / total >= 0.97, "apportionment lost too many premises"

    out_path = os.path.join(DATA, "premises.csv")
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "premises"])
        for name in sorted(district):
            w.writerow([name, f"{district[name]:.1f}"])
    print(f"wrote {out_path}: {len(district):,} districts, "
          f"{placed:,.0f} premises", flush=True)

    top = sorted(district.items(), key=lambda kv: -kv[1])[:5]
    print("  most commercial:",
          ", ".join(f"{n} {v:,.0f}" for n, v in top), flush=True)


if __name__ == "__main__":
    main()
