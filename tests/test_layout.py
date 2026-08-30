"""Layout regression tests: the built site in docs/, in a real browser.

Why these exist: one mobile audit (2026-08-08) found three real user-facing
defects — chart labels rendered at 3.6px, zoom buttons buried under a panel
so taps fell through to the metric buttons, and a 1,076px popup clipped off
screen with no way to scroll — and *none* of them was visible to the other
38 tests, because all three are properties of a laid-out page, not of the
data. Each test here is one of those defects generalised into an invariant.

Lessons encoded here (learned the hard way, see the commit messages):

  * "Nothing overflows" is not "it is readable". An SVG with width:100% and
    a fixed viewBox scales its TEXT down with everything else, so the check
    is fontSize x (renderedWidth / viewBoxWidth), never scrollWidth.
  * Measure what receives the tap, not whether an element exists and is
    big enough: document.elementFromPoint() found the buried zoom control
    and the covered popup close button; size checks found neither.

These tests need Playwright (pip install playwright pytest, then
`python -m playwright install chromium`). They skip — they do not fail —
where it is missing, so the model test suite stays runnable without it.
CI runs them in their own job (see .github/workflows/tests.yml).

They test docs/ served over local HTTP: file:// reports clientWidth = 0,
which makes every layout measurement meaningless (see the project notes).
"""

import functools
import io
import http.server
import os
import threading

import pytest

sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="layout tests need Playwright: pip install playwright && "
           "python -m playwright install chromium")

DOCS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))

PAGES = ["index.html", "map.html", "sectors.html", "years.html",
         "methodology.html"]

# Both maps are the same template with different data, so every map
# invariant is checked on both - a page that only one of them fails is
# exactly the drift publishing two resolutions invites.
MAP_PAGES = ["map.html", "sectors.html"]

# a real unit on each map to deep-link to (sector names carry a digit;
# CB8 6 does not exist, CB8 9 does - the data decides, not the pattern)
DEEP_LINK = {"map.html": "?d=YO25", "sectors.html": "?d=YO25%206"}

# The two shapes that caught real bugs: a phone (375x812, the audit
# viewport) and a small laptop. Nothing between them has ever broken alone.
PHONE = {"width": 375, "height": 812}
DESKTOP = {"width": 1280, "height": 800}
VIEWPORTS = {"phone": PHONE, "desktop": DESKTOP}

