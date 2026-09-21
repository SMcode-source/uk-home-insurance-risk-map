"""External validation of flood ORDERING in ENGLAND - 85% of the exposure.

validate_flood_ordering.py checked Wales and Scotland, because NRW
publishes people-at-risk per community and SEPA an annual-average-damage
grid. England had nothing, and HANDOFF has carried the open question
since 2026-09-05: does the EA publish the same kind of thing? It does.

  EA  "Risk of Flooding from Rivers and Sea - Key Summary Information"
      and "...from Surface Water - Key Summary Information". Each is a
      zip of spreadsheets counting the properties and people inside the
      risk bands, broken down by ONS Region, River Basin District,
      RFCC, EA Area, LLFA, Local Authority and MP Constituency.
      OGL - recorded ONLY in the CKAN `extras` key `licence`, exactly
      as NCERM does it (DATA_SOURCES #21); `license_id` reads null.

The sheet this script reads is the finest and the most like-for-like:
PERCENTAGE OF PROPERTIES AT RISK BY MP CONSTITUENCY - BREAKDOWN BY
PROPERTY TYPE (RELATIVE TO PROPERTY TYPE), the `Residential (%)`
columns. That is the share of a constituency's HOMES in each band -
the same quantity `f_high` and `sw_high` are, on the same bands,
counted from the National Receptor Dataset 2023 rather than sampled at
unit-postcode centroids. 534 English constituencies.

WHAT THIS DOES AND DOES NOT TEST. The EA derives these counts from the
same RoFRS/RoFSW rasters the model samples, so agreement is NOT
evidence that the hazard map is right. What differs is everything
between the raster and a district number: which receptors are counted
(NRD address points vs unit-postcode centroids), and the aggregation
and shrinkage on top. That is exactly the class of error the Welsh
check found on 2026-09-05 - area share standing in for household
share, Spearman -0.13 on Welsh rivers - so it is worth measuring, and
it is not worth overclaiming.

The join is administrative, not geometric: ONSPD gives every unit
postcode a Westminster constituency (`pcon24cd`), so a district's rate
is carried to constituencies by the postcodes it actually has there.
No area apportionment, unlike the Wales/Scotland script.

Writes data/flood_validation_england.csv and changes nothing the model
reads. Needs openpyxl and data/cache/onspd_full.zip (fetch_onspd.py).
Run from a laptop:

    .venv/Scripts/python.exe -u scripts/validate_flood_england.py
"""
import csv
import io
import json
import os
import re
import urllib.request
import zipfile

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
os.makedirs(CACHE, exist_ok=True)

DL = "https://environment.data.gov.uk/api/file/download?fileDataSetId={}&fileName={}"

# product -> (CKAN fileDataSetId, zip name, model >=1% AEP column,
#             model whole-envelope column)
PACKS = {
    "rivers_sea": ("03068e80-a88b-418d-bd3d-8d8caf4f3c62",
                   "RoFRS_KeySummaryInfo.zip", "f_high", "f_low"),
    "surface_water": ("b15bdd08-6e4b-4f12-9429-6c07f50e2698",
                      "RoFSW_KeySummaryInfo.zip", "sw_high", "sw_low"),
}

# The only one of the five blocks in the sheet that is directly
# comparable to a model fraction. The others are counts, or percentages
# of ALL properties (so a constituency with many shops reads low on a
# residential measure), or the whole-stock share.
BLOCK = ("PERCENTAGE OF PROPERTIES AT RISK BY MP CONSTITUENCY - "
         "BREAKDOWN BY PROPERTY TYPE (RELATIVE TO PROPERTY TYPE)")

# Both products band by annual chance: High >3.3% (1 in 30), Medium
# 1-3.3% (1 in 100), Low below that. High+Medium is the >=1% AEP band
# the model calls `*_high`. RoFRS adds a fourth, "Very Low"; summing
# every band gives the whole envelope, `*_low`.
HIGH_BANDS = ("High", "Medium")

# The EA writes ONS Boundary-Line names ("Aldershot Boro Const");
# ONSPD's own lookup writes them plain ("Aldershot"). The two also
# disagree about the full stop in "St. Albans" - 8 of 534, all of them
# saints, silently dropped before this was normalised.
SUFFIX = re.compile(r"\s+(Boro|Co|County|Burgh)\s+Const$", re.I)


def canon(name):
    """Join key. The two sources also disagree on the case of
    'Weston-super-Mare', so fold it."""
    return SUFFIX.sub("", name.strip()).replace("St. ", "St ").lower()


# A postcode DISTRICT is not nested inside a constituency, and the two
# cross-cut EVERYWHERE, not just in cities: the median constituency
# takes only 34% of its postcodes from its largest district and the
# best in England manages 89%. So a district's one rate is carried into
# several constituencies and the model cannot be right about more than
# their average - which caps how high this rho can go, and means a
# disagreement may be the join's resolution rather than the model's
# error. That is a claim to measure, not assert: every row carries the
# share of its postcodes from its single largest district, and the
# report correlates within quartiles of it. If the tightest quartile
# scores no better than the loosest, resolution is not the story.
NEST_Q = 4


