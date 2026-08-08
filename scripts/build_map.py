"""Assemble the interactive map HTML and its data file.

Inlines Leaflet 1.9.4 (assets/) into map/template.html ->
map/uk_home_insurance_risk_map.html, and minifies
data/districts_risk.geojson -> map/map_data.geojson, which the page
fetches at runtime.

The data is fetched, NOT inlined: inlined it made the page 5.08 MB —
100x every other page and re-downloaded on every visit, since the HTML
carried the data. The pair is published by build_site.py (the HTML with
site chrome as docs/map.html, the data as docs/assets/map_data.geojson).
Because of the fetch, the page needs HTTP even locally:
`python -m http.server` inside docs/ — file:// will not serve it.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def main():
    template = read("map", "template.html")
    leaflet_js = read("assets", "leaflet.js")
    leaflet_css = read("assets", "leaflet.css")
    geojson = json.dumps(json.loads(read("data", "districts_risk.geojson")),
                         separators=(",", ":"))

    # </script> inside inlined JS would terminate the script tag early
    leaflet_js = leaflet_js.replace("</script>", "<\\/script>")

    html = (template
            .replace("__LEAFLET_CSS__", leaflet_css)
            .replace("__LEAFLET_JS__", leaflet_js))

    out = os.path.join(ROOT, "map", "uk_home_insurance_risk_map.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {out} ({os.path.getsize(out) / 1e3:.0f} KB)")

    data_out = os.path.join(ROOT, "map", "map_data.geojson")
    with open(data_out, "w", encoding="utf-8") as f:
        f.write(geojson)
    print(f"wrote {data_out} ({os.path.getsize(data_out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
