import json

raw = open("data/districts_risk.geojson", encoding="utf-8").read()
print("has NaN literal:", " NaN" in raw or ":NaN" in raw)
g = json.loads(raw)          # raises if invalid JSON
p = g["features"][0]["properties"]
print("features:", len(g["features"]))
print("keys:", ", ".join(p.keys()))
print("gust_rp50 sample:", p.get("gust_rp50"))
prem = [f["properties"]["premium"] for f in g["features"]]
print(f"premium min {min(prem):.0f} max {max(prem):.0f}")
