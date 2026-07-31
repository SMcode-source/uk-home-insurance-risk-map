"""Assemble the public website into docs/ (GitHub Pages source folder).

  docs/index.html        landing page  (site/index.template.html + live numbers)
  docs/methodology.html  methodology   (site/methodology.template.html)
  docs/map.html          the Leaflet map, with site nav injected
  docs/years.html        the year analysis, with site nav injected
  docs/assets/site.css   shared styles
  docs/.nojekyll         stop Pages running Jekyll over the output

The map/years pages are the self-contained artefacts produced by
build_map.py / build_analysis.py; this script only wraps them in the site
chrome so the whole thing navigates as one website.
"""

import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SITE = os.path.join(ROOT, "site")
DOCS = os.path.join(ROOT, "docs")
REPO_URL = "https://github.com/SMcode-source/uk-home-insurance-risk-map"

PAGES = [("index.html", "Overview"), ("map.html", "Map"),
         ("years.html", "Good vs bad years"), ("methodology.html", "Methodology")]

# Recognisable names for districts that top the premium ranking.
PLACES = {
    "ME11": "Isle of Sheppey", "ME12": "Isle of Sheppey",
    "LA4": "Morecambe", "LA5": "Carnforth",
    "HU1": "Hull", "HU2": "Hull", "HU3": "Hull", "HU4": "Hull",
    "HU5": "Hull", "HU6": "Hull", "HU7": "Hull", "HU8": "Hull",
    "HU9": "Hull",
    "TW18": "Staines-upon-Thames", "TW19": "Stanwell Moor",
    "PR9": "Southport", "PO11": "Hayling Island", "PO20": "Selsey",
    "PO4": "Southsea", "PO40": "Freshwater, IoW",
    "CO13": "Frinton-on-Sea", "CO14": "Walton-on-the-Naze",
    "CO15": "Clacton-on-Sea", "CO12": "Harwich", "CO16": "St Osyth",
    "SS3": "Shoeburyness", "DT4": "Weymouth", "FY8": "Lytham St Annes",
    "CM77": "Braintree", "CM6": "Great Dunmow", "CB10": "Saffron Walden",
    "SG16": "Henlow", "SG15": "Arlesey", "SG6": "Letchworth",
    "SG18": "Biggleswade", "AL8": "Welwyn Garden City", "WD5": "Abbots Langley",
    "HP10": "High Wycombe", "SP1": "Salisbury", "SP2": "Salisbury",
    "SP4": "Amesbury", "DT1": "Dorchester", "DT11": "Blandford Forum",
    "CT14": "Deal", "CT16": "Dover", "CT17": "Dover",
}

PERIL_NAMES = {"el_fl": "flood", "el_sub": "subsidence",
               "el_wx": "weather", "el_gw": "groundwater"}


def nav_html(current):
    links = []
    for href, label in PAGES:
        cur = ' aria-current="page"' if href == current else ""
        links.append(f'<a class="navlink" href="{href}"{cur}>{label}</a>')
    dots = ('<span class="dots">'
            '<i style="background:var(--sub)"></i>'
            '<i style="background:var(--wx)"></i>'
            '<i style="background:var(--fl)"></i>'
            '<i style="background:var(--gw)"></i></span>')
    return (
        '<nav class="site-nav">'
        f'<a class="brand" href="index.html">{dots}'
        '<span class="txt">UK Home Insurance Risk Map</span></a>'
        + "".join(links)
        + '<span class="spacer"></span>'
        f'<a class="ghlink" href="{REPO_URL}">GitHub ↗</a>'
        '</nav>'
    )


def drivers(props):
    """Short phrase naming the perils that carry this district's expected loss."""
    parts = {k: props.get(k, 0) or 0 for k in PERIL_NAMES}
    total = sum(parts.values()) or 1.0
    ranked = sorted(parts.items(), key=lambda kv: -kv[1])
    named = [(PERIL_NAMES[k], v / total) for k, v in ranked if v / total >= 0.18]
    if not named:
        named = [(PERIL_NAMES[ranked[0][0]], ranked[0][1] / total)]
    if len(named) == 1:
        return f"{named[0][0].capitalize()}-dominated ({named[0][1]:.0%} of E[loss])"
    lead = " + ".join(n for n, _ in named[:3])
    return f"{lead.capitalize()} ({named[0][1]:.0%} / {named[1][1]:.0%})"


