"""Per-district groundwater flood-risk fractions.

Source: EA 'Flood risk: postcode search tool data' (OGL) — already
downloaded to data/ea_postcode_risk.csv. Its GWTR_RISK field flags each
unit postcode 'Possible' if any address falls in a groundwater flood
alert target area. District fraction = share of unit postcodes flagged.

Coverage is England only (groundwater flooding in the UK is dominated by
the English chalk/limestone aquifers); districts with no English unit
postcodes get a nominal 0.02 background, documented in the README.

Output: data/gw_fractions.csv (name, gw_frac)
"""

import csv
from collections import defaultdict

counts = defaultdict(lambda: [0, 0])   # SECTOR -> [possible, total]

with open("data/ea_postcode_risk.csv", newline="", encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        # sector-model branch: key on "OUTWARD D" (e.g. "AL1 1"), the
        # first inward character after the outward code
        parts = row["Postcode"].split()
        if len(parts) < 2 or not parts[1]:
            continue
        sector = f"{parts[0]} {parts[1][0]}"
        counts[sector][1] += 1
        if row["GWTR_RISK"].strip().lower() == "possible":
            counts[sector][0] += 1

with open("data/gw_fractions.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["name", "gw_frac", "n_postcodes"])
    for sector, (poss, tot) in sorted(counts.items()):
        w.writerow([sector, round(poss / tot, 5), tot])

print(f"wrote data/gw_fractions.csv: {len(counts)} districts")
top = sorted(counts.items(), key=lambda kv: -kv[1][0] / kv[1][1])[:10]
for d, (p, t) in top:
    print(f"  {d:6} {p}/{t} = {p / t:.2%}")
