"""Council-tax band mix per postcode district, as a severity relativity
(DATA_SOURCES.md #30).

Purpose: council-tax bands are the only full-stock, small-area,
OGL-licensed proxy for property value in Great Britain. A district
whose stock sits in the upper bands holds more rebuild cost and more
contents value per household than a bottom-band district, so the flat
national severities behind the attritional perils overstate cheap
areas and understate dear ones. This script turns each district's
band mix into a single value relativity, exposure-normalised to 1.0,
for the model to apply to severity.

CRITICAL TRAP (recorded in HANDOFF's Phase 2 plan): the three nations'
band letters are incompatible regimes - England A-H on 1991 values,
Wales A-I on 2003 values, Scotland A-H on 1991 values with its own
post-2017 multiplier ratios. A band-D Welsh home is not a band-D
English home. So band weights are the STATUTORY charge ratios of each
nation's own regime, and the weight is normalised WITHIN nation to a
dwelling-weighted mean of 1.0 before any district (some straddle the
English-Welsh border) averages over its small areas.

Sources (both OGL v3, no registration):
- CTSOP1.1, VOA, snapshot 31 March 2025: dwelling counts by band at
  LSOA grain for England & Wales. Counts rounded to nearest 10, cells
  under 5 suppressed as "-" (treated as 0), band I is ".." outside
  Wales.
- "Dwellings by Council Tax Band Detailed", NRS via
  statistics.gov.scot: band x 2011 data zone. YEAR 2023 ONLY - the
  2024 sheet switches to 2022 data zones, which the postcode lookup
  cannot join.

Geography join: the cached ONS postcode lookup (Aug 2023 member) has
ONLY a lsoa21cd column - and for Scotland that column carries the
2011 data zones (S01...), because Scotland had no 2021 census small
areas. So one column joins both nations' codes; coverage is asserted
>=97% separately for E&W and Scotland, so a CTSOP vintage change or a
lookup refresh that swaps Scotland to 2022 data zones fails loudly
instead of silently zeroing a nation.
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

CTSOP_URL = ("https://assets.publishing.service.gov.uk/media/"
             "6a0ad444c75cc34a8ff8f397/CTSOP1.1.zip")
CTSOP_MEMBER = "CTSOP1.1/CTSOP1_1_2025_03_31.csv"
SCOT_URL = ("https://statistics.gov.scot/downloads/file?id="
            "c0c89950-ae25-48c1-b806-c6a759a211c5%2F"
            "Dwellings+by+Council+Tax+Band+Detailed.zip")
SCOT_MEMBER = ("Dwellings by Council Tax Band Detailed/"
               "dwellings-by-band-DZ-2023.csv")

# Statutory charge ratios relative to band D, per nation's own regime.
# England & Wales: LGFA 1992 s.5 (Wales adds band I, 21/9, from 2005).
# Scotland: LGF(S)A 1992 as amended 2017 - E-H were raised, so the
# Scottish spread is deliberately steeper in the upper bands.
WEIGHTS = {
    "E": {"a": 6 / 9, "b": 7 / 9, "c": 8 / 9, "d": 1.0, "e": 11 / 9,
          "f": 13 / 9, "g": 15 / 9, "h": 18 / 9},
    "W": {"a": 6 / 9, "b": 7 / 9, "c": 8 / 9, "d": 1.0, "e": 11 / 9,
          "f": 13 / 9, "g": 15 / 9, "h": 18 / 9, "i": 21 / 9},
    "S": {"a": 240 / 360, "b": 280 / 360, "c": 320 / 360, "d": 1.0,
          "e": 473 / 360, "f": 585 / 360, "g": 705 / 360,
          "h": 882 / 360},
}
BAND_COLS = ["band_" + b for b in "abcdefghi"]


def cached(name, url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        return path
    import urllib.request
    print(f"  downloading {name}...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(path, "wb") as fh:
        fh.write(r.read())
    return path


def _num(cell):
    """CTSOP cell -> float. '-' (suppressed <5) and '..' (n/a) -> 0."""
    cell = (cell or "").strip()
    try:
        return float(cell)
    except ValueError:
        return 0.0


def ew_small_areas():
    """{lsoa_code: (dwelling_count, value_weight)} for England & Wales.
    value_weight is the band-ratio mean of the area's stock, in its
    own nation's regime (unnormalised at this point)."""
    path = cached("CTSOP1_1.zip", CTSOP_URL)
    areas = {}
    with zipfile.ZipFile(path).open(CTSOP_MEMBER) as fh:
        reader = csv.DictReader(io.TextIOWrapper(
            fh, encoding="utf-8-sig", errors="replace"))
        for row in reader:
            if row["geography"] != "LSOA":
                continue
            code = row["ecode"].strip()
            nation = code[:1]           # E01... or W01...
            weights = WEIGHTS.get(nation)
            if weights is None:
                continue
            counts = {b[-1]: _num(row[b]) for b in BAND_COLS}
            n = sum(counts.values())
            if n <= 0:
                continue
            w = sum(counts[b] * weights.get(b, 0.0)
                    for b in counts) / n
            areas[code] = (n, w, nation)
    print(f"  CTSOP1.1: {len(areas):,} LSOAs, "
          f"{sum(a[0] for a in areas.values()):,.0f} dwellings", flush=True)
    return areas