def fetch(name, url):
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"  downloading {name}", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "uk-risk-map"})
        with urllib.request.urlopen(req, timeout=300) as r, \
                open(path + ".part", "wb") as fh:
            fh.write(r.read())
        os.replace(path + ".part", path)
    return path


def ea_residential_rates(product):
    """{constituency -> {band -> share of its residential properties}}."""
    import openpyxl
    fid, fname = PACKS[product][0], PACKS[product][1]
    z = zipfile.ZipFile(fetch(fname, DL.format(fid, fname)))
    # "GroundfloorPropertiesAtRisk" is a DIFFERENT product in the same
    # zip - ground floors only, arguably closer to what damages a home,
    # but not what `*_high` measures. Take the plain workbook.
    inner = [i.filename for i in z.infolist()
             if i.filename.endswith(".xlsx")
             and "PropertiesAtRisk" in i.filename
             and "Groundfloor" not in i.filename]
    if len(inner) != 1:
        raise SystemExit(f"{fname}: expected one properties workbook, got {inner}")
    wb = openpyxl.load_workbook(io.BytesIO(z.read(inner[0])),
                                read_only=True, data_only=True)
    rows = list(wb["MP Constituency"].iter_rows(values_only=True))
    starts = [i for i, r in enumerate(rows)
              if isinstance(r[0], str) and r[0].strip() == BLOCK]
    if len(starts) != 1:
        raise SystemExit(f"{inner[0]}: found {len(starts)} blocks named "
                         f"{BLOCK!r} - the workbook layout changed")
    i = starts[0]
    # the band row is the first below the title whose second cell names
    # a risk band; the property type is the row under it. The two packs
    # put these at different offsets, so find them rather than assume.
    band_row = next(j for j in range(i + 1, i + 6)
                    if rows[j][1] and "Risk" in str(rows[j][1]))
    type_row = band_row + 1
    bands, last = [], ""
    for c in rows[band_row]:
        last = str(c).strip() if c else last
        bands.append(last)
    cols = {bands[k].replace(" Risk", ""): k
            for k, t in enumerate(rows[type_row])
            if t and str(t).strip() == "Residential (%)"}
    if not cols:
        raise SystemExit(f"{inner[0]}: no 'Residential (%)' columns found")

    out = {}
    for r in rows[type_row + 1:]:
        nm = r[0]
        if not isinstance(nm, str) or not nm.strip():
            break
        if nm.strip().isupper():
            break
        if nm.startswith("<<"):
            continue
        out[canon(nm)] = dict(
            {b: float(r[k] or 0) / 100.0 for b, k in cols.items()},
            display=nm.strip())
    print(f"  {product}: {inner[0].split('/')[-1]}, {len(out)} constituencies, "
          f"bands {sorted(cols)}", flush=True)
    missing = [b for b in HIGH_BANDS if b not in cols]
    if missing:
        raise SystemExit(f"{inner[0]}: no {missing} column - band names changed")
    return out


def postcode_constituency():
    """{unit postcode -> constituency name} for England, from ONSPD."""
    zp = os.path.join(CACHE, "onspd_full.zip")
    if not os.path.exists(zp):
        raise SystemExit(f"{zp} missing - run scripts/fetch_onspd.py first")
    z = zipfile.ZipFile(zp)
    lut = next(n for n in z.namelist()
               if n.endswith(".csv") and "Constituency names and codes" in n)
    with z.open(lut) as fh:
        rdr = csv.reader(io.TextIOWrapper(fh, "utf-8-sig"))
        hdr = next(rdr)
        ci, ni = hdr.index("PCON24CD"), hdr.index("PCON24NM")
        names = {r[ci]: canon(r[ni]) for r in rdr if r}
    out = {}
    files = sorted(n for n in z.namelist()
                   if n.lower().endswith(".csv") and "/multi_csv/" in n.lower())
    for n in files:
        with z.open(n) as fh:
            rdr = csv.reader(io.TextIOWrapper(fh, "latin-1"))
            hdr = next(rdr)
            ix = {c: i for i, c in enumerate(hdr)}
            pc, pcon = ix["pcds"], ix["pcon24cd"]
            for r in rdr:
                code = r[pcon].strip()
                if code.startswith("E"):
                    out[r[pc].strip()] = names.get(code, code)
    print(f"  ONSPD: {len(out):,} English postcodes across "
          f"{len(set(out.values()))} constituencies", flush=True)
    return out


