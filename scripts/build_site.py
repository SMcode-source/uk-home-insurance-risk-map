"""Assemble the public website into docs/ (GitHub Pages source folder).

  docs/index.html        landing page  (site/index.template.html + live numbers)
  docs/methodology.html  methodology   (site/methodology.template.html)
  docs/map.html          the MapLibre map, with site nav injected
  docs/years.html        the year analysis, with site nav injected
  docs/assets/site.css   shared styles
  docs/.nojekyll         stop Pages running Jekyll over the output

The map/years pages are the artefacts produced by build_map.py /
build_analysis.py; this script only wraps them in the site chrome so the
whole thing navigates as one website. (years is self-contained; the map
reads vector tiles and popup shards at runtime, copied in below.)
"""

import csv
import io
import math
import json
import os
import re
import shutil
import sys

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
        "The model — UK Home Insurance Risk Map",
        "Eleven layers across 2,736 postcode districts: rating group, "
        "premium, each peril score, surface-water depth, coastal erosion "
        "and the climate repricing. Click any district for its breakdown."),
    "sectors.html": (
        "Sector map — UK Home Insurance Risk Map",
        "The same model at postcode-sector resolution: 10,398 units "
        "instead of 2,736. Nineteen per cent of districts turn out to "
        "hold sectors that differ by more than 2x in premium."),
    "relative.html": (
        "Relative risk — UK Home Insurance Risk Map",
        "Every postcode district's modelled premium as a multiple of the "
        "UK median: 2.00x means homes there carry twice the median risk. "
        "The same model, re-expressed for comparison."),
    "years.html": (
        "What happened — UK Home Insurance Risk Map",
        "What UK home insurance actually paid out, year by year, from ABI "
        "releases — including their own revisions — beside what the model "
        "says a good, bad or catastrophic year looks like."),
    "temperature.html": (
        "Temperature — UK Home Insurance Risk Map",
        "UK frost days are down a fifth since the 1961–1990 normal and "
        "summer soil deficits are up. What that measured change does to "
        "the model — one peril re-mapped, one deliberately left alone."),
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
#
# The content tabs, in reading order: what actually happened, what the
# model makes of it, the same model relative to the median, what
# temperature does to it, and the methodology that backs all of them.
# sectors.html is deliberately NOT here - it is the model tab at a finer
# grain, reached by the switch link in the map panel, and another nav
# item bought nothing but width.
#
# The temperature tab joined on 2026-08-31, when the last of the
# five-gate temperature workstream reported and its one shippable
# result went live (the drought curve on subsidence frequency). It is
# NOT called "prediction": nothing on it forecasts anything, and the
# page says so in its own opening line.
PAGES = [("index.html", "Overview", "Overview"),
         ("years.html", "What happened", "History"),
         ("map.html", "The model", "Model"),
         ("relative.html", "Relative risk", "Relative"),
         ("temperature.html", "Temperature", "Temp"),
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
    # QUANTISED, and it has to be. libm's cos differs by an ULP between
    # glibc and MSVC, and that last bit propagates through the transform
    # until a coordinate sitting on a .05 boundary rounds the other way -
    # two lines of path data, a "docs/ is stale" CI failure, and a diff
    # no human can read. Rounding the only transcendental in the pipeline
    # makes every platform start from the same number; everything after
    # it is +-*/ , which IEEE 754 already pins. (Verified: perturbing cos
    # by one ULP changed exactly the 2 lines CI reported.) 1e-6 of a
    # radian's cosine is nanometres at this scale.
    kx = round(math.cos(math.radians((y0 + y1) / 2)), 6)
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

def climate_band_stats():
    """The present-vs-future flood-band deltas the methodology quotes.

    Computed from the same fraction CSVs the model reads, over the same
    England mask, so the published sentences track the data. They used to
    be hand-written, and went stale the first time the extents were
    re-fetched: "61 districts shrink" had quietly become 52, and only an
    audit of the prose against the data caught it. Growth is the change in
    the AVERAGE district's zone fraction (the same statistic flood_future
    logs), not in mapped area - districts are not equal-sized.
    """
    sys.path.insert(0, HERE)
    from scores_real import england_mask

    def table(fname, col):
        out = {}
        with open(os.path.join(ROOT, "data", fname), newline="") as fh:
            for row in csv.DictReader(fh):
                out[row["name"]] = float(row[col])
        return out

    fh_now = table("flood_fractions.csv", "f_high")
    fh_fut = table("flood_fractions_cc.csv", "f_high")
    sw_now = table("sw_fractions.csv", "sw_high")
    sw_fut = table("sw_fractions_cc.csv", "sw_high")
    names = sorted(fh_now)
    eng = england_mask(names)
    fh_cov = [n for n, m in zip(names, eng) if m and n in fh_fut]
    sw_cov = [n for n, m in zip(names, eng) if m and n in sw_fut]
    fh_shrunk = [fh_fut[n] - fh_now[n] for n in fh_cov
                 if fh_fut[n] < fh_now[n] - 1e-12]
    sw_shrunk = [sw_fut[n] - sw_now[n] for n in sw_cov
                 if sw_fut[n] < sw_now[n] - 1e-12]
    fh_growth = 100 * (sum(fh_fut[n] for n in fh_cov)
                       / sum(fh_now[n] for n in fh_cov) - 1)
    sw_growth = 100 * (sum(sw_fut[n] for n in sw_cov)
                       / sum(sw_now[n] for n in sw_cov) - 1)
    return {
        "__CC_FH_SHRINK_N__": str(len(fh_shrunk)),
        "__CC_FH_SHRINK_PCT__": f"{100 * len(fh_shrunk) / len(fh_cov):.1f}",
        "__CC_FH_SHRINK_WORST_PP__": f"{100 * min(fh_shrunk):.1f}",
        "__CC_SW_SHRINK_N__": str(len(sw_shrunk)),
        "__CC_FH_GROWTH__": f"{fh_growth:+.1f}",
        "__CC_SW_GROWTH__": f"{sw_growth:+.1f}",
    }


def load_stats():
    from build_model import (SUB_DROUGHT_SHARE as _SUB_DROUGHT_SHARE,
                             EOW_FREEZE_SHARE as _EOW_FREEZE_SHARE)
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

    # Theft, injected from the same committed data the model read.
    # Everything degrades to zeros when the geojson predates the theft
    # peril (the window between merging the model change and the bot
    # committing the rebuilt outputs) - the published pages never see
    # the fallback because the site is only built after the model.
    th_el = np.array([p.get("el_th", np.nan) for p in feats], dtype=float)
    th_rate = np.array([p.get("th_rate", np.nan) for p in feats], dtype=float)
    if np.isnan(th_el).all():
        th_el = np.zeros(len(feats))
    if np.isnan(th_rate).all():
        th_rate = np.zeros(len(feats))
    with open(os.path.join(ROOT, "data", "burglary.csv"), newline="") as fh:
        b_rows = list(csv.DictReader(fh))
    # The winsorisation cap IS the maximum surviving rate, so it needs no
    # side channel from the model; the district count at the cap is an
    # exact float equality because np.minimum wrote the cap value itself.
    # Scotland used to be recoverable as the modal rate, because the
    # override gave hundreds of districts one identical value. Council
    # geography ended that (2026-09-01), so read the country flag and
    # summarise the spread the 32 councils actually produce.
    _scot = np.array([p.get("country") == "Scotland" for p in feats])
    _s_rate = th_rate[_scot]
    _s_w = _w[_scot]
    _s_ok = _scot.any() and _s_rate.max() > 0
    th_bits = {
        "__TH_INCIDENTS__": f"{sum(int(r['burglaries']) for r in b_rows):,}",
        "__TH_MONTHS__": b_rows[0]["months"],
        "__TH_EL__": f"{np.average(th_el, weights=_w):.2f}",
        "__TH_CAP_PCT__": f"{100 * th_rate.max():.1f}",
        "__TH_CLIPPED__": str(int((th_rate == th_rate.max()).sum())
                              if th_rate.max() > 0 else 0),
        # 3dp, not the 2dp the rest of this dict uses: the smallest
        # council rate rounds to "0.04%" at 2dp, and 0.63/0.04 is 15.8,
        # which contradicts the 16x spread injected beside it.
        "__TH_SCOT_MEAN_PCT__": (f"{100 * np.average(_s_rate, weights=_s_w):.3f}"
                                 if _s_ok else "0.000"),
        "__TH_SCOT_LO_PCT__": f"{100 * _s_rate.min():.3f}" if _s_ok else "0.000",
        "__TH_SCOT_HI_PCT__": f"{100 * _s_rate.max():.3f}" if _s_ok else "0.000",
        "__TH_SCOT_SPREAD_X__": (f"{_s_rate.max() / _s_rate.min():.0f}"
                                 if _s_ok and _s_rate.min() > 0 else "0"),
        "__TH_CAT_CORR__": (f"{np.corrcoef(th_el, _el - th_el)[0, 1]:.2f}"
                            if th_el.max() > 0 else "0.00"),
    }

    # Escape of water, same discipline and the same transition fallback.
    # The freeze share and ABI context are imported from the model rather
    # than restated, so this prose cannot drift from what was priced.
    from build_model import ABI, POLICIES, EOW_FREEZE_SHARE
    eow_el = np.array([p.get("el_eow", np.nan) for p in feats], dtype=float)
    frost = np.array([p.get("frost_days", np.nan) for p in feats],
                     dtype=float)
    if np.isnan(eow_el).all():
        eow_el = np.zeros(len(feats))
    if np.isnan(frost).all():
        frost = np.zeros(len(feats))
    _has_eow = eow_el.max() > 0
    i_lo, i_hi = int(np.argmin(eow_el)), int(np.argmax(eow_el))
    eow_bits = {
        "__EOW_EL__": f"{np.average(eow_el, weights=_w):.2f}",
        "__EOW_LO__": f"{eow_el.min():.0f}",
        "__EOW_HI__": f"{eow_el.max():.0f}",
        "__EOW_LO_NAME__": feats[i_lo]["name"] if _has_eow else "n/a",
        "__EOW_HI_NAME__": feats[i_hi]["name"] if _has_eow else "n/a",
        "__EOW_FROST_LO__": f"{frost[i_lo]:.0f}",
        "__EOW_FROST_HI__": f"{frost[i_hi]:.0f}",
        "__EOW_FREEZE_PCT__": f"{100 * EOW_FREEZE_SHARE:.0f}",
        "__EOW_CAT_CORR__": (f"{np.corrcoef(eow_el, _el - eow_el)[0, 1]:.2f}"
                             if _has_eow else "0.00"),
    }
    # Fire, same discipline and the same transition fallback. The rate
    # cap is recovered from the data the way theft's is: np.minimum
    # wrote the cap value itself, so exact float equality counts the
    # clipped districts.
    fire_el = np.array([p.get("el_fire", np.nan) for p in feats],
                       dtype=float)
    fire_rate = np.array([p.get("fire_rate", np.nan) for p in feats],
                         dtype=float)
    if np.isnan(fire_el).all():
        fire_el = np.zeros(len(feats))
    if np.isnan(fire_rate).all():
        fire_rate = np.zeros(len(feats))
    _has_fire = fire_el.max() > 0
    fi_lo, fi_hi = int(np.argmin(fire_el)), int(np.argmax(fire_el))
    with open(os.path.join(ROOT, "data", "fires.csv"), newline="") as fh:
        f_rows = list(csv.DictReader(fh))
    fire_bits = {
        "__FIRE_EL__": f"{np.average(fire_el, weights=_w):.2f}",
        "__FIRE_LO__": f"{fire_el.min():.0f}",
        "__FIRE_HI__": f"{fire_el.max():.0f}",
        "__FIRE_LO_NAME__": feats[fi_lo]["name"] if _has_fire else "n/a",
        "__FIRE_HI_NAME__": feats[fi_hi]["name"] if _has_fire else "n/a",
        "__FIRE_YR__": f"{sum(float(r['fires_yr']) for r in f_rows):,.0f}",
        "__FIRE_CAP_PCT__": f"{100 * fire_rate.max():.2f}",
        "__FIRE_CLIPPED__": str(int((fire_rate == fire_rate.max()).sum())
                                if fire_rate.max() > 0 else 0),
        "__FIRE_CAT_CORR__": (f"{np.corrcoef(fire_el, _el - fire_el)[0, 1]:.2f}"
                              if _has_fire else "0.00"),
    }
    # Accidental damage, same discipline and the same transition
    # fallback. The child share is recomputed from children.csv (the
    # same counts the model read), so the published extremes cannot
    # drift from what was priced; the slice size is imported.
    from build_model import AD_CHILD_SHARE
    ad_el = np.array([p.get("el_ad", np.nan) for p in feats], dtype=float)
    if np.isnan(ad_el).all():
        ad_el = np.zeros(len(feats))
    _has_ad = ad_el.max() > 0
    ai_lo, ai_hi = int(np.argmin(ad_el)), int(np.argmax(ad_el))
    with open(os.path.join(ROOT, "data", "children.csv"), newline="") as fh:
        c_rows = {r["name"]: (float(r["hh_total"]), float(r["hh_depchild"]))
                  for r in csv.DictReader(fh)}
    def _cshare(i):
        t, d = c_rows.get(feats[i]["name"], (0.0, 0.0))
        return 100 * d / t if t else 0.0
    ad_bits = {
        "__AD_EL__": f"{np.average(ad_el, weights=_w):.2f}",
        "__AD_LO__": f"{ad_el.min():.0f}",
        "__AD_HI__": f"{ad_el.max():.0f}",
        "__AD_LO_NAME__": feats[ai_lo]["name"] if _has_ad else "n/a",
        "__AD_HI_NAME__": feats[ai_hi]["name"] if _has_ad else "n/a",
        "__AD_CHILD_PCT__": f"{100 * AD_CHILD_SHARE:.0f}",
        "__AD_SHARE_LO__": f"{_cshare(ai_lo):.0f}",
        "__AD_SHARE_HI__": f"{_cshare(ai_hi):.0f}",
        "__AD_CAT_CORR__": (f"{np.corrcoef(ad_el, _el - ad_el)[0, 1]:.2f}"
                            if _has_ad else "0.00"),
    }
    # The insured expected loss as a share of ALL home claims paid - the
    # landing-page finding that quietly went stale when theft arrived
    # ("none of which this models" survived a peril that was modelled).
    _all_claims_pp = ABI["total_home_paid"] / POLICIES
    el_claims_share = f"{100 * np.average(_el, weights=_w) / _all_claims_pp:.0f}"

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

    # Sector premiums aggregated back to districts, and how closely they
    # reproduce the district model. Injected for the same reason as the
    # climate deltas below: the "0.964 / 0.6%" that used to be hand-written
    # here was measured BEFORE the terminated-postcode fix and quietly
    # went stale when both models were rebuilt.
    dbyname = {p["name"]: p for p in feats}
    agg_names = [d for d in grouped if d in dbyname]

    def _agg_premium(g):
        wts = [max(q.get("households", 0), 1e-9) for q in g]
        return sum(q["premium"] * v for q, v in zip(g, wts)) / sum(wts)

    a = np.array([dbyname[d]["premium"] for d in agg_names])
    b = np.array([_agg_premium(grouped[d]) for d in agg_names])
    wag = np.array([dbyname[d].get("households", 1) for d in agg_names],
                   dtype=float)
    lvl = abs(100 * (np.average(b, weights=wag)
                     / np.average(a, weights=wag) - 1))
    sector_bits.update({
        "__AGG_CORR__": f"{np.corrcoef(a, b)[0, 1]:.3f}",
        "__AGG_LEVEL_PCT__": f"{lvl:.1f}",
    })

    # how many districts carry a household count (the CSV covers every
    # district with live postcodes, more than the modelled boundary set)
    with open(os.path.join(ROOT, "data", "households.csv"), newline="") as fh:
        hh_districts = sum(1 for _ in fh) - 1

    val_path = os.path.join(ROOT, "data", "sector_validation.json")
    with open(val_path) as fh:
        val = json.load(fh)
    sector_bits.update({
        "__SECTOR_IOU__": f"{val['sector_iou_median']:.3f}",
        "__DISTRICT_IOU__": f"{val['district_iou_median']:.3f}",
        "__SECTOR_IOU_50__": str(val["pct_above_50"]),
        "__SECTOR_IOU_70__": str(val["pct_above_70"]),
    })

    # ---- the ABI CALIBRATION table. Hand-written from the first commit,
    # and by 2026-08-28 it had drifted twice at once. Theft still read
    # GBP450m / ~118,000 / 0.76% three days after the 2026-08-25 level
    # correction moved it to GBP341.6m / 89,895 / 0.58%, and subsidence
    # read GBP17,820 / ~17,200 the moment Gate 1's severity fix landed.
    # Both were found by grepping the LIVE page for a number that should
    # no longer exist, which is not a control anyone should rely on.
    #
    # A published table that restates the calibration will always drift
    # from the calibration; the only fix is to stop restating it. Counts
    # and frequencies are rendered to three significant figures - the old
    # cells mixed 2, 3 and 4 sig figs by hand and rounded 137,576 down to
    # "~137,000".
    def _sf3(x):
        from math import floor, log10
        if x <= 0:
            return "0"
        # d goes NEGATIVE for counts, which is the whole point: round()
        # with a negative ndigits is what turns 99,592 into 99,600.
        # Clamping it at zero (the first attempt) silently rendered every
        # count in full and produced a table claiming five significant
        # figures on a calibration good to three.
        d = 2 - int(floor(log10(abs(x))))
        return f"{round(x, d):,.{max(0, d)}f}"

    def _cal(paid_key, sev_key):
        n = ABI[paid_key] / ABI[sev_key]
        return (f"{ABI[paid_key] / 1e6:,.0f}", f"{ABI[sev_key]:,.0f}",
                _sf3(n), _sf3(100 * n / POLICIES))

    _wx = _cal("storm_paid", "sev_weather")
    _fl = _cal("flood_paid", "sev_flood")
    _sb = _cal("subsidence_paid", "sev_subsidence")
    _th = _cal("theft_paid", "sev_theft")
    _ew = _cal("eow_paid", "sev_eow")
    _fr = _cal("fire_paid", "sev_fire")
    _ad = _cal("ad_paid", "sev_ad")
    # Every key spelled out as a LITERAL, not built with an f-string.
    # test_site_placeholders_all_resolve greps this file for quoted
    # double-underscore tokens and fails any placeholder in a template it
    # cannot find here - and an f-string key is invisible to it. (Do not
    # write an example token in quotes anywhere in this file either: the
    # same grep reads it as a defined key and the test then fails the
    # other way, for a key no template uses. It has already happened.) The first
    # version of this block used a loop and shipped 28 placeholders the
    # guard could not see. Verbose beats unverifiable: the guard exists
    # because raw __TOKEN__ text has reached the live page before.
    calib_bits = {
        "__CAL_WX_PAID__": _wx[0], "__CAL_WX_SEV__": _wx[1],
        "__CAL_WX_N__": _wx[2], "__CAL_WX_FREQ__": _wx[3],
        "__CAL_FL_PAID__": _fl[0], "__CAL_FL_SEV__": _fl[1],
        "__CAL_FL_N__": _fl[2], "__CAL_FL_FREQ__": _fl[3],
        "__CAL_SUB_PAID__": _sb[0], "__CAL_SUB_SEV__": _sb[1],
        "__CAL_SUB_N__": _sb[2], "__CAL_SUB_FREQ__": _sb[3],
        "__CAL_TH_PAID__": _th[0], "__CAL_TH_SEV__": _th[1],
        "__CAL_TH_N__": _th[2], "__CAL_TH_FREQ__": _th[3],
        "__CAL_EOW_PAID__": _ew[0], "__CAL_EOW_SEV__": _ew[1],
        "__CAL_EOW_N__": _ew[2], "__CAL_EOW_FREQ__": _ew[3],
        "__CAL_FIRE_PAID__": _fr[0], "__CAL_FIRE_SEV__": _fr[1],
        "__CAL_FIRE_N__": _fr[2], "__CAL_FIRE_FREQ__": _fr[3],
        "__CAL_AD_PAID__": _ad[0], "__CAL_AD_SEV__": _ad[1],
        "__CAL_AD_N__": _ad[2], "__CAL_AD_FREQ__": _ad[3],
        # Groundwater has no published total and is pegged to a share of
        # flood, so only its severity is a calibration figure at all.
        "__CAL_GW_SEV__": f"{ABI['sev_groundwater']:,.0f}",
    }

    # ---- methodology peril table. EVERY numeric cell in it is injected.
    # The severity column was hand-written in the first commit and six of
    # its nine cells had drifted by up to +162% once the ABI calibration
    # landed (HANDOFF, defect 3), so the medians are derived from ABI and
    # SEV_SIGMA here and cannot go stale again.
    from build_model import SEV_SIGMA, _median_for_mean
    _med = lambda anchor, sig: f"{_median_for_mean(ABI[anchor], SEV_SIGMA[sig]):,.0f}"
    # Claim-cost shares over the INSURED book. Erosion is excluded for the
    # same reason el_total excludes it - gradual coastal erosion is not
    # covered, so it is not part of a claim-cost split.
    _pcols = [("SUB", "el_sub"), ("WX", "el_wx"), ("FL", "el_fl"),
              ("GW", "el_gw"), ("TH", "el_th"), ("EOW", "el_eow"),
              ("FIRE", "el_fire"), ("AD", "el_ad")]
    _pel = {k: float(np.average([p.get(c, 0.0) for p in feats], weights=_w))
            for k, c in _pcols}
    _psum = sum(_pel.values()) or 1.0
    # Buildings/contents split. PUBLISHED ANCHORS ONLY (DATA_SOURCES #31):
    # subsidence is a structural peril by definition, theft and fire have
    # ABI/Aviva cover-level splits, and flood takes the Multi-Coloured
    # Manual depth-damage convention (the table footnote names the two
    # published conventions that disagree with it, and why MCM is used).
    # Groundwater follows flood. Weather, escape of water and accidental
    # damage have NO published split - they render as "unsplit" in the
    # template rather than being given an invented number, which is why
    # only 57% of claim cost carries a split at all.
    # Derived from build_model.SPLIT_BUILDINGS, never restated. These
    # were duplicated literals until 2026-08-27, and they had already
    # drifted: theft sat at 25 here against 0.242 there, both citing the
    # same ONS nature-of-crime table. Shipping the cover section would
    # have put 25% in this peril table and 24% in that one, on the same
    # page, from the same source. SPLIT_BUILDINGS is the anchored value,
    # so it wins; the published theft figure moves 25% -> 24%.
    #
    # SPLIT_ANCHORED decides membership too, so a peril gaining or
    # losing an anchor cannot leave this table disagreeing with the
    # cover table about which perils are splittable.
    from build_model import SPLIT_BUILDINGS, SPLIT_ANCHORED
    COVER_BLD = {k.upper(): round(100 * SPLIT_BUILDINGS[k])
                 for k in SPLIT_ANCHORED}
    # Spelled out as LITERAL keys, not built with f-strings in a
    # comprehension. test_site_placeholders_all_resolve greps this file for
    # double-quoted placeholder literals to prove every token in the templates has
    # somewhere to come from; keys assembled dynamically are invisible to
    # it, so a comprehension here silently disables the guard that stops
    # raw __TOKENS__ shipping to the live page. Verbosity is the price of
    # keeping that check able to see what it is checking.
    _pct = lambda k: f"{100 * _pel[k] / _psum:.1f}"
    _bld = lambda k: str(COVER_BLD[k])
    _cnt = lambda k: str(100 - COVER_BLD[k])
    peril_bits = {
        "__PCT_SUB__": _pct("SUB"), "__PCT_WX__": _pct("WX"),
        "__PCT_FL__": _pct("FL"), "__PCT_GW__": _pct("GW"),
        "__PCT_TH__": _pct("TH"), "__PCT_EOW__": _pct("EOW"),
        "__PCT_FIRE__": _pct("FIRE"), "__PCT_AD__": _pct("AD"),
        "__BLD_SUB__": _bld("SUB"), "__CNT_SUB__": _cnt("SUB"),
        "__BLD_FL__": _bld("FL"), "__CNT_FL__": _cnt("FL"),
        "__BLD_GW__": _bld("GW"), "__CNT_GW__": _cnt("GW"),
        "__BLD_TH__": _bld("TH"), "__CNT_TH__": _cnt("TH"),
        "__BLD_FIRE__": _bld("FIRE"), "__CNT_FIRE__": _cnt("FIRE"),
    }
    peril_bits.update({
        "__SEV_SUB__": _med("sev_subsidence", "sub"),
        "__SEV_WX__": _med("sev_weather", "wx"),
        "__SEV_FL_RS__": _med("sev_flood_fluvial", "fl"),
        "__SEV_FL_SW__": _med("sev_surface_water", "fl"),
        "__SEV_GW__": _med("sev_groundwater", "gw"),
        "__SEV_TH__": _med("sev_theft", "th"),
        "__SEV_EOW__": _med("sev_eow", "eow"),
        "__SEV_FIRE__": _med("sev_fire", "fire"),
        "__SEV_AD__": _med("sev_ad", "ad"),
        "__SEV_ER__": _med("sev_erosion", "er"),
    })

    # ---- seed sensitivity. Committed measurement, not rebuilt here: a
    # six-seed sweep is an hour of simulation, so `data/seed_sensitivity.json`
    # ships like `data/sector_validation.json` and is regenerated by hand with
    # `scripts/seed_sweep.py --write-json`. It exists because the standalone
    # TVaR99's Monte Carlo error is COMONOTONE across districts (every
    # district sees the same draws), so it does not average away and a
    # one-seed point estimate would overstate the precision. The allocated
    # share and the premium do average down and stay points.
    with open(os.path.join(ROOT, "data", "seed_sensitivity.json")) as fh:
        _seed = json.load(fh)
    _sa, _pt = _seed["standalone_tvar99"], _seed["port_tvar99"]
    _dv = _seed["diversification_pct"]
    # round OUTWARDS to the nearest 100 so the quoted range never claims
    # to be tighter than what was measured
    seed_bits = {
        "__STANDALONE_LO__": f"{100 * math.floor(_sa['min'] / 100):,.0f}",
        "__STANDALONE_HI__": f"{100 * math.ceil(_sa['max'] / 100):,.0f}",
        "__STANDALONE_SPREAD__": f"{_sa['spread_pct']:.0f}",
        "__PORT_SPREAD__": f"{_pt['spread_pct']:.1f}",
        "__PREMIUM_SPREAD__": f"{_seed['premium']['spread_pct']:.2f}",
        "__SEED_N__": str(len(_seed["seeds"])),
        "__TAIL_YEARS__": f"{max(int(_seed['n_sim'] // 100), 1):,}",
        "__DIV_LO__": f"{_dv['min']:.1f}",
        "__DIV_HI__": f"{_dv['max']:.1f}",
    }

    return {
        **peril_bits,
        **seed_bits,
        **cc_bits,
        **th_bits,
        **eow_bits,
        **fire_bits,
        **ad_bits,
        **calib_bits,
        "__EL_CLAIMS_SHARE__": el_claims_share,
        **sector_bits,
        **climate_band_stats(),
        "__HH_DISTRICTS__": f"{hh_districts:,}",
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
        # The headline premium, household-weighted because that is what
        # "the premium" means everywhere else here and in HANDOFF's
        # publish notes. Two decimals: a model change worth under a penny
        # is a real result this project keeps quoting, so rounding to the
        # pound would hide exactly the differences the gates measure.
        "__PREM_MEAN__": f"{np.average([p['premium'] for p in feats], weights=[p.get('households', 0) for p in feats]):,.2f}",
        # Peril-blend shares, site-wide rather than page-local: the
        # methodology page and the temperature page each state the
        # subsidence split in their own words, and a constant restated on
        # two pages drifts on one of them first.
        "__SUB_DROUGHT_PCT__": f"{100 * _SUB_DROUGHT_SHARE:.1f}",
        "__SUB_FLAT_PCT__": f"{100 * (1 - _SUB_DROUGHT_SHARE):.1f}",
        "__EOW_FREEZE_PCT__": f"{100 * _EOW_FREEZE_SHARE:.0f}",
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
        # Exposure-weighted, like every other "nationally" figure here.
        # This was a plain np.mean until 2026-08-25, which put two
        # different bases in ONE published sentence: "come to GBP X per
        # policy per year - Y% of what all home claims cost", where Y
        # (__EL_CLAIMS_SHARE__) was already exposure-weighted. An
        # unweighted mean over 2,736 districts is not a per-policy
        # figure at all - it over-weights small rural districts - and it
        # read GBP 163 against a 75% that implies GBP 164.
        "__MEAN_EL__": f"{np.average(_el, weights=_w):,.0f}",
        "__MEAN_CAPITAL__": f"{np.mean([p.get('capital', 0) for p in feats]):,.0f}",
        # NOT __MEAN_STANDALONE__ any more: the standalone tail is quoted
        # as a measured range (see seed_bits below). Its Monte Carlo error
        # is comonotone across districts, so a point estimate from one seed
        # claims a precision the simulation does not have - at 20,000 years
        # the national mean ran 11,956 to 17,118 over six seeds.
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
        **cover_split(feats),
    }


def cover_split(feats):
    """Per-risk-type claim cost, split into buildings and contents cover
    ONLY where a published anchor exists.

    Deliberately built from the per-peril ELs and the anchored fractions
    alone - NOT from the el_buildings/capital_buildings columns on
    exp/buildings-contents. The distinction is the whole point of Phase
    3: this table is a DISCLOSURE of numbers the model already publishes
    times five constants with sources behind them, so it needs no model
    change, no evidence run and no unanchored parameter. The mechanism
    that splits capital as well is a separate thing and is not shipped,
    because the four unanchored perils would put an opinion in the
    portfolio total. See DATA_SOURCES #31.
    """
    from build_model import SPLIT_BUILDINGS, SPLIT_ANCHORED, PERIL_LABELS
    w = np.array([p.get("households", 1) for p in feats], dtype=float)
    tot = np.average([p["el_total"] for p in feats], weights=w)

    rows, anchored_el, anchored_bld = [], 0.0, 0.0
    per = sorted(PERIL_LABELS, key=lambda k: -np.average(
        [p["el_" + k] for p in feats], weights=w))
    for k in per:
        el = float(np.average([p["el_" + k] for p in feats], weights=w))
        share = 100 * el / tot
        if k in SPLIT_ANCHORED:
            b = SPLIT_BUILDINGS[k]
            anchored_el += el
            anchored_bld += el * b
            cells = (f'<td class="num">{100 * b:.0f}%</td>'
                     f'<td class="num">£{el * b:,.2f}</td>'
                     f'<td class="num">£{el - el * b:,.2f}</td>')
        else:
            cells = ('<td class="num">—</td>'
                     '<td class="num" colspan="2"><em>no anchor</em></td>')
        rows.append("<tr>"
                    f'<td><strong>{PERIL_LABELS[k]}</strong></td>'
                    f'<td class="num">£{el:,.2f}</td>'
                    f'<td class="num">{share:.1f}%</td>'
                    f"{cells}</tr>")
    rows.append('<tr class="sub"><td><strong>anchored subtotal</strong></td>'
                f'<td class="num"><strong>£{anchored_el:,.2f}</strong></td>'
                f'<td class="num"><strong>{100 * anchored_el / tot:.1f}%</strong></td>'
                f'<td class="num"><strong>{100 * anchored_bld / anchored_el:.0f}%</strong></td>'
                f'<td class="num"><strong>£{anchored_bld:,.2f}</strong></td>'
                f'<td class="num"><strong>£{anchored_el - anchored_bld:,.2f}</strong></td></tr>')
    rows.append('<tr class="sub"><td><strong>not split</strong></td>'
                f'<td class="num"><strong>£{tot - anchored_el:,.2f}</strong></td>'
                f'<td class="num"><strong>{100 * (tot - anchored_el) / tot:.1f}%</strong></td>'
                '<td class="num" colspan="3"><em>named and left blank</em></td></tr>')

    unsplit = tot - anchored_el
    return {
        "__SPLIT_ROWS__": "\n        ".join(rows),
        "__SPLIT_ANCHORED_PCT__": f"{100 * anchored_el / tot:.1f}",
        "__SPLIT_UNANCHORED_PCT__": f"{100 * unsplit / tot:.1f}",
        "__SPLIT_BLD_PCT__": f"{100 * anchored_bld / anchored_el:.0f}",
        # The portfolio bound: the unanchored block is all contents at one
        # end and all buildings at the other. A 40-point band is not a
        # figure, which is exactly why the total row is absent above.
        "__SPLIT_FLOOR__": f"{100 * anchored_bld / tot:.1f}",
        "__SPLIT_CEIL__": f"{100 * (anchored_bld + unsplit) / tot:.1f}",
        "__SPLIT_EOW_PCT__": f"{100 * np.average([p['el_eow'] for p in feats], weights=w) / tot:.1f}",
    }


# ---- the temperature page's two series -------------------------------
#
# Drawn server-side as inline SVG, like the methodology diagrams and for
# the same reason the resolution figure is: a chart built at build time
# from the committed series cannot go stale, and a screenshot can. The
# analysis page's client-side charting harness is deliberately NOT
# reused here - it exists to redraw on resize, which these do not need,
# and importing it would mean shipping its whole geometry system to a
# page with two static plots.
#
# Two variants per chart, wide and narrow, swapped by media query. That
# is the methodology page's answer to the measured 3.4px failure: a
# fixed viewBox scales its TYPE down with everything else, so a phone
# gets a correct layout nobody can read. Sizes below are chosen so each
# variant renders near 1:1 at its own breakpoint.
TEMPERATURE = os.path.join(ROOT, "data", "temperature_series.json")


def _series_svg(t, key, *, wide, colour, unit, decimals=0, marks=()):
    """One annual series with its least-squares trend, as inline SVG.

    Arithmetic is +-*/ and round() only. The resolution figure's comment
    explains why that matters: one unrounded transcendental differing by
    an ULP between glibc and MSVC is enough to make docs/ "stale" in CI
    with a diff no human can read.
    """
    years, vals = t["years"], t[key]
    st = t[key + "_stats"]
    W, H = (720, 250) if wide else (330, 260)
    L, R, T, B = (46, 10, 16, 26) if wide else (36, 8, 14, 24)
    pw, ph = W - L - R, H - T - B
    hi = max(vals) * 1.08
    x = lambda i: L + pw * i / (len(years) - 1)            # noqa: E731
    y = lambda v: T + ph - ph * v / hi                     # noqa: E731

    # The class is what the breakpoint keys on; without it the wide
    # drawing stays visible on a phone and both charts render at once.
    out = [f'<svg class="{"chart-wide" if wide else "chart-narrow-svg"}" '
           f'viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="{unit} by year, {years[0]} to {years[-1]}">']
    # horizontal grid + value ticks
    for frac in (0.0, 0.5, 1.0):
        v = hi * frac
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" '
                   f'y2="{y(v):.1f}" stroke="var(--grid)"/>')
        out.append(f'<text class="tick-label" x="{L - 5}" y="{y(v) + 4:.1f}" '
                   f'text-anchor="end">{v:,.{decimals}f}</text>')
    # decade ticks; every 20 years on the narrow variant so labels cannot
    # collide instead of shrinking
    step = 10 if wide else 20
    for i, yr in enumerate(years):
        if yr % step == 0:
            out.append(f'<text class="tick-label" x="{x(i):.1f}" '
                       f'y="{H - 8}" text-anchor="middle">{yr}</text>')
    # the marked years (canonical subsidence surges), behind the series
    for yr in marks:
        if yr in years:
            i = years.index(yr)
            out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{T}" '
                       f'y2="{T + ph}" stroke="var(--sub)" stroke-width="1.5" '
                       f'stroke-opacity="0.30"/>')
    # the series
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    out.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" '
               f'stroke-width="1.8" stroke-linejoin="round"/>')
    for yr in marks:
        if yr in years:
            i = years.index(yr)
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(vals[i]):.1f}" r="3.2" '
                       f'fill="{colour}" stroke="var(--surface-1)" '
                       f'stroke-width="1.2"/>')
    # least-squares trend. Every such line passes through the centroid,
    # so the stored slope alone fixes it - no second fitted constant to
    # round, and nothing here to drift against the JSON.
    mx = (len(years) - 1) / 2.0
    my = sum(vals) / len(vals)
    slope = st["slope_per_year"]
    y0, y1 = my - slope * mx, my + slope * mx
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(y0):.1f}" '
               f'y2="{y(y1):.1f}" stroke="var(--ink-1)" stroke-width="1.6" '
               f'stroke-dasharray="6 4" stroke-opacity="0.75"/>')
    out.append("</svg>")
    return "".join(out)