def scot_small_areas():
    """{dz2011_code: (dwelling_count, value_weight, 'S')} for Scotland,
    year 2023 (last year on 2011 data zones)."""
    path = cached("scot_ct_bands.zip", SCOT_URL)
    counts = collections.defaultdict(dict)
    with zipfile.ZipFile(path).open(SCOT_MEMBER) as fh:
        reader = csv.DictReader(io.TextIOWrapper(
            fh, encoding="utf-8-sig", errors="replace"))
        for row in reader:
            code = row["Geography_Code"].strip()
            if not code.startswith("S01"):
                continue                # skip council-area etc rollups
            band = row["Council Tax Band"].strip().lower()
            if not band.startswith("band "):
                continue                # skip "Total" rows
            letter = band.split()[-1]
            if letter not in WEIGHTS["S"]:
                continue
            counts[code][letter] = _num(row["Value"])
    areas = {}
    for code, by_band in counts.items():
        n = sum(by_band.values())
        if n <= 0:
            continue
        w = sum(v * WEIGHTS["S"][b] for b, v in by_band.items()) / n
        areas[code] = (n, w, "S")
    print(f"  Scotland 2023: {len(areas):,} data zones, "
          f"{sum(a[0] for a in areas.values()):,.0f} dwellings", flush=True)
    return areas


def postcode_rows():
    """Yield (district, small_area_code) per live GB postcode from the
    same cached ONS lookup fetch_households.py uses. The lsoa21cd
    column holds E&W 2021 LSOAs and Scottish 2011 data zones alike."""
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
            l21_i = cols["lsoa21cd"]
            term_i = cols.get("doterm")
            for row in reader:
                if len(row) <= max(pc_i, l21_i):
                    continue
                pc = row[pc_i].strip()
                if not pc:
                    continue
                if term_i is not None and (row[term_i] or "").strip():
                    continue          # terminated: not an address
                code = row[l21_i].strip()
                if code[:3] not in ("E01", "W01", "S01"):
                    continue
                # sector-model branch: key on "OUTWARD D", exactly as
                # fetch_households.py does. The inward code is ALWAYS
                # the last three characters, however the column pads
                # ("YO25 6QP", "S1  1AA", fixed-width pcd7) - splitting
                # on whitespace does not survive the padded variants.
                compact = pc.replace(" ", "")
                if len(compact) < 5:
                    continue
                out, inward = compact[:-3], compact[-3:]
                yield f"{out.upper()} {inward[0]}", code


def main():
    print("council-tax band mix: small areas...", flush=True)
    areas = ew_small_areas()
    areas.update(scot_small_areas())

    # Normalise the value weight WITHIN nation to dwelling-weighted
    # mean 1.0, so the three incompatible band regimes never compare.
    for nation in "EWS":
        nat = [(n, w) for n, w, nt in areas.values() if nt == nation]
        tot = sum(n for n, _ in nat)
        mean = sum(n * w for n, w in nat) / tot
        for code, (n, w, nt) in list(areas.items()):
            if nt == nation:
                areas[code] = (n, w / mean, nt)
        print(f"  nation {nation}: mean band-weight {mean:.4f} "
              f"over {tot:,.0f} dwellings -> normalised to 1.0", flush=True)

    print("postcode apportionment...", flush=True)
    per_code = collections.Counter()         # live postcodes per area
    pairs = []
    for out, code in postcode_rows():
        per_code[code] += 1
        pairs.append((out, code))

    for nation, label in [("EW", "E&W LSOA2021"), ("S", "Scotland DZ2011")]:
        tot = sum(n for code, (n, w, nt) in areas.items()
                  if (nt == "S") == (nation == "S"))
        cov = sum(n for code, (n, w, nt) in areas.items()
                  if (nt == "S") == (nation == "S") and code in per_code)
        print(f"  {label} coverage: {cov / tot:.1%}", flush=True)
        assert cov / tot >= 0.97, f"{label} join failed - vintage change?"

    dw = collections.defaultdict(float)      # dwellings per district
    wsum = collections.defaultdict(float)    # weight x dwellings
    for out, code in pairs:
        rec = areas.get(code)
        if rec is None:
            continue
        n, w, _ = rec
        share = n / per_code[code]
        dw[out] += share
        wsum[out] += share * w

    placed = sum(dw.values())
    total = sum(n for n, w, nt in areas.values())
    print(f"  {placed:,.0f} of {total:,.0f} dwellings placed "
          f"({placed / total:.1%}) across {len(dw):,} districts", flush=True)
    assert placed / total >= 0.97, "apportionment lost too many dwellings"

    out_path = os.path.join(DATA, "ct_bands.csv")
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "sev_rel", "dwellings"])
        for name in sorted(dw):
            w.writerow([name, f"{wsum[name] / dw[name]:.4f}",
                        f"{dw[name]:.0f}"])
    print(f"wrote {out_path}: {len(dw):,} districts", flush=True)

    rel = {n: wsum[n] / dw[n] for n in dw}
    top = sorted(rel.items(), key=lambda kv: -kv[1])[:5]
    bot = sorted(rel.items(), key=lambda kv: kv[1])[:5]
    print("  dearest:", ", ".join(f"{n} {v:.2f}" for n, v in top),
          flush=True)
    print("  cheapest:", ", ".join(f"{n} {v:.2f}" for n, v in bot),
          flush=True)


if __name__ == "__main__":
    main()
