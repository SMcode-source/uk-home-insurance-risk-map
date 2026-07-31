"""Download the full BGS 625k bedrock geology (OGL) from the BGS OGC API.

Pages through /collections/bgsgeology625kbedrock/items following `next`
links, keeps only the fields needed for shrink-swell classification, and
writes data/bgs_625k_bedrock.geojson.
"""

import json
import time
import urllib.request

URL = ("https://ogcapi.bgs.ac.uk/collections/bgsgeology625kbedrock/items"
       "?f=json&limit=500")
OUT = "data/bgs_625k_bedrock.geojson"
KEEP = ["lex", "lex_d", "rcs_d", "gp_eq_d", "max_period"]

features = []
url = URL
page = 0
while url:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                data = json.load(r)
            break
        except Exception as e:
            print(f"  page {page} attempt {attempt + 1} failed: {e}")
            time.sleep(10)
    else:
        raise SystemExit(f"giving up on page {page}")

    for f in data.get("features", []):
        props = f.get("properties", {})
        features.append({
            "type": "Feature",
            "properties": {k: props.get(k) for k in KEEP},
            "geometry": f.get("geometry"),
        })
    page += 1
    print(f"page {page}: total {len(features)}/{data.get('numberMatched')}")

    url = None
    for link in data.get("links", []):
        if link.get("rel") == "next":
            url = link["href"]

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"type": "FeatureCollection", "features": features}, fh)
print(f"wrote {OUT}: {len(features)} features")