def load_stats():
    with open(os.path.join(ROOT, "data", "year_analysis.json")) as fh:
        ya = json.load(fh)
    with open(os.path.join(ROOT, "data", "districts_risk.geojson"),
              encoding="utf-8") as fh:
        gj = json.load(fh)

    feats = [f["properties"] for f in gj["features"]]
    prem = sorted(p["premium"] for p in feats)
    buckets = {b["label"]: b for b in ya["buckets"]}
    typ, bad, cat = buckets["typical"], buckets["bad"], buckets["catastrophic"]

    top = sorted(feats, key=lambda p: -p["premium"])[:6]
    rows = []
    for p in top:
        rows.append(
            "<tr>"
            f'<td><strong>{p["name"]}</strong></td>'
            f'<td>{PLACES.get(p["name"], "postcode area " + p["area"])}</td>'
            f'<td class="num"><strong>£{p["premium"]:,.0f}</strong></td>'
            f'<td class="num">{p["sub_score"]:.2f}</td>'
            f'<td class="num">{p["wx_score"]:.2f}</td>'
            f'<td class="num">{p["fl_score"]:.2f}</td>'
            f'<td class="num">{p["gw_score"]:.2f}</td>'
            f'<td>{drivers(p)}</td>'
            "</tr>")

    mult = lambda a, b: f"{(a / b):.0f}" if b else "—"
    return {
        "__N_DISTRICTS__": f"{len(feats):,}",
        "__N_SIM__": f"{ya['n_sim']:,}",
        "__PREM_MIN__": f"{prem[0]:,.0f}",
        "__PREM_MAX__": f"{prem[-1]:,.0f}",
        "__CAT_UPLIFT__": f"{100 * (cat['mean_total'] - cat['indep_mean_total']) / cat['indep_mean_total']:.0f}",
        "__CAT_COST__": f"{cat['mean_total']:,.0f}",
        "__CAT_INDEP__": f"{cat['indep_mean_total']:,.0f}",
        "__TYPICAL__": f"{typ['mean_total']:,.0f}",
        "__BAD__": f"{bad['mean_total']:,.0f}",
        "__FL_MULT__": mult(bad["mean_fl"], typ["mean_fl"]),
        "__SUB_MULT__": mult(bad["mean_sub"], typ["mean_sub"]),
        "__WX_MULT__": mult(bad["mean_wx"], typ["mean_wx"]),
        "__TOP_ROWS__": "\n        ".join(rows),
        "__REPO_URL__": REPO_URL,
    }


def render_template(name, out_name, stats):
    with open(os.path.join(SITE, name), encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("__NAV__", nav_html(out_name))
    for k, v in stats.items():
        html = html.replace(k, v)
    write(out_name, html)


def wrap_generated(src, out_name, extra_css=""):
    """Inject site stylesheet + nav into a generated self-contained page."""
    with open(src, encoding="utf-8") as fh:
        html = fh.read()
    # site.css goes FIRST so the page's own <style> keeps precedence for
    # shared tokens; the per-page override goes LAST so it beats them.
    html = html.replace(
        "<head>", '<head>\n<link rel="stylesheet" href="assets/site.css">', 1)
    if extra_css:
        html = html.replace("</head>", f"<style>{extra_css}</style>\n</head>", 1)
    html = re.sub(r"<body([^>]*)>", r"<body\1>\n" + nav_html(out_name), html,
                  count=1)
    write(out_name, html)


def write(rel, content):
    path = os.path.join(DOCS, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"  {rel}  ({os.path.getsize(path) / 1e3:.0f} KB)")


MAP_CSS = """
/* full-bleed map sits below the fixed site nav */
.site-nav { position: fixed; top: 0; left: 0; right: 0; }
#map { top: 52px; inset: 52px 0 0 0; }
#controls { top: 64px; }
#legend, #about { bottom: 22px; }
body { overflow: hidden; }
"""

YEARS_CSS = """
.wrap { padding-top: 8px; }
"""


def main():
    print("building site -> docs/")
    os.makedirs(DOCS, exist_ok=True)
    stats = load_stats()

    render_template("index.template.html", "index.html", stats)
    render_template("methodology.template.html", "methodology.html", stats)
    wrap_generated(os.path.join(ROOT, "map", "uk_home_insurance_risk_map.html"),
                   "map.html", MAP_CSS)
    wrap_generated(os.path.join(ROOT, "analysis", "uk_risk_year_analysis.html"),
                   "years.html", YEARS_CSS)

    os.makedirs(os.path.join(DOCS, "assets"), exist_ok=True)
    shutil.copy(os.path.join(SITE, "assets", "site.css"),
                os.path.join(DOCS, "assets", "site.css"))
    print("  assets/site.css")
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("  .nojekyll")
    print("done")


if __name__ == "__main__":
    main()
