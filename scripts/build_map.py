"""Assemble the interactive map pages and their data files.

TWO resolutions of the same model, from ONE template
(map/template.html), because their behaviour must not drift apart:

  districts  data/districts_risk.geojson  2,736 units -> map/uk_home_insurance_risk_map.html
  sectors    data/sectors_risk.geojson   10,398 units -> map/uk_sector_risk_map.html

The model writes the same OUTPUT_COLUMNS at both resolutions, so the
popup, metrics, legend and keyboard routes are literally the same code;
only the nouns, counts, sibling link and data URL are substituted.

The data is fetched, NOT inlined: inlined it made the district page
5.08 MB, and the sector data is three times that again. Each page gets
a web asset trimmed to the columns the template actually reads and
rounded to 4dp - the model output keeps full precision, but shipping
`4.6226001` to a popup that renders `£5` is 30% of the payload for
nothing. Sectors: 15.8 MB -> 13.4 MB raw, ~2.2 MB over the wire once
GitHub Pages gzips it.

Because of the fetch, the pages need HTTP even locally:
`python -m http.server` inside docs/ - file:// will not serve them.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

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


def web_asset(geojson_path, keep):
    """Minified GeoJSON carrying only `keep`, rounded for the wire.

    `keep` must be SORTED, not a set: Python randomises string hashing
    per process, so iterating a set of column names writes the JSON keys
    in a different order on every run. The bytes then differ between a
    laptop build and a CI build of identical inputs, and CI's
    docs/-is-stale check fails with a diff nobody can see (it did).
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
        out.append({"type": "Feature", "properties": props,
                    "geometry": feat["geometry"]})
    return json.dumps({"type": "FeatureCollection", "features": out},
                      separators=(",", ":")), len(out)


# (model output, page, data asset, substitutions)
BUILDS = [
    dict(
        source="data/districts_risk.geojson",
        page="uk_home_insurance_risk_map.html",
        asset="map_data.geojson",
        unit="district", unit_plural="districts", example="YO25",
        csv="assets/uk_district_risk.csv",
        omit=[],
        title="Interactive map — UK Home Insurance Risk Map",
        sibling='Districts &middot; <a href="sectors.html">switch to the '
                'finer postcode-sector map &rarr;</a>',
        note="",
    ),
    dict(
        source="data/sectors_risk.geojson",
        page="uk_sector_risk_map.html",
        asset="sector_data.geojson",
        unit="sector", unit_plural="sectors", example="YO25 6",
        csv="assets/uk_sector_risk.csv",
        # the EA climate extents have not been fetched at sector
        # resolution, so cc_covered is 0 everywhere; see the note below
        omit=["cc_uplift"],
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
             'outlines it inherits (median IoU 0.706 vs 0.689). '
             '<b>The climate-change repricing is not modelled at this '
             'resolution yet</b>; use the district map for that layer.</p>',
    ),
]


def main():
    template = read("map", "template.html")
    leaflet_js = read("assets", "leaflet.js").replace("</script>", "<\\/script>")
    leaflet_css = read("assets", "leaflet.css")
    keep = columns_read_by_template(template)
    print(f"template reads {len(keep)} columns")

    for b in BUILDS:
        data, n = web_asset(b["source"], keep)
        html = (template
                .replace("__LEAFLET_CSS__", leaflet_css)
                .replace("__LEAFLET_JS__", leaflet_js)
                .replace("__PAGE_TITLE__", b["title"])
                .replace("__DATA_ASSET__", "assets/" + b["asset"])
                .replace("__CSV_ASSET__", b["csv"])
                .replace("__SIBLING_LINK__", b["sibling"])
                .replace("__GEOGRAPHY_NOTE__", b["note"])
                .replace("__OMIT_METRICS__", json.dumps(b["omit"]))
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

        data_out = os.path.join(ROOT, "map", b["asset"])
        with open(data_out, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"wrote {b['asset']} ({n:,} units, "
              f"{os.path.getsize(data_out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
