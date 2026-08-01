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

import csv
import io
import json
import os
import re
import shutil

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SITE = os.path.join(ROOT, "site")
DOCS = os.path.join(ROOT, "docs")
REPO_URL = "https://github.com/SMcode-source/uk-home-insurance-risk-map"
SITE_URL = "https://smcode-source.github.io/uk-home-insurance-risk-map/"

# Per-page social metadata. Descriptions are what appears under the link
# preview in Slack/WhatsApp/X, so they say what the page shows.
META = {
    "index.html": (
        "UK Home Insurance Risk Map",
        "Subsidence, weather, flood and groundwater risk for 2,736 UK postcode "
        "districts, joined by a vine copula and calibrated to published ABI "
        "payouts. Built entirely on open data."),
    "map.html": (
        "Interactive map — UK Home Insurance Risk Map",
        "Eight switchable layers across 2,736 postcode districts: rating group, "
        "technical premium, each peril score, and the capital charge. Click any "
        "district for its full risk breakdown."),
    "years.html": (
        "Good years vs bad years — UK Home Insurance Risk Map",
        "What separates a quiet year from an expensive one: cost by peril, how "
        "widely claims spread, an exceedance curve, and a backtest against 35 "
        "years of real UK weather."),
    "methodology.html": (
        "Methodology — UK Home Insurance Risk Map",
        "How the four peril scores are built from open data, how the C-vine "
        "copula joins them, why the risk measure is TVaR, and how to reproduce "
        "the whole pipeline."),
}


def head_tags(page):
    """Favicon set + Open Graph/Twitter card, identical on every page."""
    title, desc = META[page]
    url = SITE_URL + ("" if page == "index.html" else page)
    img = SITE_URL + "assets/social.png"
    return f"""<link rel="icon" type="image/svg+xml" href="assets/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="assets/favicon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="assets/apple-touch-icon.png">
<meta name="description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="UK Home Insurance Risk Map">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Choropleth of Great Britain shaded by home-insurance rating group, with the title UK Home Insurance Risk Map">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{img}">"""

# (href, full label, short label for narrow screens)
PAGES = [("index.html", "Overview", "Overview"),
         ("map.html", "Map", "Map"),
         ("years.html", "Good vs bad years", "Years"),
         ("methodology.html", "Methodology", "Method")]

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
    for href, label, short in PAGES:
        cur = ' aria-current="page"' if href == current else ""
        # both labels ship; CSS shows the short one on narrow screens so the
        # nav fits without sideways scrolling
        inner = (f'<span class="nav-full">{label}</span>'
                 f'<span class="nav-short">{short}</span>') if short != label \
            else label
        links.append(f'<a class="navlink" href="{href}"{cur}>{inner}</a>')
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

    mult = lambda a, b: f"{(a / b):.1f}" if b else "—"

    dep_path = os.path.join(ROOT, "data", "dependence.json")
    dep_ratio, dep_vine, dep_indep = "—", "—", "—"
    if os.path.exists(dep_path):
        with open(dep_path) as fh:
            dep = json.load(fh)
        dep_ratio = f"{dep['multi_peril_ratio']:.0f}"
        dep_vine = f"{100 * dep['multi_peril_vine']:.2f}"
        dep_indep = f"{100 * dep['multi_peril_indep']:.3f}"

    # optional: sensitivity.json drives an extra landing-page finding
    sens_path = os.path.join(ROOT, "data", "sensitivity.json")
    sens_finding = ""
    if os.path.exists(sens_path):
        with open(sens_path) as fh:
            s = json.load(fh)
        dep = max(s[k]["group_churn_pct"] for k in
                  ("theta_low", "theta_high", "rho2_zero", "rho2_high")
                  if k in s)
        marg = max(s[k]["group_churn_pct"] for k in
                   ("sev_sigma_up", "flood_freq_150") if k in s)
        up_lo = s.get("theta_low", {}).get("mean_uplift_pct")
        up_hi = s.get("flood_freq_150", {}).get("mean_uplift_pct")
        sens_finding = f"""<div class="finding">
      <div class="num">{dep:.0f}% vs {marg:.0f}%<small>rating-group churn</small></div>
      <div>
        <h3>Dependence sets the tail; the marginals set the ranking</h3>
        <p>Perturbing the copula — dependence strength ±25%, conditional correlations
        zeroed or doubled — moves at most <b>{dep:.0f}%</b> of districts into a different
        rating group. Perturbing the loss assumptions moves up to <b>{marg:.0f}%</b>. The
        vine is what makes the tail honest (uplift ranges {up_lo:.0f}–{up_hi:.0f}% across
        scenarios), but if you want the <i>ranking</i> right, spend your effort on claim
        frequencies and severities. Every scenario is tabulated on the
        <a href="years.html#sens-section">year analysis page</a>.</p>
      </div>
    </div>"""

    return {
        "__SENS_FINDING__": sens_finding,
        "__N_DISTRICTS__": f"{len(feats):,}",
        "__N_HOUSEHOLDS__": f"{sum(p.get('households', 0) for p in feats) / 1e6:.1f}m",
        "__N_SIM__": f"{ya['n_sim']:,}",
        "__PREM_MIN__": f"{prem[0]:,.0f}",
        "__PREM_MAX__": f"{prem[-1]:,.0f}",
        "__CAT_UPLIFT__": f"{100 * (cat['mean_total'] - cat['indep_mean_total']) / cat['indep_mean_total']:.0f}",
        "__DIST_UPLIFT__": f"{np.mean([p['uplift_pct'] for p in feats]):.0f}",
        "__MEAN_EL__": f"{np.mean([p['el_total'] for p in feats]):,.0f}",
        "__MEAN_CAPITAL__": f"{np.mean([p.get('capital', 0) for p in feats]):,.0f}",
        "__MEAN_STANDALONE__": f"{np.mean([p['tvar99_vine'] for p in feats]):,.0f}",
        "__PORT_TVAR__": f"{np.mean([p.get('tvar99_euler', 0) for p in feats]):,.0f}",
        "__DIVERSIFICATION__": f"{100 * (1 - np.mean([p.get('tvar99_euler', 0) for p in feats]) / np.mean([p['tvar99_vine'] for p in feats])):.0f}",
        "__MULTI_RATIO__": dep_ratio,
        "__MULTI_VINE__": dep_vine,
        "__MULTI_INDEP__": dep_indep,
        "__CAT_VS_INDEP__": f"{100 * (cat['mean_total'] - cat['indep_mean_total']) / cat['indep_mean_total']:.1f}",
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
    html = html.replace("__HEAD__", head_tags(out_name))
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
        "<head>",
        '<head>\n<link rel="stylesheet" href="assets/site.css">\n'
        + head_tags(out_name), 1)
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

