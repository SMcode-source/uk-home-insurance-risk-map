"""Assemble the interactive map pages and their data files.

TWO resolutions of the same model, from ONE template
(map/template.html), because their behaviour must not drift apart:

  districts  data/districts_risk.geojson  2,736 units -> map/uk_home_insurance_risk_map.html
  sectors    data/sectors_risk.geojson   10,398 units -> map/uk_sector_risk_map.html

The model writes the same OUTPUT_COLUMNS at both resolutions, so the
popup, metrics, legend and keyboard routes are literally the same code;
only the nouns, counts, sibling link and data URL are substituted.

The pages carry no data of their own. They read vector tiles, popup
shards and a name index, all built by build_tiles.py; this script writes
only the HTML, plus the one thing that cannot be left to the browser -
the national quantile breaks (see quantile_breaks).

That replaced a whole-country GeoJSON per page, fetched at every zoom
whether you were looking at the country or one street: 0.9 MB gzipped
for districts, 2.6 MB for sectors. Tiles cost 394 KB and 1.05 MB for
the opening view and FALL as you zoom in, and - the reason it was worth
doing - they can carry full-resolution boundaries, which as a single
file would have been 3.7 MB and 5.7 MB.

The pages need HTTP even locally: `python -m http.server` inside docs/ -
file:// will not serve tiles or shards.
"""

import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

# The ABI context behind the headline share is imported from the model
# rather than restated, exactly as build_site.py does it: two copies of
# total_home_paid is how the published pages drift apart.
sys.path.insert(0, HERE)
from build_model import ABI, POLICIES  # noqa: E402

# Coordinates are already written at ~100 m precision by build_model, and
# properties are 3x the geometry in these files, so trimming columns is
# the lever that matters - simplifying geometry would only risk slivers
# between neighbouring polygons for a fraction of the saving.
ROUND_DP = 4


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def columns_read_by_template(template=None):
    """Every `p.<col>` / `.properties.<col>` the map template reads.

    THE single source of truth for what a web asset must contain, used
    by the asset writer here and by the contract tests. The `\\b` is
    load-bearing: without it `ramp.length` and `tooltip.district-tip`
    match as `p.length` / `p.district`.
    """
    tpl = template if template is not None else read("map", "template.html")
    cols = set(re.findall(r"\bp\.([A-Za-z_][A-Za-z_0-9]*)", tpl))
    cols |= set(re.findall(r"\.properties\.([A-Za-z_][A-Za-z_0-9]*)", tpl))
    return cols


# Read by the popup and nothing else. The popup renders ONE unit at a
# time, so these need not travel with every unit in the viewport.
POPUP_ONLY_FUNCS = ("popupHtml", "erosionBlock")


def _function_body(tpl, name):
    """Source of `function <name>(...) {...}`, by brace matching."""
    m = re.search(r"\bfunction\s+" + name + r"\s*\([^)]*\)\s*\{", tpl)
    if not m:
        raise SystemExit(f"map/template.html has no function {name}() - "
                         f"the tile/popup column split reads it by name")
    i, depth = m.end(), 1
    while depth:
        if tpl[i] == "{":
            depth += 1
        elif tpl[i] == "}":
            depth -= 1
        i += 1
    return tpl[m.start():i]


def tile_columns(template=None):
    """Columns a vector tile must carry: everything the template reads
    OUTSIDE the popup.

    Derived, not listed. A column that colours the map but is missing
    from the tile paints every unit the same and nothing raises - so the
    split has to follow the template automatically. Add a metric and its
    column joins the tile; move a field into the popup and it leaves.
    """
    tpl = template if template is not None else read("map", "template.html")
    outside = tpl
    for fn in POPUP_ONLY_FUNCS:
        outside = outside.replace(_function_body(tpl, fn), "")
    return columns_read_by_template(outside)


