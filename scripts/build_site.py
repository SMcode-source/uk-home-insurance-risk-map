"""Assemble the public website into docs/ (GitHub Pages source folder).

  docs/index.html        landing page  (site/index.template.html + live numbers)
  docs/methodology.html  methodology   (site/methodology.template.html)
  docs/map.html          the Leaflet map, with site nav injected
  docs/years.html        the year analysis, with site nav injected
  docs/assets/site.css   shared styles
  docs/.nojekyll         stop Pages running Jekyll over the output

The map/years pages are the artefacts produced by build_map.py /
build_analysis.py; this script only wraps them in the site chrome so the
whole thing navigates as one website. (years is self-contained; the map
fetches assets/map_data.geojson at runtime, copied in below.)
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
        # Keep under ~200 chars: Twitter and LinkedIn truncate around there,
        # so anything past it is lost from the shared preview.
        "Subsidence, weather, flood, groundwater and coastal erosion across "
        "2,736 UK postcode districts — a 5-dim vine copula calibrated to ABI "
        "payouts, plus a climate-change repricing. All open data."),
    "map.html": (
        "Interactive map — UK Home Insurance Risk Map",
        "Eleven layers across 2,736 postcode districts: rating group, "
        "premium, each peril score, surface-water depth, coastal erosion "
        "and the climate repricing. Click any district for its breakdown."),
    "sectors.html": (
        "Sector map — UK Home Insurance Risk Map",
        "The same model at postcode-sector resolution: 10,398 units "
        "instead of 2,736. Nineteen per cent of districts turn out to "
        "hold sectors that differ by more than 2x in premium."),
    "years.html": (
        "Good years vs bad years — UK Home Insurance Risk Map",
        "What separates a quiet year from an expensive one: cost by peril, how "
        "widely claims spread, an exceedance curve, and a backtest against 35 "
        "years of real UK weather."),
    "methodology.html": (
        "Methodology — UK Home Insurance Risk Map",
        "How the peril scores are built from open data, how the 5-dim C-vine "
        "joins them, why coastal erosion is modelled but not priced, why the "
        "measure is TVaR, and how to reproduce it all."),
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
         ("sectors.html", "Sector map", "Sectors"),
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



# The climate ramp, mirrored from map/template.html so the methodology
# figure and the live map say the same thing in the same colours. A test
# asserts the two stay identical - if you retune one, retune both.
CC_RAMP = ["#1c5cab", "#5598e7", "#b7d3f6", "#f0efec",
           "#f2b8b7", "#e34948", "#9c2b2a"]
CC_BREAKS = [-20, -5, -1, 1, 15, 50]
CC_NO_DATA = "#e4e2dd"

FOCUS = "HU8"          # the one district that FALLS under the scenario


def _polys(geom):
    """Every ring list in a geometry, whatever its type.

    GeometryCollection is not hypothetical here: make_valid emits two of
    them in the sector set, and a naive geom["coordinates"] raises.
    """
    if not geom:
        return []
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    if t == "GeometryCollection":
        return [r for g in geom.get("geometries", []) for r in _polys(g)]
    return []


def _bbox(geom):
    pts = [pt for poly in _polys(geom) for ring in poly for pt in ring]
    if not pts:
        return None
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _cc_colour(props):
    if not props.get("cc_covered"):
        return CC_NO_DATA
    v = props.get("cc_uplift_pct", 0.0)
    i = 0
    while i < len(CC_BREAKS) and v >= CC_BREAKS[i]:
        i += 1
    return CC_RAMP[i]


def _panel(feats, frame, title, focus_prefix, w=330, h=365, head=24):
    """One choropleth panel over `frame`, focus units outlined."""
    x0, y0, x1, y1 = frame
    # equirectangular is fine over 20 km; scale x by cos(lat) so the
    # coastline is not stretched
    import math
    kx = math.cos(math.radians((y0 + y1) / 2))
    sx = w / ((x1 - x0) * kx)
    sy = h / (y1 - y0)
    sc = min(sx, sy)
    ox = (w - (x1 - x0) * kx * sc) / 2
    oy = (h - (y1 - y0) * sc) / 2

    def pt(x, y):
        return (ox + (x - x0) * kx * sc, head + h - oy - (y - y0) * sc)

    body, focus_paths, focus_pts = [], [], []
    for f in feats:
        props = f["properties"]
        d = []
        for poly in _polys(f["geometry"]):
            for ring in poly:
                if len(ring) < 3:
                    continue
                d.append("M" + "L".join(
                    f"{a:.1f} {b:.1f}" for a, b in (pt(x, y) for x, y in ring)) + "Z")
        if not d:
            continue
        path = " ".join(d)
        body.append(f'<path d="{path}" fill="{_cc_colour(props)}" '
                    f'stroke="#ffffff" stroke-width="0.4" stroke-opacity="0.6"/>')
        name = props["name"]
        if name == focus_prefix or name.startswith(focus_prefix + " "):
            focus_paths.append(f'<path d="{path}" fill="none" stroke="var(--ink-1)" '
                               f'stroke-width="1.6"/>')
            b = _bbox(f["geometry"])
            focus_pts.append(pt((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))

    lx = sum(q[0] for q in focus_pts) / len(focus_pts) if focus_pts else w / 2
    ly = sum(q[1] for q in focus_pts) / len(focus_pts) if focus_pts else h / 2
    return f"""<svg viewBox="0 0 {w} {head + h}" role="img" aria-label="{title}">
      <text class="panel-title" x="0" y="14">{title}</text>
      <g clip-path="url(#frameclip)">{''.join(body)}{''.join(focus_paths)}</g>
      <text class="focus-label" x="{lx:.0f}" y="{ly:.0f}" text-anchor="middle"
            paint-order="stroke" stroke="var(--surface-1)" stroke-width="3.5"
            stroke-linejoin="round">{focus_prefix}</text>
      <clipPath id="frameclip"><rect x="0" y="{head}" width="{w}" height="{h}"/></clipPath>
    </svg>"""


def resolution_figure(districts, sectors):
    """Districts vs sectors over the same ground, on the climate layer.

    Built from the published GeoJSON at build time rather than pasted in
    as a screenshot: a screenshot of a map goes stale the next time the
    model is rebuilt, and this one cannot.
    """
    focus = next((f for f in districts if f["properties"]["name"] == FOCUS), None)
    if focus is None:
        return ""
    x0, y0, x1, y1 = _bbox(focus["geometry"])
    px, py = (x1 - x0) * 1.5, (y1 - y0) * 1.5
    frame = (x0 - px, y0 - py, x1 + px, y1 + py)

    def inside(f):
        b = _bbox(f["geometry"])
        return b and not (b[2] < frame[0] or b[0] > frame[2]
                          or b[3] < frame[1] or b[1] > frame[3])

    left = _panel([f for f in districts if inside(f)], frame,
                  "Districts", FOCUS)
    right = _panel([f for f in sectors if inside(f)], frame,
                   "Sectors", FOCUS)
    return f'<div class="res-figure">{left}{right}</div>'

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

    _w = np.array([p.get('households', 1) for p in feats], dtype=float)
    _prem = np.array([p['premium'] for p in feats], dtype=float)
    _el = np.array([p['el_total'] for p in feats], dtype=float)
    _cap = np.array([p.get('capital', 0) for p in feats], dtype=float)

    mult = lambda a, b: f"{(a / b):.1f}" if b else "—"

    dep_path = os.path.join(ROOT, "data", "dependence.json")
    dep_ratio, dep_vine, dep_indep = "—", "—", "—"
    dep_uplift, dep_ci = "—", "—"
    if os.path.exists(dep_path):
        with open(dep_path) as fh:
            dep = json.load(fh)
        dep_ratio = f"{dep['multi_peril_ratio']:.0f}"
        dep_vine = f"{100 * dep['multi_peril_vine']:.2f}"
        dep_indep = f"{100 * dep['multi_peril_indep']:.4f}"
        # The per-policy TVaR uplift is noise by construction, so its point
        # estimate wanders between runs. Injecting it rather than writing it
        # into the template stops the prose drifting away from the data.
        dep_uplift = f"{dep['tvar_uplift_pct']:+.1f}"
        lo, hi = dep["tvar_uplift_ci"]
        dep_ci = f"{lo:+.1f}% to {hi:+.1f}%"

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

    # Coastal erosion, computed from the data so the copy cannot drift.
    # "Saved" districts are the striking case: land the sea would take if
    # the defences were left to lapse, held at exactly zero by the adopted
    # Shoreline Management Plan.
    er_exposed = [p for p in feats if p.get("er_nfi105", 0) > 0]
    er_saved = [p for p in er_exposed if p.get("er_smp105", 0) == 0]
    er_worst = max(feats, key=lambda p: p.get("er_smp105", 0))

    # Climate repricing, over the districts the EA actually models. A
    # national average would be diluted by Wales and Scotland, which have
    # no future extents and so cannot move by construction.
    cc = [p for p in feats if p.get("cc_covered")]
    if cc:
        w = np.array([p.get("households", 1) for p in cc], dtype=float)
        cc_pct = 100 * (np.average([p["premium_cc"] for p in cc], weights=w)
                        / np.average([p["premium"] for p in cc], weights=w) - 1)
        cc_worst = max(cc, key=lambda p: p.get("cc_uplift_pct", 0))
        cc_bits = {
            "__CC_N__": f"{len(cc):,}",
            "__CC_UPLIFT__": f"{cc_pct:+.0f}",
            "__CC_WORST__": cc_worst["name"],
            "__CC_WORST_PCT__": f"{cc_worst.get('cc_uplift_pct', 0):+.0f}",
        }
    else:
        cc_bits = {"__CC_N__": "0", "__CC_UPLIFT__": "n/a",
                   "__CC_WORST__": "n/a", "__CC_WORST_PCT__": "n/a"}

    # Sector resolution: the spread a district price averages away, and
    # how well the derived boundaries score against Scotland's official
    # ones. Computed here so the published claims cannot drift from the
    # published data - the same rule the dependence uplift follows.
    with open(os.path.join(ROOT, "data", "sectors_risk.geojson"),
              encoding="utf-8") as fh:
        secs = [f["properties"] for f in json.load(fh)["features"]]
    grouped = {}
    for s in secs:
        grouped.setdefault(s["name"].rsplit(" ", 1)[0], []).append(s)
    multi = {d: g for d, g in grouped.items() if len(g) > 1}
    ratios = {}
    for d, g in multi.items():
        prem = [s["premium"] for s in g]
        ratios[d] = max(prem) / max(min(prem), 1e-9)
    worst = max(ratios, key=ratios.get)
    worst_prem = [s["premium"] for s in grouped[worst]]
    wide = sum(1 for r in ratios.values() if r > 2)
    sector_bits = {
        "__SECTOR_N__": f"{len(secs):,}",
        "__SECTOR_MULTI_N__": f"{len(multi):,}",
        "__SECTOR_SPREAD__": f"{np.median(list(ratios.values())):.2f}",
        "__SECTOR_WIDE_N__": f"{wide:,}",
        "__SECTOR_WIDE_PCT__": f"{100 * wide / len(ratios):.0f}",
        "__SECTOR_WORST__": worst,
        "__SECTOR_WORST_RATIO__": f"{ratios[worst]:.1f}",
        "__SECTOR_WORST_LO__": f"{min(worst_prem):,.0f}",
        "__SECTOR_WORST_HI__": f"{max(worst_prem):,.0f}",
        "__SECTOR_WORST_N__": f"{len(grouped[worst])}",
    }
    # the climate scenario at sector resolution, and the district figure
    # it should be compared against
    scc = [q for q in secs if q.get("cc_covered")]
    if scc:
        wcc = np.array([q.get("households", 1) for q in scc], float)
        s_pct = 100 * (np.average([q["premium_cc"] for q in scc], weights=wcc)
                       / np.average([q["premium"] for q in scc], weights=wcc) - 1)
        s_worst = max(scc, key=lambda q: q.get("cc_uplift_pct", 0))
        sector_bits.update({
            "__SECTOR_CC_N__": f"{len(scc):,}",
            "__SECTOR_CC_UPLIFT__": f"{s_pct:+.1f}",
            "__SECTOR_CC_WORST__": s_worst["name"],
            "__SECTOR_CC_WORST_PCT__": f"{s_worst['cc_uplift_pct']:+.0f}",
            "__SECTOR_CC_DOWN__": f"{sum(1 for q in scc if q['cc_uplift_pct'] < 0):,}",
            "__CC_DOWN__": f"{sum(1 for q in cc if q['cc_uplift_pct'] < 0):,}",
        })

    # the districts-vs-sectors figure, drawn from the published geometry
    with open(os.path.join(ROOT, "data", "districts_risk.geojson"),
              encoding="utf-8") as fh:
        dfeats = json.load(fh)["features"]
    with open(os.path.join(ROOT, "data", "sectors_risk.geojson"),
              encoding="utf-8") as fh:
        sfeats = json.load(fh)["features"]
    sector_bits["__RES_FIGURE__"] = resolution_figure(dfeats, sfeats)
    fdist = next(q for q in feats if q["name"] == FOCUS)
    fsec = sorted((q for q in secs if q["name"].startswith(FOCUS + " ")),
                  key=lambda q: q["cc_uplift_pct"])
    sector_bits.update({
        "__FOCUS__": FOCUS,
        "__FOCUS_PCT__": f"{fdist.get('cc_uplift_pct', 0):+.0f}",
        "__FOCUS_LO__": f"{fsec[0]['cc_uplift_pct']:+.0f}",
        "__FOCUS_HI__": f"{fsec[-1]['cc_uplift_pct']:+.0f}",
        "__FOCUS_LO_NAME__": fsec[0]["name"],
        "__FOCUS_HI_NAME__": fsec[-1]["name"],
        "__FOCUS_N__": str(len(fsec)),
    })

    val_path = os.path.join(ROOT, "data", "sector_validation.json")
    with open(val_path) as fh:
        val = json.load(fh)
    sector_bits.update({
        "__SECTOR_IOU__": f"{val['sector_iou_median']:.3f}",
        "__DISTRICT_IOU__": f"{val['district_iou_median']:.3f}",
        "__SECTOR_IOU_50__": str(val["pct_above_50"]),
        "__SECTOR_IOU_70__": str(val["pct_above_70"]),
    })

    return {
        **cc_bits,
        **sector_bits,
        "__SENS_FINDING__": sens_finding,
        "__EROSION_N__": f"{len(er_exposed):,}",
        "__EROSION_SAVED__": f"{len(er_saved):,}",
        "__EROSION_WORST__": er_worst["name"],
        "__EROSION_WORST_PCT__": f"{100 * er_worst.get('er_smp105', 0):.0f}",
        "__N_DISTRICTS__": f"{len(feats):,}",
        "__N_HOUSEHOLDS__": f"{sum(p.get('households', 0) for p in feats) / 1e6:.1f}m",
        "__N_SIM__": f"{ya['n_sim']:,}",
        "__PREM_MIN__": f"{prem[0]:,.0f}",
        "__PREM_MAX__": f"{prem[-1]:,.0f}",
        "__CAT_UPLIFT__": f"{100 * (cat['mean_total'] - cat['indep_mean_total']) / cat['indep_mean_total']:.0f}",
        "__DIST_UPLIFT__": f"{np.mean([p['uplift_pct'] for p in feats]):.0f}",
        # The premium split, exposure-weighted because that is what
        # "nationally" means everywhere else in this model. It is the
        # crispest answer to "what does the copula actually change":
        # expected loss is copula-independent by construction, so the
        # dependence structure can only reach price through the capital
        # charge - and only via the PORTFOLIO tail, never a district's own.
        "__EL_SHARE__": f"{100 * np.average(_el, weights=_w) / np.average(_prem, weights=_w):.0f}",
        "__CAPITAL_SHARE__": f"{100 * np.average(_cap, weights=_w) / np.average(_prem, weights=_w):.0f}",
        "__MEAN_EL__": f"{np.mean([p['el_total'] for p in feats]):,.0f}",
        "__MEAN_CAPITAL__": f"{np.mean([p.get('capital', 0) for p in feats]):,.0f}",
        "__MEAN_STANDALONE__": f"{np.mean([p['tvar99_vine'] for p in feats]):,.0f}",
        "__PORT_TVAR__": f"{np.mean([p.get('tvar99_euler', 0) for p in feats]):,.0f}",
        "__DIVERSIFICATION__": f"{100 * (1 - np.mean([p.get('tvar99_euler', 0) for p in feats]) / np.mean([p['tvar99_vine'] for p in feats])):.0f}",
        "__MULTI_RATIO__": dep_ratio,
        "__MULTI_VINE__": dep_vine,
        "__MULTI_INDEP__": dep_indep,
        "__TVAR_UPLIFT__": dep_uplift,
        "__TVAR_CI__": dep_ci,
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

/* NOTE - do not try to fix popup/panel overlap with z-index. Leaflet's
   .leaflet-map-pane carries a transform, which makes it a stacking
   context, so every pane inside it (popups included) is trapped below
   whatever that pane resolves to. Raising .leaflet-popup-pane changes
   nothing - measured - and raising .leaflet-map-pane lifts the whole map
   over the panels and hides them. The popup is kept clear of the panels
   by panning instead; see keepPopupClear() in the map template. */

/* The popup opens compact (headline, scores, disclosures), but a reader
   who unfolds everything is back to ~1,000px of content - taller than an
   800px laptop viewport - and Leaflet adds overflow handling only when
   given a maxHeight, which it never was. Cap it and let it scroll
   everywhere; the phone rule below tightens this to the gap between the
   floating panels. */
.leaflet-popup-content { max-height: 60vh; overflow-y: auto; }

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

  /* Leaflet puts the zoom buttons at the map's top-left, which on a phone
     is exactly where #controls sits. They were not merely hidden - they
     were unreachable, and a tap on "zoom out" landed on the metric button
     underneath, silently switching the map's layer instead of zooming.

     #controls starts 8px into the map and is capped at 34vh, so the band
     below that is free until #legend begins. Put the zoom there, and lift
     it above the panels (which sit at z-index 1000) so a panel growing
     can never bury it again. */
  .leaflet-top.leaflet-left { top: calc(34vh + 18px); z-index: 1100; }

  /* The popup must FIT the free band between #controls (top: 60px,
     max-height 34vh) and #legend (bottom: 62px, max-height 24vh), or
     keepPopupClear() has no clear position to move it to and leaves it
     under a panel - which is how the close button ended up untappable
     under the metric buttons (caught by the layout tests; the old cap of
     42vh - 165px plus Leaflet's ~35px of wrapper margins and tip was
     taller than the band by construction).
     Band = 100vh - (60 + 34vh) - (62 + 24vh) = 42vh - 122px. Less 2x8px
     keep-clear padding and ~35px chrome: content cap = 42vh - 173px.
     -180 leaves slack for font rounding. Width in vw so rotation is
     handled without JS. */
  .leaflet-popup-content { max-height: calc(42vh - 180px); overflow-y: auto; max-width: calc(100vw - 64px); }
  .leaflet-popup-content-wrapper { max-width: calc(100vw - 40px); }
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
    wrap_generated(os.path.join(ROOT, "map", "uk_sector_risk_map.html"),
                   "sectors.html", MAP_CSS)
    wrap_generated(os.path.join(ROOT, "analysis", "uk_risk_year_analysis.html"),
                   "years.html", YEARS_CSS)

    os.makedirs(os.path.join(DOCS, "assets"), exist_ok=True)
    shutil.copy(os.path.join(SITE, "assets", "site.css"),
                os.path.join(DOCS, "assets", "site.css"))
    print("  assets/site.css")

    # Each map's geometry+properties, fetched at runtime rather than
    # inlined (which made the district page 5.08 MB; the sector data is
    # three times that again). build_map.py trims these to the columns
    # the template reads - do not copy the raw model output here.
    for asset in ("map_data.geojson", "sector_data.geojson"):
        shutil.copy(os.path.join(ROOT, "map", asset),
                    os.path.join(DOCS, "assets", asset))
        print(f"  assets/{asset}  ("
              f"{os.path.getsize(os.path.join(DOCS, 'assets', asset)) / 1e6:.1f} MB)")

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
    # el_er and the er_* columns are erosion, which is NOT in `premium` —
    # see the methodology. They are exported so the exposure is usable,
    # but anyone summing them into the premium is doing it wrong.
    cols = ["name", "area", "households", "group", "premium", "capital",
            "el_total",
            "el_sub", "el_wx", "el_fl", "el_gw", "sub_score", "wx_score",
            "fl_score", "gw_score", "f_high", "f_low", "sw_high", "sw_low",
            "gw_frac", "sw_depth_m", "sw_sev",
            "wind_ms", "gust_rp50", "rain10_days", "precip_mm",
            "tvar99_vine", "tvar99_euler", "uplift_pct",
            "el_er", "er_score", "er_smp55", "er_smp105", "er_nfi55",
            "er_nfi105", "er_smp105_lo", "er_smp105_hi", "er_nfi105_lo",
            "er_nfi105_hi", "er_gi",
            # climate scenario: zero outside England, where the EA
            # publishes no future extents - cc_covered says which
            "cc_covered", "premium_cc", "el_total_cc", "cc_uplift_pct",
            "country", "geol", "sup_geol", "sup_frac"]
    def csv_bytes(rows):
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        w.writerow(cols)
        for p in sorted(rows, key=lambda d: d["name"]):
            w.writerow([p.get(c, "") for c in cols])
        return out.getvalue()

    write("assets/uk_district_risk.csv", csv_bytes(feats))

    # the same table at sector resolution. Same columns on purpose: the
    # model writes the same OUTPUT_COLUMNS at both scales, so anything
    # written against one CSV reads the other unchanged.
    with open(os.path.join(ROOT, "data", "sectors_risk.geojson"),
              encoding="utf-8") as fh:
        sector_feats = [f["properties"] for f in json.load(fh)["features"]]
    write("assets/uk_sector_risk.csv", csv_bytes(sector_feats))

    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("  .nojekyll")
    print("done")


if __name__ == "__main__":
    main()