/* Phones: the three floating panels have to share one small screen.
   Full-width stacked panels, each capped and internally scrollable, so
   they never overlap each other and always leave map visible between. */
@media (max-width: 640px) {
  #controls {
    top: 60px; left: 8px; right: 8px; max-width: none;
    max-height: 34vh; overflow-y: auto; padding: 10px 12px;
  }
  #controls h1 { font-size: 14px; }
  #controls .sub { display: none; }
  .metric-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
  .metric-btns button { font-size: 12px; padding: 8px; }
  #legend {
    left: 8px; right: 8px; bottom: 62px; min-width: 0;
    max-height: 24vh; overflow-y: auto; padding: 10px 12px;
  }
  #legend .legend-row span { font-size: 11px; }
  #about { left: 8px; right: 8px; bottom: 8px; max-width: none; max-height: 40vh; overflow-y: auto; }
}
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

    # compact per-district lookup for the landing-page search (no geometry)
    with open(os.path.join(ROOT, "data", "districts_risk.geojson"),
              encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    lookup = sorted(
        ({"n": p["name"], "g": int(p["group"]), "p": round(p["premium"]),
          "s": round(p["sub_score"], 2), "w": round(p["wx_score"], 2),
          "f": round(p["fl_score"], 2), "gw": round(p["gw_score"], 2),
          "u": round(p["uplift_pct"], 1),
          # premium build-up: four expected losses + allocated capital
          "es": round(p["el_sub"]), "ew": round(p["el_wx"]),
          "ef": round(p["el_fl"]), "eg": round(p["el_gw"]),
          "c": round(p.get("capital", 0)),
          "h": round(p.get("households", 0))} for p in feats),
        key=lambda d: d["n"])
    write("assets/districts.json", json.dumps(lookup, separators=(",", ":")))

    # full table as CSV, for anyone who wants the numbers directly
    cols = ["name", "area", "households", "group", "premium", "capital",
            "el_total",
            "el_sub", "el_wx", "el_fl", "el_gw", "sub_score", "wx_score",
            "fl_score", "gw_score", "f_high", "f_low", "sw_high", "sw_low",
            "gw_frac", "wind_ms", "gust_rp50", "rain10_days", "precip_mm",
            "tvar99_vine", "tvar99_euler", "uplift_pct", "geol"]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(cols)
    for p in sorted(feats, key=lambda d: d["name"]):
        w.writerow([p.get(c, "") for c in cols])
    write("assets/uk_district_risk.csv", out.getvalue())
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("  .nojekyll")
    print("done")


if __name__ == "__main__":
    main()
