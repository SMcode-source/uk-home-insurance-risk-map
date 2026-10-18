import pandas as pd

d = pd.read_csv("data/sw_fractions.csv").set_index("name")
print(d.describe().round(4))
print()
for n in ["M1", "B1", "LS1", "SE15", "CF10", "G5", "LL18", "HU6", "TR1", "EC1"]:
    if n in d.index:
        print(f"{n:5} sw_high={d.loc[n, 'sw_high']:.3f} sw_low={d.loc[n, 'sw_low']:.3f}")
