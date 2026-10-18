"""Validate data/abi_subsidence.csv and print what it says about the anchors.

The ABI publishes domestic subsidence on TWO bases and never says so in
the same sentence:

  incurred_notified / incurred_ultimate  the value of claims MADE in the
      period, an estimate that moves as monitoring finishes. The 2018 and
      2022 surge releases are on this basis.
  paid_in_period  cash actually paid during the quarter, whenever the
      claim was notified. The Property Insurance Tracker is on this basis.

They are not interchangeable, and the difference is the whole reason this
file exists. Subsidence runs a monitoring period - often a full seasonal
cycle - before repair, so paid lags notification by quarters to years.
The evidence is in the data below: the paid series splits 2025 almost
exactly 50/50 across the half-years, while the notified series in a surge
year is 78% H2. Paying smears the summer signal into a flat line, so any
curve fitted to a temperature index has to be fitted to NOTIFIED COUNTS.

Run:  .venv/Scripts/python.exe scripts/check_abi_subsidence.py
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PATH = os.path.join(ROOT, "data", "abi_subsidence.csv")

# Closed vocabularies. A new value here is a decision, not a typo, so the
# check fails rather than silently widening the meaning of the column.
BASIS = {"notified_count", "supported_households", "incurred_notified",
         "incurred_ultimate", "paid_in_period", "avg_incurred", "avg_paid",
         "implied"}
PROVENANCE = {"published", "derived", "restated"}
UNIT = {"count", "gbp", "gbp_m"}

# build_model.py's current anchors, restated here so this script can say
# what the series implies about them without importing the model (which
# would pull in numpy and the whole calibration).
MODEL_SUBSIDENCE_PAID = 307e6      # FY2025, ABI 2026-02 release
MODEL_SEV_SUBSIDENCE = 17_820.0    # ABI 2026-05 release - but see below
MODEL_IMPLIED_COUNT = 17_228


def load():
    with open(PATH, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit("data/abi_subsidence.csv is empty")
    return rows


def check_vocabularies(rows):
    bad = 0
    for i, r in enumerate(rows, start=2):
        for col, allowed in (("basis", BASIS), ("provenance", PROVENANCE),
                             ("unit", UNIT)):
            if r[col] not in allowed:
                print(f"  line {i}: {col} = {r[col]!r} not in vocabulary")
                bad += 1
        try:
            float(r["value"])
        except (TypeError, ValueError):
            print(f"  line {i}: value = {r['value']!r} is not a number")
            bad += 1
        if not r["source"].startswith("http"):
            print(f"  line {i}: source is not a URL")
            bad += 1
        if not r["note"].strip():
            print(f"  line {i}: empty note - every figure needs its quote")
            bad += 1
    print(f"  {len(rows)} rows, {bad} violations")
    return bad


def main():
    rows = load()
    v = {(r["period"], r["metric"], r["provenance"]): float(r["value"])
         for r in rows}

    def get(period, metric, *provenances):
        for p in provenances or ("published", "restated", "derived"):
            if (period, metric, p) in v:
                return v[(period, metric, p)]
        return None

    print("== vocabulary and provenance ==")
    bad = check_vocabularies(rows)

    print()
    print("== the two bases are internally consistent ==")
    inc, cnt = get("2022", "subsidence_incurred"), get("2022", "subsidence_claims")
    avg = get("2022", "subsidence_avg")
    implied = inc * 1e6 / cnt
    print(f"  2022 incurred GBP {inc:.0f}m / {cnt:,.0f} claims made "
          f"= GBP {implied:,.0f}")
    print(f"  2022 published average incurred        = GBP {avg:,.0f}"
          f"   ({abs(implied / avg - 1):.1%} apart)")
    if abs(implied / avg - 1) > 0.02:
        print("  WARN: the 2022 triangle no longer closes to 2%")
        bad += 1

    print()
    print("== paid has no seasonality; notified is all summer ==")
    h1, fy = get("2025H1", "subsidence_paid"), get("2025", "subsidence_paid")
    print(f"  2025 PAID     H1 {h1:.0f} / FY {fy:.0f} "
          f"-> {100 * h1 / fy:.1f}% H1, {100 * (fy - h1) / fy:.1f}% H2")
    h2c, yc = get("2022H2", "subsidence_claims"), get("2022", "subsidence_claims")
    print(f"  2022 NOTIFIED H2 {h2c:,.0f} / FY {yc:,.0f} "
          f"-> {100 * (yc - h2c) / yc:.1f}% H1, {100 * h2c / yc:.1f}% H2")
    print("  -> fit the temperature curve to NOTIFIED COUNTS, not paid")

    print()
    print("== the 2018 surge, the signature any curve must reproduce ==")
    for q in ("2018Q2", "2018Q3"):
        c, val = get(q, "subsidence_claims"), get(q, "subsidence_incurred")
        print(f"  {q}  {c:>6,.0f} claims  GBP {val:>3.0f}m  "
              f"avg GBP {val * 1e6 / c:>6,.0f}")
    print(f"  Q2 -> Q3 claim count x"
          f"{get('2018Q3', 'subsidence_claims') / get('2018Q2', 'subsidence_claims'):.1f}"
          " in one quarter")

    print()
    print("== 2024 quarterly vs full year: UNRECONCILED ==")
    qs = [get(f"2024Q{i}", "subsidence_paid", "restated", "published")
          for i in (1, 2, 3)]
    fy24 = get("2024", "subsidence_paid")
    print(f"  Q1 {qs[0]:.0f} + Q2 {qs[1]:.0f} + Q3 {qs[2]:.0f} = {sum(qs):.0f}"
          f"  vs FY {fy24:.0f}  -> implied Q4 {fy24 - sum(qs):.0f}")
    print(f"  that Q4 is {(fy24 - sum(qs)) / max(qs):.2f}x the largest "
          "published quarter. Q1 and Q2 are both confirmed from primary")
    print("  text, so the suspect is FY2024 = 307 - 27, itself derived.")
    print("  OPEN: the 2025-02 FY2024 release carries no subsidence line.")

    print()
    print("== what the series says about build_model's anchors ==")
    print(f"  subsidence_paid  = GBP {MODEL_SUBSIDENCE_PAID / 1e6:.0f}m"
          "   FY2025, ABI 2026-02       OK")
    print(f"  sev_subsidence   = GBP {MODEL_SEV_SUBSIDENCE:,.0f}"
          "     Q1 2026, ABI 2026-05      PERIOD MISMATCH")
    print("  The severity is one quarter of 2026; the paid total is the")
    print("  whole of 2025. Counts implied by each candidate average:")
    for label, a in (("Q1 2026 (what the model uses)", MODEL_SEV_SUBSIDENCE),
                     ("Q1 2025 (the y/y comparator)", get("2025Q1", "subsidence_avg")),
                     ("H1 2025 (the only 2025 average on a stated period)",
                      get("2025H1", "subsidence_avg"))):
        n = MODEL_SUBSIDENCE_PAID / a
        print(f"    {label:52} GBP {a:>7,.0f} -> {n:>9,.0f} claims"
              f"  ({n - MODEL_IMPLIED_COUNT:+,.0f} vs published)")
    print("  Every consistent choice RAISES the count, which worsens the")
    print("  claim-count budget - see anchor_budget.py.")

    print()
    if bad:
        print(f"FAILED: {bad} violation(s)")
        return 1
    print("OK (the 2024 Q4 gap is a recorded open item, not a failure)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
