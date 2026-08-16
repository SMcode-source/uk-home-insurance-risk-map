"""Download Met Office open climate layers from the Climate Data Portal
(ArcGIS feature services, anonymous, OGL).

Outputs data/metoffice/<name>.csv with columns x, y (EPSG:27700) + value:
  wind      ws_winter_baseline_median   winter mean wind speed, 5km (UKCP18 baseline 1981-2000)
  wdr       WDR_baseline_Median         annual wind-driven rain index, SW-facing walls, 5km
  precip    pr                          annual precipitation 1991-2020 (HadUK-Grid obs, 12km)
  rain10    Rain10mmDays                annual count of >=10mm rain days 1991-2020 (HadUK-Grid obs)
  frost     airfrostDays                annual count of air-frost days 1991-2020 (HadUK-Grid obs)
                                        - the freeze-exposure driver for escape of water
"""

import csv
import json
import os
import urllib.parse
import urllib.request

BASE = "https://services.arcgis.com/Lq3V5RFuTBC9I7kv/arcgis/rest/services"
OUT_DIR = os.path.join("data", "metoffice")

LAYERS = {
    "wind": dict(
        url=f"{BASE}/Seasonal_Average_Wind_Speed_Projections_5km/FeatureServer/0",
        fields=["x_coord", "y_coord", "ws_winter_baseline_median"],
        where="1=1", centroid=False,
    ),
    "wdr": dict(
        url=f"{BASE}/Annual_Index_of_Wind_Driven_Rain_Projections_5km/FeatureServer/2",
        fields=["x_coord", "y_coord", "WDR_baseline_Median"],
        where="Wall_orientation=225", centroid=False,
    ),
    "precip": dict(
        url=f"{BASE}/Annual_Precipitation_Observations_1991_2020/FeatureServer/0",
        fields=["pr"], where="1=1", centroid=True,
    ),
    "rain10": dict(
        url=f"{BASE}/Annual_Count_of_10mm_Rain_Days_1991_2020/FeatureServer/0",
        fields=["Rain10mmDays"], where="1=1", centroid=True,
    ),
    "frost": dict(
        url=f"{BASE}/Annual_Count_of_Airfrost_Days_1991_2020/FeatureServer/0",
        fields=["airfrostDays"], where="1=1", centroid=True,
    ),
}


def fetch(name, spec):
    rows, offset = [], 0
    while True:
        params = {
            "where": spec["where"],
            "outFields": ",".join(spec["fields"]),
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": 2000,
            "f": "json",
        }
        if spec["centroid"]:
            params["returnCentroid"] = "true"
        url = spec["url"] + "/query?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=300) as r:
            data = json.load(r)
        if "error" in data:
            raise RuntimeError(f"{name}: {data['error']}")
        feats = data.get("features", [])
        if not feats:
            break
        for f in feats:
            a = f["attributes"]
            if spec["centroid"]:
                c = f.get("centroid") or {}
                row = [c.get("x"), c.get("y")] + [a.get(k) for k in spec["fields"]]
            else:
                row = [a.get(spec["fields"][0]), a.get(spec["fields"][1]),
                       a.get(spec["fields"][2])]
            if all(v is not None for v in row):
                rows.append(row)
        offset += len(feats)
        print(f"  {name}: {offset} rows")
        if not data.get("exceededTransferLimit") and len(feats) < 2000:
            break
    path = os.path.join(OUT_DIR, f"{name}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["x", "y", "value"])
        w.writerows(rows)
    print(f"wrote {path}: {len(rows)} rows")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    import sys
    only = sys.argv[1:]          # e.g. `fetch_metoffice.py frost` refetches one
    for name, spec in LAYERS.items():
        if only and name not in only:
            continue
        print(f"fetching {name}...")
        fetch(name, spec)


if __name__ == "__main__":
    main()
