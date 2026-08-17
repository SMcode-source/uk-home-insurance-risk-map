"""Generate the favicon and the social preview card from the real data.

Both images are rendered from data/districts_risk.geojson, so the artwork
IS the model output rather than a stock illustration:

  docs/assets/social.png        1200x630 Open Graph / Twitter card
  docs/assets/social-github.png 1280x640 opaque copy of the same card, for
                                GitHub's repository social preview, which
                                wants that size and has to be set by hand
  docs/assets/favicon.svg       vector favicon (UK silhouette, peril colours)
  docs/assets/favicon-32.png    raster fallback
  docs/assets/apple-touch-icon.png  180x180 for iOS home screens

Run after build_model.py; build_site.py copies nothing here, the files are
written straight into docs/assets/.
"""

import os

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "docs", "assets")

# the map's rating-group ramp (dataviz blue, light -> dark)
RAMP = ['#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7',
        '#3987e5', '#2a78d6', '#256abf', '#184f95', '#0d366b']
# The INSURED perils (light-theme hues). Coastal erosion has its own hue
# on the site (rose, --er) but is deliberately absent here: the favicon
# and card stand for the premium model, and erosion is not part of the
# premium. The favicon stays quartered in the four vine perils - seven
# quadrants at 16px is noise - but the card's dot row carries all seven.
PERIL = {'sub': '#eb6834', 'wx': '#2a78d6', 'fl': '#1baf7a', 'gw': '#6f5cc4',
         'th': '#7a6115', 'eow': '#006d7d', 'fire': '#a4262c'}
INK = '#0b0b0b'
MUTED = '#6f6d67'
SURFACE = '#fcfcfb'


def load():
    gdf = gpd.read_file(os.path.join(ROOT, "data", "districts_risk.geojson"))
    return gdf.to_crs(27700)