def spearman(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 8:
        return float("nan"), int(ok.sum())
    return float(stats.spearmanr(a[ok], b[ok]).statistic), int(ok.sum())


def main():
    with open(os.path.join(DATA, "districts_risk.geojson"), encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    model = pd.DataFrame([f["properties"] for f in feats])
    model = model[model["country"] == "England"].set_index("name")
    print(f"  model: {len(model)} English districts", flush=True)

    cen = pd.read_csv(os.path.join(DATA, "postcode_centroids.csv"))
    cen = cen[cen["country"] == "England"].copy()
    cen["pcon"] = cen["postcode"].map(postcode_constituency())
    missing = int(cen["pcon"].isna().sum())
    cen = cen.dropna(subset=["pcon"])
    cen = cen[cen["district"].isin(model.index)]
    print(f"  {len(cen):,} English model postcodes joined "
          f"({missing:,} had no ONSPD constituency)", flush=True)

    # A district's rate is carried to a constituency by the postcodes it
    # actually has there. Weighted by postcode COUNT, not area, because
    # the model's own fractions have been postcode shares since
    # 2026-09-06 - weighting them by area would reintroduce the very
    # thing the Welsh check condemned.
    w = cen.groupby(["pcon", "district"]).size().rename("n").reset_index()

    rows = []
    for product, (_, _, hi_col, lo_col) in PACKS.items():
        ea = ea_residential_rates(product)
        w2 = w.copy()
        for col in (hi_col, lo_col):
            w2[col] = w2["district"].map(model[col]).astype(float)
        agg = w2.groupby("pcon").apply(
            lambda g: pd.Series(
                {"n": g["n"].sum(),
                 "nest": g["n"].max() / g["n"].sum(),
                 "hi": float(np.average(g[hi_col], weights=g["n"])),
                 "lo": float(np.average(g[lo_col], weights=g["n"]))}),
            include_groups=False)
        matched = 0
        for pcon, r in agg.iterrows():
            e = ea.get(pcon)
            if e is None:
                continue
            matched += 1
            rows.append({"product": product, "constituency": e["display"],
                         "n_postcodes": int(r["n"]), "nest": float(r["nest"]),
                         "ea_high": sum(e.get(b, 0.0) for b in HIGH_BANDS),
                         "ea_all": float(sum(v for k, v in e.items() if k != "display")),
                         "model_high": r["hi"], "model_all": r["lo"],
                         "hi_col": hi_col, "lo_col": lo_col})
        unmatched = sorted(set(ea) - set(agg.index))
        print(f"     matched {matched} of {len(ea)} EA constituencies"
              + (f"; unmatched e.g. {unmatched[:4]}" if unmatched else ""),
              flush=True)

    out = pd.DataFrame(rows)
    print("\n  Spearman rank correlation over English constituencies, "
          "EA residential share vs model fraction")
    print(f"  {'product':<15}{'EA band':<10}{'model':<10}{'rho':>8}{'n':>6}")
    for product, g in out.groupby("product"):
        for ea_c, mo_c, col_key in (("ea_high", "model_high", "hi_col"),
                                    ("ea_all", "model_all", "lo_col"),
                                    ("ea_high", "model_all", "lo_col"),
                                    ("ea_all", "model_high", "hi_col")):
            rho, n = spearman(g[ea_c].values, g[mo_c].values)
            print(f"  {product:<15}{ea_c:<10}{g[col_key].iloc[0]:<10}"
                  f"{rho:>8.3f}{n:>6}")

    print("\n  Within quartiles of how concentrated the constituency is in "
          "one district\n  (Q1 = most split, Q4 = tightest; if rho does not "
          "climb, resolution is not the story)")
    print(f"  {'product':<15}{'quartile':<10}{'nest range':<16}{'rho':>8}{'n':>6}")
    for product, g in out.groupby("product"):
        q = pd.qcut(g["nest"], NEST_Q, labels=[f"Q{i + 1}" for i in range(NEST_Q)])
        for lab in [f"Q{i + 1}" for i in range(NEST_Q)]:
            sub = g[q == lab]
            rho, n = spearman(sub["ea_high"].values, sub["model_high"].values)
            rng = f"{sub['nest'].min():.2f}-{sub['nest'].max():.2f}"
            print(f"  {product:<15}{lab:<10}{rng:<16}{rho:>8.3f}{n:>6}")

    for product, g in out.groupby("product"):
        g = g.copy()
        g["gap"] = g["ea_high"].rank() - g["model_high"].rank()
        order = g["gap"].abs().sort_values(ascending=False).index
        print(f"\n  {product}: largest rank disagreements of {len(g)} "
              f"(EA rank - model rank)")
        for _, r in g.loc[order].head(6).iterrows():
            print(f"    {r['constituency'][:32]:32} "
                  f"EA {100 * r['ea_high']:6.2f}%  "
                  f"model {100 * r['model_high']:6.2f}%  gap {r['gap']:+.0f}")

    path = os.path.join(DATA, "flood_validation_england.csv")
    out.to_csv(path, index=False)
    print(f"\n  wrote {path}  ({len(out)} rows)")


if __name__ == "__main__":
    main()