FREEZE_PRICING = os.path.join(ROOT, "data", "freeze_share_pricing.json")
SMD_PRICING = os.path.join(ROOT, "data", "smd_curve_pricing.json")


def temperature_bits():
    """Every number and both charts on the temperature page.

    Injected, never hand-written into the template: the stale-severity
    -column defect (HANDOFF, defect 3) started as six numbers typed into
    a page once and never revisited. The freeze dose-response is read
    from the pricing run's own artifact for the same reason
    seed_sensitivity.json is - a measured range quoted from memory is a
    measured range that drifts.
    """
    with open(TEMPERATURE) as fh:
        t = json.load(fh)
    with open(FREEZE_PRICING) as fh:
        fz = {r["key"]: r for r in json.load(fh)}
    with open(os.path.join(ROOT, "data", "year_analysis.json")) as fh:
        _yb = {b["label"]: b for b in json.load(fh)["buckets"]}
    fs, ds = t["frost_days_stats"], t["cwd_yr_mm_stats"]
    marks = t["canonical_subsidence_years"]
    hits = t["cwd_canonical_hits"]

    base = fz["baseline"]
    # The widest premium excursion anywhere in the dose-response, in
    # pence, and the largest single-district move that produced it.
    _dp = [abs(r["premium"] - base["premium"]) for r in fz.values()]
    _shares = [r for k, r in fz.items() if k.startswith("share_")]
    _worst = max(_shares, key=lambda r: r["churn"])
    _big = max((abs(v) for r in _shares
                for _n, v in r["movers_up"] + r["movers_down"]))
    _era = fz["era_2006_2025"]["premium"] - fz["daily_1991_2020"]["premium"]

    # Gate 4's answer, recomputed from the committed year analysis rather
    # than from the run that first measured it. The buckets already carry
    # UNROUNDED claims_*_per_100k and cost_*_per_claim precisely so this
    # is derivable without a simulation - see year_claim_view.py's
    # docstring for why the rounded inc_*_pct columns are not usable.
    #
    # The shift-share is the standard one: hold every peril's typical
    # cost per claim fixed and move only the claim MIX to get the mix
    # term; the rest of the total ratio is severity rising within perils.
    # The two multiply back to the total exactly, which is what makes
    # quoting both honest rather than two separate framings of one number.
    # The shares this page states are injected site-wide from
    # load_stats(); SUB_DROUGHT_SHARE is imported here only to look the
    # SHIPPED pricing row up by value.
    from build_model import SUB_DROUGHT_SHARE

    # The churn the published curve actually caused, looked up by the
    # SHIPPED index and share rather than by the variant's key. If
    # SUB_DROUGHT_SHARE is ever re-tuned this raises instead of quietly
    # describing a variant the model no longer runs - which is the whole
    # failure this page has now had four of.
    with open(SMD_PRICING) as fh:
        _smd = json.load(fh)
    _shipped = [r for r in _smd
                if r["index"] == "cwd_yr"
                and abs(r["share"] - SUB_DROUGHT_SHARE) < 1e-9]
    if len(_shipped) != 1:
        raise SystemExit(
            f"smd_curve_pricing.json has {len(_shipped)} variants at "
            f"cwd_yr/{SUB_DROUGHT_SHARE} - the published curve must "
            f"match exactly one priced variant")
    _shipped = _shipped[0]

    _ty, _cat = _yb["typical"], _yb["catastrophic"]
    _P = ("wx", "fl", "sub", "gw")

    def _w(b, p):
        return b[f"claims_{p}_per_100k"] / b["claims_total_per_100k"]

    _ratio = _cat["cost_total_per_claim"] / _ty["cost_total_per_claim"]
    _mix = (sum(_w(_cat, p) * _ty[f"cost_{p}_per_claim"] for p in _P)
            / sum(_w(_ty, p) * _ty[f"cost_{p}_per_claim"] for p in _P))
    return {
        "__FREEZE_MAX_PENCE__": f"{100 * max(_dp):.2f}",
        "__FREEZE_MAX_CHURN__": f"{_worst['churn']:,}",
        "__FREEZE_LOW__": f"{min(r['share'] for r in _shares):.2f}",
        "__FREEZE_HIGH__": f"{max(r['share'] for r in _shares):.2f}",
        "__FREEZE_BIG_MOVE__": f"{_big:.0f}",
        "__FREEZE_ERA_PENCE__": f"{abs(100 * _era):.2f}",
        "__TEMP_DROUGHT_CHART__": _series_svg(
            t, "cwd_yr_mm", wide=True, colour="var(--sub)",
            unit="Peak annual soil water deficit in mm", marks=marks),
        "__TEMP_DROUGHT_CHART_N__": _series_svg(
            t, "cwd_yr_mm", wide=False, colour="var(--sub)",
            unit="Peak annual soil water deficit in mm", marks=marks),
        "__TEMP_FROST_CHART__": _series_svg(
            t, "frost_days", wide=True, colour="var(--gw)",
            unit="Air-frost days per year"),
        "__TEMP_FROST_CHART_N__": _series_svg(
            t, "frost_days", wide=False, colour="var(--gw)",
            unit="Air-frost days per year"),
        "__TEMP_Y0__": str(t["years"][0]),
        "__TEMP_Y1__": str(t["years"][-1]),
        "__TEMP_NDIST__": f"{t['n_polygons']:,}",
        "__TEMP_CLIM0__": str(t["clim"][0]),
        "__TEMP_CLIM1__": str(t["clim"][1]),
        "__TEMP_PREV0__": str(t["previous"][0]),
        "__TEMP_PREV1__": str(t["previous"][1]),
        "__TEMP_FROST_CLIM__": f"{fs['clim_mean']:.1f}",
        "__TEMP_FROST_PREV__": f"{fs['previous_mean']:.1f}",
        "__TEMP_FROST_DROP__": f"{abs(fs['previous_to_clim_pct']):.1f}",
        "__TEMP_FROST_DECADE__": f"{abs(fs['pct_per_decade']):.1f}",
        "__TEMP_FROST_P__": f"{fs['p_value']:.4f}".rstrip("0"),
        "__TEMP_DROUGHT_CLIM__": f"{ds['clim_mean']:,.0f}",
        "__TEMP_DROUGHT_DECADE__": f"{ds['pct_per_decade']:+.1f}",
        "__TEMP_DROUGHT_P__": f"{ds['p_value']:.3f}",
        "__TEMP_HITS__": str(len(hits)),
        "__TEMP_CANON_N__": str(len(marks)),
        "__TEMP_HIT_YEARS__": ", ".join(str(y) for y in hits),
        "__TEMP_MISS_YEARS__": ", ".join(str(y) for y in
                                         t["cwd_canonical_misses"]),
        "__BY_COUNT__": f"{_cat['claims_total_per_100k'] / _ty['claims_total_per_100k']:.2f}",
        "__BY_VALUE__": f"{_ratio:.2f}",
        "__BY_MIX__": f"{_mix:.2f}",
        "__BY_WITHIN__": f"{_ratio / _mix:.2f}",
        "__BY_WX_FROM__": f"{100 * _w(_ty, 'wx'):.1f}",
        "__BY_WX_TO__": f"{100 * _w(_cat, 'wx'):.1f}",
        "__BY_FL_FROM__": f"{100 * _w(_ty, 'fl'):.1f}",
        "__BY_FL_TO__": f"{100 * _w(_cat, 'fl'):.1f}",
        "__BY_WX_COUNT__": f"{_cat['claims_wx_per_100k'] / _ty['claims_wx_per_100k']:.2f}",
        "__BY_WX_VALUE__": f"{_cat['cost_wx_per_claim'] / _ty['cost_wx_per_claim']:.2f}",
        "__BY_FL_COUNT__": f"{_cat['claims_fl_per_100k'] / _ty['claims_fl_per_100k']:.2f}",
        "__BY_FL_VALUE__": f"{_cat['cost_fl_per_claim'] / _ty['cost_fl_per_claim']:.2f}",
        "__SMD_CHURN__": f"{_shipped['churn']:,}",
        "__SMD_CHURN2__": f"{_shipped['churn2']:,}",
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

/* NOTE - do not try to fix popup/panel overlap with z-index. The map
   container carries a transform, which makes it a stacking context, so
   the popup inside it is trapped below whatever that container resolves
   to; this was measured under Leaflet and MapLibre positions its popups
   the same way. The popup is kept clear of the panels by panning
   instead; see keepPopupClear() in the map template. */

/* The popup opens compact (headline, scores, disclosures), but a reader
   who unfolds everything is back to ~1,000px of content - taller than an
   800px laptop viewport - and no map library caps a popup on its own.
   Cap it and let it scroll everywhere; the phone rule below tightens
   this to the gap between the floating panels. */
.maplibregl-popup-content { max-height: 60vh; overflow-y: auto; }

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

  /* The zoom buttons sit at the map's top-left, which on a phone is
     exactly where #controls sits. They were not merely hidden - they
     were unreachable, and a tap on "zoom out" landed on the metric button
     underneath, silently switching the map's layer instead of zooming.

     #controls starts 8px into the map and is capped at 34vh, so the band
     below that is free until #legend begins. Put the zoom there, and lift
     it above the panels (which sit at z-index 1000) so a panel growing
     can never bury it again. */
  .maplibregl-ctrl-top-left { top: calc(34vh + 18px); z-index: 1100; }

  /* The popup must FIT the free band between #controls (top: 60px,
     max-height 34vh) and #legend (bottom: 62px, max-height 24vh), or
     keepPopupClear() has no clear position to move it to and leaves it
     under a panel - which is how the close button ended up untappable
     under the metric buttons (caught by the layout tests; the old cap of
     42vh - 165px plus ~35px of popup chrome and tip was taller than the
     band by construction).
     Band = 100vh - (60 + 34vh) - (62 + 24vh) = 42vh - 122px. Less 2x8px
     keep-clear padding and ~35px chrome: content cap = 42vh - 173px.
     -180 leaves slack for font rounding. Width in vw so rotation is
     handled without JS. */
  .maplibregl-popup-content { max-height: calc(42vh - 180px); overflow-y: auto; max-width: calc(100vw - 64px); }
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
    render_template("temperature.template.html", "temperature.html",
                    dict(stats, **temperature_bits()))
    wrap_generated(os.path.join(ROOT, "map", "uk_home_insurance_risk_map.html"),
                   "map.html", MAP_CSS)
    wrap_generated(os.path.join(ROOT, "map", "uk_sector_risk_map.html"),
                   "sectors.html", MAP_CSS)
    wrap_generated(os.path.join(ROOT, "map", "uk_relative_risk_map.html"),
                   "relative.html", MAP_CSS)
    wrap_generated(os.path.join(ROOT, "analysis", "uk_risk_year_analysis.html"),
                   "years.html", YEARS_CSS)

    os.makedirs(os.path.join(DOCS, "assets"), exist_ok=True)
    shutil.copy(os.path.join(SITE, "assets", "site.css"),
                os.path.join(DOCS, "assets", "site.css"))
    print("  assets/site.css")

    # MapLibre and the PMTiles protocol, linked by the map pages rather
    # than inlined the way Leaflet was: 267 KB gzipped is worth fetching
    # once and caching across both map pages, where 47 KB was not.
    for lib in ("maplibre-gl.js", "maplibre-gl.css", "pmtiles.js"):
        shutil.copy(os.path.join(ROOT, "assets", lib),
                    os.path.join(DOCS, "assets", lib))
        print(f"  assets/{lib}")

    # The maps themselves: vector tiles, one popup shard per postcode
    # area, and the national name index. All from build_tiles.py, which
    # must therefore have run - a missing tile set is a blank map, so
    # copy it loudly rather than skipping what is not there.
    for grain in ("districts", "sectors"):
        for rel in (os.path.join("tiles", f"{grain}.pmtiles"),
                    f"{grain}_index.json"):
            src = os.path.join(ROOT, "map", rel)
            if not os.path.exists(src):
                raise SystemExit(
                    f"map/{rel} is missing - run scripts/build_tiles.py "
                    f"before build_site.py, or the published map is blank")
            dst = os.path.join(DOCS, "assets", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
            print(f"  assets/{rel}  ({os.path.getsize(dst) / 1e6:.1f} MB)")
        units_src = os.path.join(ROOT, "map", "units", grain)
        units_dst = os.path.join(DOCS, "assets", "units", grain)
        shutil.rmtree(units_dst, ignore_errors=True)
        shutil.copytree(units_src, units_dst)
        print(f"  assets/units/{grain}/  "
              f"({len(os.listdir(units_dst))} area files)")

    # compact per-district lookup for the landing-page search (no geometry)
    with open(os.path.join(ROOT, "data", "districts_risk.geojson"),
              encoding="utf-8") as fh:
        feats = [f["properties"] for f in json.load(fh)["features"]]
    lookup = sorted(
        ({"n": p["name"], "g": int(p["group"]), "p": round(p["premium"]),
          "s": round(p["sub_score"], 2), "w": round(p["wx_score"], 2),
          "f": round(p["fl_score"], 2), "gw": round(p["gw_score"], 2),
          "u": round(p["uplift_pct"], 1),
          # premium build-up: eight expected losses + allocated capital
          # (el_th/el_eow/el_fire/el_ad .get-guarded for the pre-rebuild
          # window, like load_stats). NB "ef" is FLOOD (named before
          # fire existed); fire is "efi", AD is "ea" - a duplicate key
          # here would silently drop the older entry from every
          # decomposition.
          "es": round(p["el_sub"]), "ew": round(p["el_wx"]),
          "ef": round(p["el_fl"]), "eg": round(p["el_gw"]),
          "et": round(p.get("el_th", 0)),
          "ee": round(p.get("el_eow", 0)),
          "efi": round(p.get("el_fire", 0)),
          "ea": round(p.get("el_ad", 0)),
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
            "el_sub", "el_wx", "el_fl", "el_gw", "el_th", "el_eow",
            "el_fire", "el_ad",
            "sub_score",
            "wx_score",
            "fl_score", "gw_score", "f_high", "f_low", "sw_high", "sw_low",
            "gw_frac", "sw_depth_m", "sw_sev", "th_rate", "eow_rate",
            "frost_days", "fire_rate", "ad_rate",
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
