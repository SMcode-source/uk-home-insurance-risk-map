"""Recorded housebreaking by Scottish council area, apportioned to the
model's postcode districts.

WHY THIS EXISTS. police.uk has no Scottish forces, so
`scores_real.theft_from_police` overrides all 442 Scottish districts
with ONE national rate - 7,381 housebreakings over the model's Scottish
households, 0.295%/yr, the same number everywhere from Shetland to
central Edinburgh. That is the largest remaining geography gap in a
peril worth 13.43% of claim cost (LIMITATIONS sections 5 and 7).

Scotland does publish the counts by council area, free and open:
statistics.gov.scot's `recorded-crime` cube, "Crimes: Group 3:
Housebreaking", 32 council areas, 1996/1997 onward. The 32 councils sum
to exactly the 7,381 in Recorded Crime in Scotland Table A6, so this is
the SAME measurement disaggregated, not a different series. What it buys
is a 32-value step function where the model currently has one value -
far coarser than E&W's street-level points, but 13.5x of range where
there is currently none.

APPORTIONMENT. Councils and postcode districts do not nest, so each
council's count is split across districts in proportion to the
HOUSEHOLDS each district contributes to that council:

    hh_share[d][L] = households[d] * postcodes(d in L) / postcodes(d)
    H[L]           = sum over d of  hh_share[d][L]
    hb[d]          = sum over L of  HB[L] * hh_share[d][L] / H[L]

Households, not postcode counts, because burglaries happen to dwellings
and a rural postcode is not a dwelling's worth of exposure. (fetch_fires
apportions Scottish council fires by postcode COUNT; this is the same
join with a better weight, and the difference is documented rather than
silent.) The within-district split between councils still has to come
from postcodes - it is the only sub-district geography ONSPD gives - but
that only matters for the handful of districts that straddle a boundary.

The construction conserves the total exactly: sum(hb) == sum(HB), so
swapping this in for the flat override is a PURE RELATIVITY change and
leaves the Scottish exposure-weighted level untouched. That is
deliberate - it keeps the geography question separate from the level
question `price_scotland_theft.py` already answered.

Two bases are written, because the right window is a real question:

  hb_1yr   2024-25 alone. Matches the published constant exactly, so a
           variant built on it is geography and nothing else.
  hb_3yr   annual mean of 2023-24, 2024-25 and 2025-26. Three times the
           counts, which matters: Shetland recorded SIX housebreakings in
           2024-25, Na h-Eileanan Siar seven, Orkney eight. A one-year
           council rate for those is mostly Poisson noise. This window
           also brackets the police.uk archive (2023-07 to 2026-06) that
           supplies the E&W side, so it is the period-matched basis as
           well as the quieter one.

Both columns are annual counts per district. Level and shape stay
separable downstream: renormalise hb_3yr to hb_1yr's total to price
shape alone.

MEASUREMENT INPUT, not a model change. Nothing reads housebreaking.csv
until an experiment prices it and the owner decides.

Usage:
  fetch_housebreaking.py            # download if needed, then build
"""

import collections
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
OUT = os.path.join(DATA, "housebreaking.csv")
# The modelled unit set, so a district with no polygon never appears.
# sector-model swaps this for sectors_risk.geojson - the same two-line
# seam fetch_households.py, fetch_fires.py and fetch_ct_bands.py carry.
RISK = os.path.join(DATA, "sectors_risk.geojson")

CUBE = os.path.join(CACHE, "scotland_recorded_crime_by_la.csv")
CUBE_URL = ("https://statistics.gov.scot/downloads/cube-table"
            "?uri=http%3A%2F%2Fstatistics.gov.scot%2Fdata%2Frecorded-crime")

CRIME = "Crimes: Group 3: Housebreaking"
YEAR_1 = "2024/2025"
YEARS_3 = ("2023/2024", "2024/2025", "2025/2026")

# Table A6's Total Housebreaking for 2024-25, the constant the model
# divided by households before this file existed. The cube's 32 councils
# must sum to it, or the two publications have drifted apart and the
# join is not the disaggregation it claims to be. It is the join's
# PROOF, not the level in use: the model reads the three-year column.
TABLE_A6_TOTAL_2024_25 = 7_381