# Below this, rendered type is decoration, not text. The bug this guards
# against shipped labels at 3.6px; the smallest deliberate size on the site
# is 10.5px, so 9 leaves room for sub-pixel scale wobble without letting a
# real regression through.
MIN_EFFECTIVE_FONT_PX = 9.0


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler plus HTTP Range, which the maps need.

    The map's geometry is a PMTiles archive read by byte range - the
    whole point is that a viewport costs a few tiles rather than the
    12 MB file. SimpleHTTPRequestHandler ignores the Range header and
    answers 200 with the entire body, and the PMTiles client rejects
    that outright:

      Server returned no content-length header or content-length
      exceeding request. Check that your storage backend supports HTTP
      Byte Serving.

    So without this the tiles never load, every map test fails for one
    reason that has nothing to do with the map, and - worse - a green
    run would prove nothing about the thing being tested. GitHub Pages
    serves ranges; the test server now does too.

    Only the single `bytes=start-end` form is implemented, which is all
    the PMTiles client sends.
    """

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng or not rng.startswith("bytes="):
            return super().send_head()
        path = self.translate_path(self.path)
        if os.path.isdir(path) or not os.path.exists(path):
            return super().send_head()
        size = os.path.getsize(path)
        first, _, last = rng[len("bytes="):].partition("-")
        try:
            start = int(first)
            end = int(last) if last else size - 1
        except ValueError:
            return super().send_head()
        end = min(end, size - 1)
        if start > end:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206, "Partial Content")
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        # copyfile() would stream to EOF; hand back only the slice asked
        # for, or the client sees more bytes than the header promised.
        return io.BytesIO(f.read(end - start + 1))


@pytest.fixture(scope="module")
def site_url():
    """Serve docs/ over HTTP on an OS-chosen port for the whole module."""
    handler = functools.partial(RangeHandler, directory=DOCS)
    handler.log_message = lambda *a, **k: None  # keep pytest output clean
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


def open_page(browser, site_url, page_name, viewport, query=""):
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda exc: failures.append(str(exc)))
    page.goto(site_url + page_name + query, wait_until="networkidle")
    assert not failures, f"{page_name} raised in the browser: {failures}"
    return page


# ---------------------------------------------------------------- scroll --

@pytest.mark.parametrize("viewport_name", VIEWPORTS)
@pytest.mark.parametrize("page_name", PAGES)
def test_no_horizontal_page_scroll(browser, site_url, page_name,
                                   viewport_name):
    """The page body must never scroll sideways, on any page at any width.

    Wide content (tables, charts) is allowed to scroll inside its own
    container; the page itself is not. documentElement.scrollWidth catches
    anything that pokes out, whatever caused it.
    """
    page = open_page(browser, site_url, page_name, VIEWPORTS[viewport_name])
    try:
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth"
            "      - document.documentElement.clientWidth")
        assert overflow <= 1, (
            f"{page_name} at {viewport_name}: page scrolls sideways by "
            f"{overflow}px")
    finally:
        page.context.close()


# ------------------------------------------------------------- type size --

@pytest.mark.parametrize("viewport_name", VIEWPORTS)
@pytest.mark.parametrize("page_name", ["years.html", "methodology.html",
                                       "index.html"])
def test_svg_text_renders_at_readable_size(browser, site_url, page_name,
                                           viewport_name):
    """No SVG text may render below MIN_EFFECTIVE_FONT_PX.

    The 3.6px bug: a chart drawn in a 900-unit viewBox and squeezed into a
    297px card passes every overflow check while scaling its 11px labels to
    3.6px. So measure the *effective* size: fontSize x (rendered width /
    viewBox width). Zero-area and display:none SVGs are ignored — a hidden
    element has no readers.
    """
    page = open_page(browser, site_url, page_name, VIEWPORTS[viewport_name])
    try:
        result = page.evaluate("""() => {
          const bad = [];
          let measured = 0;
          for (const svg of document.querySelectorAll('svg')) {
            const rect = svg.getBoundingClientRect();
            const vb = svg.viewBox && svg.viewBox.baseVal;
            if (!rect.width || !vb || !vb.width) continue;
            const scale = rect.width / vb.width;
            for (const t of svg.querySelectorAll('text')) {
              if (!t.textContent.trim()) continue;
              const fs = parseFloat(getComputedStyle(t).fontSize);
              if (!fs) continue;
              measured++;
              const eff = fs * scale;
              if (eff < __MIN__) {
                bad.push(`"${t.textContent.trim().slice(0, 30)}" at ` +
                         `${eff.toFixed(1)}px (${fs}px x ${scale.toFixed(2)})`);
              }
            }
          }
          return { measured, bad: bad.slice(0, 12) };
        }""".replace("__MIN__", str(MIN_EFFECTIVE_FONT_PX)))
        assert not result["bad"], (
            f"{page_name} at {viewport_name}: SVG text renders below "
            f"{MIN_EFFECTIVE_FONT_PX}px: {result['bad']}")
        # A guard that measures nothing is worse than no guard: the years
        # page alone draws dozens of tick and axis labels. If this count
        # collapses, the extraction stopped matching — not the page went
        # quiet. 25, not 40: the phone redraw thins ticks and labels on
        # purpose (measured: 32 at 375px, ~50 wide).
        if page_name == "years.html":
            assert result["measured"] >= 25, (
                f"only {result['measured']} SVG text nodes measured on "
                f"{page_name} — the charts stopped rendering or the "
                f"selector went stale")
    finally:
        page.context.close()


# ------------------------------------------------------------- hit tests --

def element_at_center_of(page, selector):
    """Which element actually receives a tap at SELECTOR's centre?

    Returns a diagnostic dict; hit=True when the receiver is the element
    itself or a descendant of it. This is the check that found the zoom
    buttons buried under #controls — they existed, were full-size, and
    were not tappable.
    """
    return page.evaluate("""(selector) => {
      const el = document.querySelector(selector);
      if (!el) return { exists: false };
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return { exists: true, visible: false };
      const receiver =
        document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return {
        exists: true, visible: true,
        hit: receiver !== null && (receiver === el || el.contains(receiver)),
        receiver: receiver ? receiver.tagName + '.' + receiver.className : null,
      };
    }""", selector)


@pytest.mark.parametrize("page_name", MAP_PAGES)
@pytest.mark.parametrize("viewport_name", VIEWPORTS)
def test_map_controls_receive_taps(browser, site_url, viewport_name, page_name):
    """Zoom buttons and metric buttons must be the top element at their own
    centre — existing is not enough, the tap has to land on them."""
    page = open_page(browser, site_url, page_name, VIEWPORTS[viewport_name])
    try:
        page.wait_for_selector(".maplibregl-ctrl-zoom-in")
        page.wait_for_selector(".metric-btns button.active")
        for selector in (".maplibregl-ctrl-zoom-in",
                         ".maplibregl-ctrl-zoom-out",
                         ".metric-btns button.active"):
            probe = element_at_center_of(page, selector)
            assert probe.get("exists"), f"{selector} missing from map.html"
            assert probe.get("visible"), f"{selector} has no size"
            assert probe.get("hit"), (
                f"map.html at {viewport_name}: a tap on {selector} lands on "
                f"{probe.get('receiver')} instead — it is buried")
    finally:
        page.context.close()


@pytest.mark.parametrize("page_name", MAP_PAGES)
@pytest.mark.parametrize("viewport_name", VIEWPORTS)
def test_district_popup_fits_and_scrolls(browser, site_url, viewport_name,
                                         page_name):
    """An open district popup must sit inside the map area, be scrollable
    when its content overflows, and keep its close button tappable.

    The bug this generalises: the popup was 1,076px tall, drawn with 430px
    of itself above the top of the screen, and Leaflet had no maxHeight so
    there was no way to scroll to the clipped rows.

    The deep link (?d=...) opens the popup without needing a canvas click,
    which also exercises the deep-link path itself.
    """
    page = open_page(browser, site_url, page_name, VIEWPORTS[viewport_name],
                     query=DEEP_LINK[page_name])
    try:
        page.wait_for_selector(".maplibregl-popup-content")
        # the keep-clear pass waits for the fitBounds animation to settle
        # (moveend, or its 350ms fallback), so give the whole chain a beat
        page.wait_for_timeout(1000)

        box = page.evaluate("""() => {
          const pop = document.querySelector('.maplibregl-popup-content');
          const wrap = document.querySelector('.maplibregl-popup');
          const mapBox = document.getElementById('map').getBoundingClientRect();
          const r = wrap.getBoundingClientRect();
          const style = getComputedStyle(pop);
          return {
            top: r.top, bottom: r.bottom, left: r.left, right: r.right,
            mapTop: mapBox.top, mapBottom: mapBox.bottom,
            mapLeft: mapBox.left, mapRight: mapBox.right,
            overflows: pop.scrollHeight > pop.clientHeight + 1,
            scrollable: ['auto', 'scroll'].includes(style.overflowY),
            clientHeight: pop.clientHeight,
          };
        }""")
        pad = 2
        assert box["top"] >= box["mapTop"] - pad and \
               box["bottom"] <= box["mapBottom"] + pad and \
               box["left"] >= box["mapLeft"] - pad and \
               box["right"] <= box["mapRight"] + pad, (
            f"map.html at {viewport_name}: popup "
            f"({box['top']:.0f}..{box['bottom']:.0f}, "
            f"{box['left']:.0f}..{box['right']:.0f}) sticks out of the map "
            f"({box['mapTop']:.0f}..{box['mapBottom']:.0f}, "
            f"{box['mapLeft']:.0f}..{box['mapRight']:.0f})")
        if box["overflows"]:
            assert box["scrollable"] and box["clientHeight"] > 60, (
                f"map.html at {viewport_name}: popup content overflows "
                f"({box['clientHeight']}px window) but cannot scroll")

        probe = element_at_center_of(page, ".maplibregl-popup-close-button")
        assert probe.get("hit"), (
            f"map.html at {viewport_name}: popup close button is covered "
            f"by {probe.get('receiver')}")
    finally:
        page.context.close()


def test_map_page_has_accessible_data_routes(browser, site_url):
    """The map renders 2,736 districts onto one canvas — zero per-district
    DOM, so no screen-reader or keyboard route to the numbers. The page
    must therefore (a) be a landmark, (b) link the CSV and the postcode
    lookup as alternate routes, and (c) expose which layer button is
    active as state, not just as a colour."""
    page = open_page(browser, site_url, "map.html", DESKTOP)
    try:
        page.wait_for_selector(".metric-btns button.active")
        assert page.locator("main").count() == 1, "map page has no <main>"
        assert page.locator(
            'a[href="assets/uk_district_risk.csv"]').count() >= 1, (
            "no CSV link — the only accessible route to the full data")
        assert page.locator('a[href="index.html#lookup"]').count() >= 1, (
            "no link to the postcode lookup")
        assert page.locator(
            '.metric-btns button[aria-pressed="true"]').count() == 1, (
            "active layer not exposed via aria-pressed")
    finally:
        page.context.close()


def test_keyboard_route_search_esc_and_arrows(browser, site_url):
    """The full keyboard path through the map, end to end: type a district
    into the search box and commit it (popup opens, focus lands inside so
    a reader starts reading), Ctrl+Arrow walks to a neighbouring district,
    Escape closes and focus comes back to the search box.

    This exercises the ONLY non-pointer route to the district data — the
    polygons are canvas pixels, so if this path breaks there is no
    keyboard access at all, and no static check can tell.
    """
    page = open_page(browser, site_url, "map.html", DESKTOP)
    try:
        page.wait_for_selector("#districtSearch:not([disabled])")
        page.fill("#districtSearch", "YO25")
        page.press("#districtSearch", "Enter")
        page.wait_for_selector(".maplibregl-popup-content")
        page.wait_for_timeout(1000)  # settle pass

        state = page.evaluate("""() => ({
          name: document.querySelector('.pop .hd').textContent,
          role: document.querySelector('.maplibregl-popup').getAttribute('role'),
          focusInside: document.querySelector('.maplibregl-popup')
                        .contains(document.activeElement),
          contentFocusable: document.querySelector('.maplibregl-popup-content')
                        .tabIndex >= 0,
          closeLabel: document.querySelector('.maplibregl-popup-close-button')
                        .getAttribute('aria-label'),
        })""")
        assert state["name"] == "YO25"
        assert state["role"] == "dialog", "popup is not exposed as a dialog"
        assert state["focusInside"], "focus did not move into the popup"
        assert state["contentFocusable"], (
            "scrollable popup content is not keyboard-reachable")
        assert state["closeLabel"], "close button has no accessible name"

        # Ctrl+Arrow walks to a different district
        page.keyboard.press("Control+ArrowDown")
        page.wait_for_function(
            "prev => document.querySelector('.pop .hd') && "
            "document.querySelector('.pop .hd').textContent !== prev",
            arg="YO25", timeout=5000)
        neighbour = page.evaluate(
            "() => document.querySelector('.pop .hd').textContent")
        assert neighbour and neighbour != "YO25"

        # Escape closes; focus must not be dropped on <body>
        page.keyboard.press("Escape")
        page.wait_for_selector(".maplibregl-popup", state="detached")
        page.wait_for_timeout(100)
        active = page.evaluate(
            "() => document.activeElement === document.body ? 'body' "
            "      : document.activeElement.id || document.activeElement.tagName")
        assert active != "body", "focus was dropped when the popup closed"
    finally:
        page.context.close()


@pytest.mark.parametrize("page_name", MAP_PAGES)
@pytest.mark.parametrize("viewport_name", VIEWPORTS)
def test_switching_metric_updates_legend(browser, site_url, viewport_name,
                                         page_name):
    """Clicking a metric button must actually switch the legend — the layer
    buttons are the page's main control and a silent no-op would be
    invisible to every static check."""
    page = open_page(browser, site_url, page_name, VIEWPORTS[viewport_name])
    try:
        page.wait_for_selector(".metric-btns button.active")
        before = page.text_content("#legendTitle")
        page.click(".metric-btns button:not(.active)")
        page.wait_for_function(
            "before => document.getElementById('legendTitle').textContent"
            "          !== before", arg=before, timeout=5000)
        after = page.text_content("#legendTitle")
        assert after and after != before
    finally:
        page.context.close()