def social_card(gdf):
    """1200x630 card: the real rating-group choropleth plus the headline."""
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor(SURFACE)

    # map on the right, text on the left
    ax = fig.add_axes([0.52, 0.02, 0.46, 0.96])
    ax.set_facecolor(SURFACE)
    gdf.plot(ax=ax, column="group", cmap=ListedColormap(RAMP),
             linewidth=0.06, edgecolor="white")
    ax.set_axis_off()
    ax.set_aspect("equal")

    t = fig.text(0.055, 0.80, "UK Home Insurance\nRisk Map",
                 fontsize=41, fontweight=650, color=INK,
                 linespacing=1.08, va="top")
    t.set_fontfamily(["Segoe UI", "DejaVu Sans", "sans-serif"])

    sub = fig.text(0.055, 0.565,
                   "Subsidence · Weather · Flood · Groundwater\n"
                   "Theft · Escape of water · Fire",
                   fontsize=16.5, color=MUTED, linespacing=1.35, va="top")
    sub.set_fontfamily(["Segoe UI", "DejaVu Sans", "sans-serif"])

    # seven peril dots, echoing the site nav. Figure coordinates are not
    # square (12 x 6.3in), so a Circle would render as an ellipse - use an
    # Ellipse with the aspect baked into its height.
    from matplotlib.patches import Ellipse
    aspect = fig.get_figwidth() / fig.get_figheight()
    dia = 0.0125
    for i, c in enumerate(PERIL.values()):
        fig.add_artist(Ellipse((0.0605 + i * 0.0235, 0.415),
                               width=dia, height=dia * aspect,
                               transform=fig.transFigure,
                               facecolor=c, edgecolor="none"))

    body = fig.text(
        0.055, 0.345,
        "2,736 postcode districts, 26.4m households.\n"
        "Seven insured perils, one dependence model,\n"
        "every hazard input open data.",
        fontsize=15.5, color="#52514e", linespacing=1.5, va="top")
    body.set_fontfamily(["Segoe UI", "DejaVu Sans", "sans-serif"])

    url = fig.text(0.055, 0.075,
                   "smcode-source.github.io/uk-home-insurance-risk-map",
                   fontsize=13, color=MUTED)
    url.set_fontfamily(["Segoe UI", "DejaVu Sans", "sans-serif"])

    path = os.path.join(OUT, "social.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print(f"  social.png  ({os.path.getsize(path) / 1e3:.0f} KB)")
    _github_variant(path)


def _github_variant(src):
    """A 1280x640 opaque copy for GitHub's repository social preview.

    The 1200x630 card above is the Open Graph / Twitter size and is what the
    site's own pages reference. GitHub's repo setting asks for 1280x640 and
    has to be uploaded by hand (no API exists), so a correctly sized copy is
    generated here rather than being resized ad hoc each time it is needed.

    Two differences that matter for that upload: the aspect ratio is padded
    rather than stretched, so nothing distorts; and the alpha channel is
    flattened, because GitHub's image processing has been known to reject
    RGBA PNGs without reporting an error.
    """
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    target = (1280, 640)
    scale = min(target[0] / im.width, target[1] / im.height)
    resized = im.resize((round(im.width * scale), round(im.height * scale)),
                        Image.LANCZOS)
    canvas = Image.new("RGB", target, _rgb(SURFACE))
    canvas.paste(resized,
                 ((target[0] - resized.width) // 2,
                  (target[1] - resized.height) // 2),
                 mask=resized.split()[-1])
    out = os.path.join(OUT, "social-github.png")
    canvas.save(out, "PNG", optimize=True)
    print(f"  social-github.png  ({os.path.getsize(out) / 1e3:.0f} KB, "
          f"1280x640, opaque - for the repo social preview)")


def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _band_edges(gdf):
    """Latitude cuts splitting the landmass into four equal-area bands.

    Equal-height bands do not work: Shetland stretches the bounding box
    ~200 km north of the mainland, so the top quarter would be empty sea.

    The cuts are computed from the 2,736 DISTRICT polygons, not from the
    unioned coastline - the union is one giant mainland polygon holding
    ~90% of the area, so cumulative-area quantiles over it collapse all
    three cuts onto a single latitude and three of the four bands vanish.
    """
    geoms = gdf.geometry.values
    ys = shapely.get_y(shapely.point_on_surface(geoms))
    areas = shapely.area(geoms)
    order = np.argsort(ys)
    ys, areas = ys[order], areas[order]
    cum = np.cumsum(areas) / areas.sum()
    return [float(ys[np.searchsorted(cum, q)]) for q in (0.25, 0.5, 0.75)]


def _outline_svg_path(gdf, size, pad=1.0, edges_src=None):
    """UK outline as an SVG path string, fitted to a square viewBox."""
    union = shapely.union_all(gdf.geometry.values)
    union = shapely.simplify(union, 2500)          # 2.5 km - icon scale
    minx, miny, maxx, maxy = shapely.bounds(union)
    span = max(maxx - minx, maxy - miny)
    k = (size - 2 * pad) / span
    offx = pad + ((span - (maxx - minx)) * k) / 2
    offy = pad + ((span - (maxy - miny)) * k) / 2

    def ring(coords):
        pts = [(offx + (x - minx) * k, size - (offy + (y - miny) * k))
               for x, y in coords]
        return ("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z")

    parts, keep = [], []
    for poly in shapely.get_parts(union):
        if shapely.area(poly) < 4e7:               # drop specks < 40 km2
            continue
        keep.append(poly)
        parts.append(ring(shapely.get_coordinates(
            shapely.get_exterior_ring(poly))))
    # band edges converted from BNG into icon y (SVG y grows downwards)
    edges = [size - (offy + (y - miny) * k) for y in _band_edges(gdf)]
    return " ".join(parts), sorted(edges)


def favicon(gdf):
    """Vector favicon: the UK, quartered in the four peril colours."""
    size = 64
    d, edges = _outline_svg_path(gdf, size)
    # Four equal-AREA horizontal bands (see _band_edges).
    cuts = [0.0] + edges + [float(size)]
    bands = "\n".join(
        f'<rect x="0" y="{cuts[i]:.1f}" width="{size}" '
        f'height="{cuts[i + 1] - cuts[i]:.1f}" fill="{c}"/>'
        for i, c in enumerate([PERIL['wx'], PERIL['gw'],
                               PERIL['sub'], PERIL['fl']]))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">
<defs>
<clipPath id="uk"><path d="{d}"/></clipPath>
</defs>
<rect width="{size}" height="{size}" rx="12" fill="{SURFACE}"/>
<g clip-path="url(#uk)">
{bands}
</g>
</svg>
"""
    path = os.path.join(OUT, "favicon.svg")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"  favicon.svg ({os.path.getsize(path) / 1e3:.1f} KB)")
    return d


def favicon_png(gdf, sizes=((32, "favicon-32.png"), (180, "apple-touch-icon.png"))):
    """Raster the same mark via matplotlib (no SVG rasteriser needed)."""
    union = shapely.simplify(shapely.union_all(gdf.geometry.values), 2000)
    polys = [p for p in shapely.get_parts(union) if shapely.area(p) >= 4e7]
    minx, miny, maxx, maxy = shapely.bounds(union)

    for px, name in sizes:
        fig = plt.figure(figsize=(px / 100, px / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor(SURFACE)
        fig.patch.set_facecolor(SURFACE)
        g = gpd.GeoSeries(polys, crs=27700)
        cuts = [miny] + _band_edges(gdf) + [maxy]
        for i, colour in enumerate([PERIL['fl'], PERIL['sub'],
                                    PERIL['gw'], PERIL['wx']]):
            part = g.clip(shapely.box(minx, cuts[i], maxx, cuts[i + 1]))
            if len(part):
                part.plot(ax=ax, color=colour, linewidth=0)
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_aspect("equal")
        ax.set_axis_off()
        path = os.path.join(OUT, name)
        fig.savefig(path, facecolor=SURFACE, dpi=100)
        plt.close(fig)
        print(f"  {name} ({os.path.getsize(path) / 1e3:.1f} KB)")


def main():
    os.makedirs(OUT, exist_ok=True)
    print("rendering images from the model output...")
    gdf = load()
    social_card(gdf)
    favicon(gdf)
    favicon_png(gdf)
    print("done")


if __name__ == "__main__":
    main()
