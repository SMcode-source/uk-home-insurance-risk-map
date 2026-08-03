"""Download BGS 625k geology (OGL) from the BGS OGC API.

Pages through /collections/<id>/items following `next` links, keeps only
the fields needed for shrink-swell classification, and writes GeoJSON.

    python scripts/fetch_bgs.py                # bedrock     (default)
    python scripts/fetch_bgs.py --superficial  # superficial

Bedrock is the base layer. Superficial deposits overlie it and, where
clay-rich, govern the near-surface behaviour domestic foundations actually
sit in - see sub_score_from_bgs() in scores_real.py for how the two are
combined, and why the combination is deliberately bounded.

The two collections do not share a schema: superficial carries `rock_d`
and has no `max_period` (its age fields read QUATERNARY throughout). KEEP
is therefore per collection, and bedrock's is unchanged so its output
stays byte-identical to the committed file.
"""

import json
import os
import sys
import time
import urllib.request

BASE = "https://ogcapi.bgs.ac.uk/collections"

LAYERS = {
    "bedrock": dict(
        collection="bgsgeology625kbedrock",
        out="data/bgs_625k_bedrock.geojson",
        keep=["lex", "lex_d", "rcs_d", "gp_eq_d", "max_period"],
    ),
    "superficial": dict(
        collection="bgsgeology625ksuperficial",
        out="data/bgs_625k_superficial.geojson",
        # rock_d is the lithology description ("CLAY, SILT AND SAND") and
        # is what the superficial classifier keys off; max_system stands in
        # for the absent max_period.
        keep=["lex", "lex_d", "rcs_d", "rock_d", "max_system"],
    ),
}


# Retry policy, matching the raster fetchers: 6 attempts with EXPONENTIAL
# backoff, not a flat sleep. This is not theoretical - the BGS API drops
# the connection on the last page of the superficial layer specifically
# ("Connection reset by peer" / WinError 10054 on page 21 of 21, the short
# final page). Four attempts 10s apart rode it out locally by luck and
# failed all four on a GitHub runner. Backing off to 10/20/40/80/160s
# gives the server time to recover instead of hammering it while it is
# still refusing.
RETRIES = 6
BACKOFF = 10


def fetch(cfg):
    url = f"{BASE}/{cfg['collection']}/items?f=json&limit=500"
    features, page, matched = [], 0, None
    while url:
        for attempt in range(RETRIES):
            try:
                with urllib.request.urlopen(url, timeout=300) as r:
                    data = json.load(r)
                break
            except Exception as e:
                wait = BACKOFF * (2 ** attempt)
                last = attempt == RETRIES - 1
                print(f"  page {page} attempt {attempt + 1}/{RETRIES} "
                      f"failed: {e}" + ("" if last else f" - retrying in {wait}s"),
                      flush=True)
                if not last:
                    time.sleep(wait)
        else:
            raise SystemExit(
                f"giving up on page {page} after {RETRIES} attempts. "
                f"Nothing is written, so no partial layer can reach the "
                f"model - rerun when the endpoint recovers.")

        if matched is None:
            matched = data.get("numberMatched")
        for f in data.get("features", []):
            props = f.get("properties", {})
            features.append({
                "type": "Feature",
                "properties": {k: props.get(k) for k in cfg["keep"]},
                "geometry": f.get("geometry"),
            })
        page += 1
        print(f"page {page}: total {len(features)}/{matched}")

        url = None
        for link in data.get("links", []):
            if link.get("rel") == "next":
                url = link["href"]

    # A short geology fetch is invisible downstream - missing polygons read
    # as "no data here" and quietly change district scores, the same trap
    # the raster fetchers guard with .partial. Do the same rather than
    # letting an incomplete layer become model input.
    out = cfg["out"]
    if matched is not None and len(features) != matched:
        out += ".partial"
        print(f"INCOMPLETE: {len(features)} of {matched} features "
              f"-> writing {out} so it cannot be used as input")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    size = os.path.getsize(out) / 1e6
    print(f"wrote {out}: {len(features)} features ({size:.1f} MB)")
    return out.endswith(".partial")


def main():
    which = "superficial" if "--superficial" in sys.argv[1:] else "bedrock"
    print(f"BGS 625k {which} -> {LAYERS[which]['out']}")
    if fetch(LAYERS[which]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
