"""Assemble the self-contained interactive map HTML.

Inlines Leaflet 1.9.4 (assets/) and data/districts_risk.geojson into
map/template.html -> map/uk_home_insurance_risk_map.html.
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

    # </script> inside inlined JS or data would terminate the script tag early
    leaflet_js = leaflet_js.replace("</script>", "<\\/script>")
    geojson = geojson.replace("</", "<\\/")

    html = (template
            .replace("__LEAFLET_CSS__", leaflet_css)
            .replace("__LEAFLET_JS__", leaflet_js)
            .replace("__DATA__", geojson))

    out = os.path.join(ROOT, "map", "uk_home_insurance_risk_map.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