def fetch_cube():
    if os.path.exists(CUBE):
        return CUBE
    os.makedirs(CACHE, exist_ok=True)
    print("  downloading the recorded-crime cube (~11 MB)...", flush=True)
    req = urllib.request.Request(
        CUBE_URL, headers={"User-Agent": "Mozilla/5.0",
                           "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    tmp = CUBE + ".partial"
    with open(tmp, "wb") as fh:
        fh.write(body)
    os.replace(tmp, CUBE)
    return CUBE


def housebreaking_by_council():
    """-> {year: {S12... ladcd: count}} for the years this script uses."""
    want = set(YEARS_3) | {YEAR_1}
    out = collections.defaultdict(dict)
    with open(fetch_cube(), newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r["Crime or Offence"] == CRIME
                    and r["Measurement"] == "Count"
                    and r["FeatureType"] == "Council Area"
                    and r["DateCode"] in want):
                out[r["DateCode"]][r["FeatureCode"]] = float(r["Value"])
    missing = sorted(want - set(out))
    if missing:
        raise SystemExit(
            f"the recorded-crime cube has no {CRIME} for {missing} - a "
            "release changed, or the cached copy predates the year. "
            f"Delete {CUBE} and rerun.")
    for y, d in out.items():
        if len(d) != 32:
            raise SystemExit(f"{y} has {len(d)} council areas, not 32 - "
                             "the cube's geography changed")
    total = sum(out[YEAR_1].values())
    if total != TABLE_A6_TOTAL_2024_25:
        raise SystemExit(
            f"the cube's 32 councils sum to {total:,.0f} for {YEAR_1}, but "
            f"Recorded Crime in Scotland Table A6 publishes "
            f"{TABLE_A6_TOTAL_2024_25:,} - these are supposed to be the "
            "same measurement, so the join is not a disaggregation")
    return out


def postcode_key(pc):
    """'AB10 1AA' -> 'AB10 1', the modelled unit's name, or None.

    The sector-model side of the seam: main returns the outward code
    alone. The inward code is ALWAYS the last three characters, however
    the column pads ("YO25 6QP", "S1  1AA", fixed-width pcd7), which is
    the same rule fetch_households.py, fetch_fires.py and
    fetch_ct_bands.py carry here. Keeping it in one function keeps this
    branch's diff to two places rather than scattered through the
    reader.
    """
    compact = pc.replace(" ", "")
    if len(compact) < 5:
        return None
    out, inward = compact[:-3], compact[-3:]
    return f"{out.upper()} {inward[0]}"


def scottish_postcodes():
    """-> {outcode: {ladcd: live postcode count}} for Scotland.

    Same cached ONSPD lookup fetch_households.py and fetch_fires.py use,
    same live-only rule: ONSPD retains terminated postcodes, and counting
    them would weight districts by their history rather than by their
    housing stock.
    """
    from fetch_households import LOOKUP_URL
    from fetch_fires import cached
    zf = zipfile.ZipFile(cached("onspd_lookup.zip", LOOKUP_URL))
    members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    n = collections.defaultdict(collections.Counter)
    live = 0
    for member in members:
        with zf.open(member) as fh:
            rd = csv.reader(io.TextIOWrapper(
                fh, encoding="utf-8-sig", errors="replace"))
            header = next(rd)
            cols = {h.strip().lower(): i for i, h in enumerate(header)}
            pc_i, lad_i = cols["pcds"], cols["ladcd"]
            term_i = cols.get("doterm")
            for row in rd:
                if len(row) <= max(pc_i, lad_i):
                    continue
                lad = row[lad_i].strip()
                if not lad.startswith("S12"):
                    continue
                if term_i is not None and (row[term_i] or "").strip():
                    continue
                pc = row[pc_i].strip()
                if not pc:
                    continue
                key = postcode_key(pc)
                if key:
                    n[key][lad] += 1
                    live += 1
    print(f"  {live:,} live Scottish postcodes across {len(n)} units",
          flush=True)
    return n


def main():
    from scores_real import load_country

    print("housebreaking by council area (statistics.gov.scot)...",
          flush=True)
    hb_year = housebreaking_by_council()
    print(f"  {YEAR_1}: {sum(hb_year[YEAR_1].values()):,.0f} over 32 "
          "councils (ties to Table A6)", flush=True)
    print("  " + ", ".join(f"{y} {sum(hb_year[y].values()):,.0f}"
                           for y in YEARS_3), flush=True)

    print("the model's own units and households...", flush=True)
    with open(RISK, encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    names = [f["name"] for f in feats]
    hh = {f["name"]: float(f.get("households", 0.0)) for f in feats}
    country = dict(zip(names, load_country(names)))
    scot = [d for d in names if country[d] == "Scotland"]
    print(f"  {len(scot)} Scottish units, "
          f"{sum(hh[d] for d in scot):,.0f} households", flush=True)

    print("postcode lookup...", flush=True)
    pc = scottish_postcodes()
    n_orphan = sum(1 for d in scot if d not in pc)
    if n_orphan:
        print(f"  {n_orphan} of {len(scot)} Scottish units hold only "
              "terminated postcodes - filled from their parent outward "
              "code, then the total renormalised", flush=True)

    # A modelled Scottish unit with no live Scottish postcode cannot be
    # joined to a council, and zero-filling it would publish a
    # crime-free unit. At DISTRICT grain there are none. At SECTOR grain
    # there are four - DG3 9, EH52 1, ML7 9, TD8 9 - and every one of
    # them holds only TERMINATED postcodes (EH52 1 is absent from the
    # lookup entirely). They are the same family as the 13
    # empty-geometry sectors that take their parent district's drought
    # climatology, and they get the same treatment: fill from the
    # parent, then renormalise so the total is still conserved.
    #
    # A handful is a data quirk; a lot is a stale or mis-keyed lookup,
    # which is the households.csv void-run shape and must stop the run
    # rather than be quietly filled.
    orphans = [d for d in scot if d not in pc]
    if len(orphans) > 0.01 * len(scot):
        raise SystemExit(
            f"{len(orphans)} of {len(scot)} modelled Scottish units have no "
            f"live Scottish postcode in ONSPD (first: {orphans[:5]}) - "
            "that is too many to be dead postcodes, so it is a wrong "
            "geography key or a stale lookup")

    # Households of district d attributed to council L. Postcodes outside
    # the modelled Scottish set are dropped and each council's count is
    # spread over what remains: 283 of 160,462 postcodes (0.18%), almost
    # all non-geographic large-user codes (AB99, EH99, G9x) plus the two
    # cross-border districts the model scores as England (TD12, TD15).
    share = collections.defaultdict(dict)
    H = collections.Counter()
    for d in scot:
        counts = pc.get(d)
        if not counts:
            continue
        tot = sum(counts.values())
        for lad, k in counts.items():
            v = hh[d] * k / tot
            share[d][lad] = v
            H[lad] += v

    dark = [lad for lad in hb_year[YEAR_1] if H[lad] <= 0]
    if dark:
        raise SystemExit(f"councils with no modelled households: {dark} - "
                         "their housebreakings cannot be placed")

    def apportion(counts):
        """Council counts -> per-unit counts, orphans filled, total kept.

        The fill is the parent's household-weighted rate: siblings
        sharing the outward code first (a sector's own district), the
        Scottish mean if the whole outward code is orphaned. Filling adds
        housebreakings that were not in the source, so everything is
        rescaled back afterwards and the total is conserved exactly - the
        property the whole harness rests on, since it is what makes the
        swap a pure relativity.
        """
        out = collections.Counter()
        for d, m in share.items():
            for lad, v in m.items():
                if lad in counts:
                    out[d] += counts[lad] * v / H[lad]
        if not orphans:
            return out
        placed_hh = sum(hh[d] for d in scot if d not in orphans)
        national = sum(out.values()) / placed_hh
        by_parent = collections.defaultdict(lambda: [0.0, 0.0])
        for d in scot:
            if d in orphans:
                continue
            p = by_parent[d.split()[0]]
            p[0] += out[d]
            p[1] += hh[d]
        for d in orphans:
            n_, h_ = by_parent.get(d.split()[0], [0.0, 0.0])
            out[d] = hh[d] * (n_ / h_ if h_ > 0 else national)
        scale = sum(counts.values()) / sum(out.values())
        for d in out:
            out[d] *= scale
        return out

    one_src = hb_year[YEAR_1]
    three_src = {lad: sum(hb_year[y][lad] for y in YEARS_3) / len(YEARS_3)
                 for lad in one_src}
    one, three = apportion(one_src), apportion(three_src)

    for label, placed, source in (("hb_1yr", one, one_src),
                                  ("hb_3yr", three, three_src)):
        got, want = sum(placed.values()), sum(source.values())
        if abs(got - want) > 1e-6:
            raise SystemExit(
                f"{label} placed {got:,.4f} of {want:,.4f} - the "
                "apportionment is supposed to conserve the total")

    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "hb_1yr", "hb_3yr"])
        for d in sorted(scot):
            w.writerow([d, round(one[d], 4), round(three[d], 4)])

    hhs = sum(hh[d] for d in scot)
    r1 = {d: one[d] / hh[d] for d in scot if hh[d] > 0}
    lo, hi = min(r1, key=r1.get), max(r1, key=r1.get)
    print(f"wrote {OUT}: {len(scot)} units, "
          f"{sum(one.values()):,.0f} housebreakings/yr placed ({YEAR_1}), "
          f"{sum(three.values()):,.0f} on the 3-year mean")
    print(f"  flat rate was {sum(one.values()) / hhs:.4%}/yr everywhere; "
          f"now {r1[lo]:.4%} ({lo}) to {r1[hi]:.4%} ({hi}), "
          f"{r1[hi] / r1[lo]:.1f}x")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