def quantile_breaks(values, n):
    """The `quantileBreaks` in map/template.html, moved to build time.

    The JS cut these from whatever features were loaded. That was fine
    while the browser fetched the whole country as one file, and wrong
    the moment it stops doing so: under vector tiles only the viewport's
    tiles are present, so a district would change colour - and the
    legend change under it - as you panned. Cutting them here fixes the
    scale to the full national distribution, once.

    Must stay identical to the JS it replaces (sort ascending, take
    s[floor(i * len / n)]) or every published map silently recolours.
    """
    s = sorted(values)
    return [s[(i * len(s)) // n] for i in range(1, n)]


# Metric -> which units it cuts over. Erosion is cut over the COASTAL
# units alone: quantiles across every district would put all six breaks
# at zero, since most of the country is nowhere near the sea.
QUANTILE_METRICS = {
    "premium":     lambda p: True,
    "var995_vine": lambda p: True,
    "capital":     lambda p: True,
    "er_head":     lambda p: p["er_head"] > 0,
}
QUANTILE_N = 7


def rounded_props(geojson_path, keep):
    """The property values the browser will actually see.

    This was web_asset(), which also wrote a whole-country GeoJSON for
    the page to fetch. The map reads vector tiles now (build_tiles.py),
    so that file is gone and only the values survive - the colour breaks
    still have to be cut over exactly what ships, and build_tiles.py
    rounds identically.

    `keep` is still sorted before use. It no longer decides the bytes of
    a written file, but it does decide the order of anything derived
    from it, and a set iterates differently every process because Python
    randomises string hashing - which once put a laptop build and a CI
    build of identical inputs at odds over a diff nobody could see.
    """
    keep = sorted(keep)
    with open(os.path.join(ROOT, geojson_path), encoding="utf-8") as f:
        gj = json.load(f)

    missing = set(keep) - set(gj["features"][0]["properties"])
    if missing:
        raise SystemExit(
            f"{geojson_path} lacks {sorted(missing)}, which the map template "
            f"reads - the popup would render `undefined`")

    out = []
    for feat in gj["features"]:
        src = feat["properties"]
        props = {}
        for k in keep:
            v = src[k]
            if isinstance(v, float):
                v = round(v, ROUND_DP)
                if v == int(v):
                    v = int(v)
            props[k] = v
        out.append(props)
    return out


def metric_keys(template=None):
    """Every metric key the template's METRICS object declares.

    Parsed rather than listed so the relative-risk build's "omit all but
    one" set cannot drift when a metric is added: a hand-kept list would
    silently let the new metric onto a page built to show exactly one.
    """
    tpl = template if template is not None else read("map", "template.html")
    block = tpl[tpl.index("const METRICS = {"):]
    block = block[:block.index("\n};")]
    keys = re.findall(r"^  (\w+): \{", block, re.M)
    if len(keys) < 10:
        raise SystemExit(f"metric_keys found only {keys} - the METRICS "
                         f"declaration moved and the parser went stale")
    return keys


def weighted_median_premium(props):
    """Household-weighted median premium - the relative page's anchor.

    Weighted so a district counts as its people, not as one vote, and a
    median so the skewed top of the distribution cannot drag everyone
    else's ratio. Rounded to whole pounds: the figure is injected into a
    published page, and sub-pound precision would imply the model
    resolves the median finer than its inputs do.
    """
    rows = sorted((p["premium"], p.get("households", 1)) for p in props)
    total = sum(w for _, w in rows)
    acc = 0
    for v, w in rows:
        acc += w
        if acc >= total / 2:
            return round(v)
    return round(rows[-1][0])


# (model output, page, data asset, substitutions)
BUILDS = [
    dict(
        source="data/districts_risk.geojson",
        page="uk_home_insurance_risk_map.html",
        grain="districts",
        unit="district", unit_plural="districts", example="YO25",
        csv="assets/uk_district_risk.csv",
        omit=["rel"],
        default="group",
        title="The model — UK Home Insurance Risk Map",
        sibling='Districts &middot; <a href="sectors.html">switch to the '
                'finer postcode-sector map &rarr;</a>',
        note="",
    ),
    dict(
        source="data/sectors_risk.geojson",
        page="uk_sector_risk_map.html",
        grain="sectors",
        unit="sector", unit_plural="sectors", example="YO25 6",
        csv="assets/uk_sector_risk.csv",
        # only the relative view is omitted (it has its own page at
        # district grain): the EA climate editions were re-fetched over
        # the sectors on 2026-08-12, so this map carries every layer the
        # district map does
        omit=["rel"],
        default="group",
        title="Sector map — UK Home Insurance Risk Map",
        sibling='Sectors &middot; <a href="map.html">back to the '
                'postcode-district map &rarr;</a>',
        note='<p><b>Geography.</b> Postcode-sector boundaries are not '
             'published for England &amp; Wales, so these are <b>derived</b>: '
             'each district is partitioned between its own unit-postcode '
             'centroids (OS Code-Point Open) and the cells dissolved by '
             'sector digit. Scored against the one published set '
             '&mdash; NRS&rsquo;s official Scottish sectors &mdash; the '
             'derivation adds no measurable error beyond the district '
             'outlines it inherits (median IoU 0.706 vs 0.689).</p>',
    ),
    dict(
        # The relative-risk page: the district premium surface with one
        # metric only, expressed as a multiple of the household-weighted
        # national median. Same source, same tiles, same shards - the
        # build differs from the district map ONLY in which metrics show
        # and which one is the default. omit is computed in main() as
        # "every metric except rel", so a metric added to the template
        # cannot quietly appear on a page built to show exactly one.
        source="data/districts_risk.geojson",
        page="uk_relative_risk_map.html",
        grain="districts",
        unit="district", unit_plural="districts", example="YO25",
        csv="assets/uk_district_risk.csv",
        omit="ALL_BUT_REL",
        default="rel",
        title="Relative risk — UK Home Insurance Risk Map",
        sibling='Relative &middot; <a href="map.html">see every model '
                'layer on the full map &rarr;</a>',
        note='<p><b>Reading this map.</b> This is the <b>same technical '
             'premium</b> as the model map, re-expressed: each district '
             'is shown as a multiple of the UK median premium '
             '(&pound;__REL_MEDIAN_GBP__/yr, household-weighted), so '
             '2.00&times; means homes there carry twice the median '
             'modelled risk. Nothing new is modelled on this page &mdash; '
             'it exists because &ldquo;2.4&times; the UK median&rdquo; '
             'answers &ldquo;how exposed is my area?&rdquo; more directly '
             'than a &pound; figure does.</p>',
    ),
]


def headline(geojson_path):
    """Exposure-weighted eight-peril EL per policy, and its share of what
    all home claims cost - the same two numbers, on the same basis, that
    build_site.py injects as __MEAN_EL__ and __EL_CLAIMS_SHARE__."""
    with open(os.path.join(ROOT, geojson_path), encoding="utf-8") as f:
        feats = [x["properties"] for x in json.load(f)["features"]]
    el = np.array([p["el_total"] for p in feats], dtype=float)
    w = np.array([p.get("households", 1) for p in feats], dtype=float)
    mean_el = np.average(el, weights=w)
    return f"{mean_el:,.0f}", f"{100 * mean_el / (ABI['total_home_paid'] / POLICIES):.0f}"


def main():
    template = read("map", "template.html")
    keep = columns_read_by_template(template)
    print(f"template reads {len(keep)} columns")

    all_metrics = metric_keys(template)
    for b in BUILDS:
        props = rounded_props(b["source"], keep)
        n = len(props)
        omit = ([k for k in all_metrics if k != "rel"]
                if b["omit"] == "ALL_BUT_REL" else b["omit"])
        rel_median = weighted_median_premium(props)
        breaks = {k: quantile_breaks([p[k] for p in props if pick(p)],
                                     QUANTILE_N)
                  for k, pick in QUANTILE_METRICS.items()}
        # The two headline figures were HARDCODED in map/template.html
        # until 2026-08-25 ("~GBP 170/policy/yr, around 77%"). Nothing
        # regenerated them, so both published map pages kept quoting a
        # premium two publishes out of date while the data underneath
        # them was current - the pages are byte-identical each rebuild,
        # so no diff and no stale-check ever fired. They are injected
        # now, on the same exposure-weighted basis build_site.py uses.
        mean_el, claims_share = headline(b["source"])
        html = (template
                .replace("__MEAN_EL__", mean_el)
                .replace("__EL_CLAIMS_SHARE__", claims_share)
                .replace("__PAGE_TITLE__", b["title"])
                .replace("__TILE_ASSET__",
                         f"assets/tiles/{b['grain']}.pmtiles")
                .replace("__TILE_LAYER__", b["grain"])
                .replace("__UNITS_DIR__", f"assets/units/{b['grain']}/")
                .replace("__INDEX_ASSET__",
                         f"assets/{b['grain']}_index.json")
                .replace("__CSV_ASSET__", b["csv"])
                .replace("__SIBLING_LINK__", b["sibling"])
                .replace("__GEOGRAPHY_NOTE__",
                         b["note"].replace("__REL_MEDIAN_GBP__",
                                           f"{rel_median:,}"))
                .replace("__REL_MEDIAN__", str(rel_median))
                .replace("__DEFAULT_METRIC__", b["default"])
                .replace("__OMIT_METRICS__", json.dumps(omit))
                .replace("__QUANTILE_BREAKS__",
                         json.dumps(breaks, separators=(",", ":")))
                .replace("__N_UNITS__", f"{n:,}")
                .replace("__UNIT_PLURAL__", b["unit_plural"])
                .replace("__UNIT__", b["unit"])
                .replace("__EXAMPLE__", b["example"]))
        left = re.findall(r"__[A-Z][A-Z_0-9]*__", html)
        if left:
            raise SystemExit(f"unsubstituted placeholder(s) in {b['page']}: "
                             f"{sorted(set(left))}")

        out = os.path.join(ROOT, "map", b["page"])
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"wrote {b['page']} ({os.path.getsize(out) / 1e3:.0f} KB)")

        print(f"  {n:,} units, breaks cut over the whole country")


if __name__ == "__main__":
    main()
