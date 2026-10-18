"""Merge the 20 m/px Wales re-render into sw_fractions.csv.

The first national pass rendered Wales at 100 m/px, which under-renders
FRAW's small surface-water polygons. The 20 m re-render only sees
Welsh-side pixels, so per district we take max(existing, wales20) —
border districts keep their (larger) England-sourced values.
"""

import pandas as pd

base = pd.read_csv("data/sw_fractions.csv").set_index("name")
wales = pd.read_csv("data/sw_wales20.csv").set_index("name")

changed = 0
for col in ["sw_high", "sw_low"]:
    upgraded = wales[col] > base[col]
    changed = max(changed, int(upgraded.sum()))
    base[col] = base[col].where(~upgraded, wales[col])
base["sw_low"] = base[["sw_low", "sw_high"]].max(axis=1)

base.round(5).to_csv("data/sw_fractions.csv")
print(f"merged: {changed} districts upgraded")
print(base.loc[[n for n in ["CF10", "CF11", "SA1", "NP20", "LL18", "SE15"]
                if n in base.index]])
