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


# The BGS endpoint throttles sustained paging. It is not a bad page and it
# is not random: a run gets ~19-20 rapid pages in, then starts resetting
# the connection, and a 160-second backoff does NOT clear it - one Actions
# run recovered on page 19 after five attempts and then lost page 20 to
# all six. It fails wherever the run happens to be by then, which is why
# it first looked like "the last page is broken".
#
# So: pace the requests to stay under the limit, back off exponentially
# when refused anyway, and - the part that actually matters - CHECKPOINT,
# so a run that is throttled at page 20 of 23 resumes there instead of
# starting over. That is the same rule fetch_sw_depth.py follows, and the
# reason it survives this machine going to sleep mid-fetch.
RETRIES = 6
BACKOFF = 10
PAGE = 500
PACE = 1.0          # seconds between successful pages


def _page_url(cfg, offset):
    # Explicit offsets rather than following `next` links: a link cannot be
    # resumed from, an offset can. Verified to give byte-identical ordering
    # to the next-link paging that produced the committed layers, which
    # matters because the dominant-formation tie-break depends on order.
    return (f"{BASE}/{cfg['collection']}/items"
            f"?f=json&limit={PAGE}&offset={offset}")


def _get(url):
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "uk-risk-map/1.0 (+github.com/"
                                            "SMcode-source)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except Exception as e:
            wait = BACKOFF * (2 ** attempt)
            last = attempt == RETRIES - 1
            print(f"    attempt {attempt + 1}/{RETRIES} failed: {e}"
                  + ("" if last else f" - retrying in {wait}s"), flush=True)
            if not last:
                time.sleep(wait)
    return None


def fetch(cfg):
    ckpt = cfg["out"] + ".progress.jsonl"
    meta = cfg["out"] + ".progress.json"
    features = []
    if os.path.exists(ckpt):
        with open(ckpt, encoding="utf-8") as fh:
            features = [json.loads(line) for line in fh if line.strip()]
        print(f"  resuming from {ckpt}: {len(features)} features already "
              f"fetched", flush=True)

    # numberMatched has to survive a resume. Without it, a resumed run
    # whose FIRST request is refused never learns the expected total, and
    # a "matched is not None" completeness test then silently passes: the
    # run writes a truncated layer under the real filename and clears the
    # .partial guard. That happened - a GitHub run shipped 10,500 of
    # 10,651 superficial polygons as if complete, and the missing 151 read
    # as "no deposits here", moving sub_score on 1,560 districts.
    matched = None
    if os.path.exists(meta):
        try:
            with open(meta, encoding="utf-8") as fh:
                matched = json.load(fh).get("numberMatched")
        except (OSError, ValueError):
            matched = None
    with open(ckpt, "a", encoding="utf-8") as ck:
        while True:
            offset = len(features)
            if matched is not None and offset >= matched:
                break
            data = _get(_page_url(cfg, offset))
            if data is None:
                print(f"  throttled at offset {offset} after {RETRIES} "
                      f"attempts - progress is checkpointed, so rerunning "
                      f"resumes here rather than restarting", flush=True)
                stalled = True
                break
            if matched is None:
                matched = data.get("numberMatched")
                with open(meta, "w", encoding="utf-8") as mh:
                    json.dump({"numberMatched": matched}, mh)
            got = data.get("features", [])
            if not got:
                break
            for f in got:
                props = f.get("properties", {})
                rec = {
                    "type": "Feature",
                    "properties": {k: props.get(k) for k in cfg["keep"]},
                    "geometry": f.get("geometry"),
                }
                features.append(rec)
                ck.write(json.dumps(rec) + "\n")
            ck.flush()
            print(f"  {len(features)}/{matched}", flush=True)
            if len(features) < matched:
                time.sleep(PACE)

    # A short geology fetch is invisible downstream - missing polygons read
    # as "no data here" and quietly change district scores, the same trap
    # the raster fetchers guard with .partial. Do the same rather than
    # letting an incomplete layer become model input.
    out = cfg["out"]
    # Unknown total counts as incomplete. "We could not check" must never
    # be treated as "it is fine" for a layer whose absence is invisible
    # downstream.
    incomplete = matched is None or len(features) != matched
    if incomplete:
        out += ".partial"
        print(f"INCOMPLETE: {len(features)} of "
              f"{matched if matched is not None else 'unknown'} features "
              f"-> writing {out} so it cannot be used as input")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    size = os.path.getsize(out) / 1e6
    print(f"wrote {out}: {len(features)} features ({size:.1f} MB)")

    if incomplete:
        # Keep the checkpoint - that is the whole point, the rerun resumes
        # from it. Also drop any stale complete copy, so a half layer can
        # never sit next to a full one and get picked up by mistake.
        if os.path.exists(cfg["out"]):
            os.remove(cfg["out"])
    else:
        os.remove(ckpt)
        if os.path.exists(meta):
            os.remove(meta)
        # And clear the .partial left by the attempt that got throttled.
        # Without this a successful resume still trips the workflow's
        # "reject incomplete geology" guard, which globs for *.partial -
        # the layer would be complete and the build would refuse to start.
        stale = cfg["out"] + ".partial"
        if os.path.exists(stale):
            os.remove(stale)
            print(f"  cleared {stale} from the earlier throttled attempt")
    return incomplete


def main():
    which = "superficial" if "--superficial" in sys.argv[1:] else "bedrock"
    print(f"BGS 625k {which} -> {LAYERS[which]['out']}")
    if fetch(LAYERS[which]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
