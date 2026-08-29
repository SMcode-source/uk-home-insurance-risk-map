"""What drives each peril, and who contributes the loss.

Two questions, and they are not the same one:

  WHAT FEEDS IT   which granular dataset sets each peril's geography, at
                  what resolution, over what coverage. This is where the
                  model is strong for some perils and thin for others,
                  and the table below says which is which rather than
                  leaving it to be inferred.
  WHO PAYS IT     where the expected loss actually comes from. A peril
                  can be geographically dramatic and financially small
                  (coastal erosion) or flat and enormous (accidental
                  damage). Exposure-weighting is what separates them.

Reads the PUBLISHED district file; no simulation, no model change.

Usage:
  peril_contributions.py                 # the full report
  peril_contributions.py --top 15        # deeper district lists
"""

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DISTRICTS = os.path.join(ROOT, "data", "districts_risk.geojson")

# What sets each peril's GEOGRAPHY in the model as it stands today. The
# resolution column is the resolution of the driver, not of the output -
# every peril is published per district. "flat" means the peril has no
# spatial driver at all beyond exposure and property value.
DRIVERS = {
    "sub":  ("Subsidence", "BGS 625k bedrock + superficial clay "
             "shrink-swell", "~1:625,000 polygons", "GB"),
    "wx":   ("Storm/weather", "Met Office winter wind, wind-driven rain, "
             ">=10mm rain days, precip + MIDAS station gusts",
             "5-12 km grids; 191 gust stations", "UK"),
    "fl":   ("Flood", "EA NaFRA2 + NRW FRAW + SEPA zone fractions, "
             "with EA surface-water depth bands", "polygon fractions "
             "per district", "UK (depth: England only)"),
    "gw":   ("Groundwater", "EA groundwater alert areas (GWTR_RISK)",
             "postcode-level flag", "England; 0.02 background elsewhere"),
    "th":   ("Theft", "police.uk street-level burglary points, "
             "668,609 of them", "street-level points", "E&W; Scotland at "
             "a national housebreaking rate"),
    "eow":  ("Escape of water", "Met Office air-frost days 1991-2020 "
             "climatology, on ~15% of the peril", "1 km climatology",
             "UK, but NO year-to-year variation"),
    "fire": ("Fire", "MHCLG dwelling-fire incidents", "fire-authority "
             "area", "GB"),
    "ad":   ("Accidental damage", "Census child-share of population",
             "LSOA census", "GB"),
    "er":   ("Coastal erosion", "EA NCERM 2024 frontages",
             "coastal frontage polygons", "England only"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    import geopandas as gpd
    g = gpd.read_file(DISTRICTS)
    hh = g["households"].to_numpy(float)
    tot_hh = hh.sum()
    keys = [k for k in DRIVERS if f"el_{k}" in g.columns]
    el = {k: g[f"el_{k}"].to_numpy(float) for k in keys}
    # national expected loss per peril = exposure-weighted mean per policy
    nat = {k: float(np.average(v, weights=hh)) for k, v in el.items()}
    total = sum(nat.values())

    print("=" * 92)
    print("WHAT FEEDS EACH PERIL".center(92))
    print("=" * 92)
    print(f"{'peril':<19}{'EL/policy':>10}{'share':>8}  driver / resolution "
          f"/ coverage")
    for k in sorted(keys, key=lambda k: -nat[k]):
        name, drv, res, cov = DRIVERS[k]
        print(f"{name:<19}{nat[k]:>9.2f}{100 * nat[k] / total:>7.1f}%  "
              f"{drv}")
        print(f"{'':<37}{res}  |  {cov}")

    print("\n" + "=" * 92)
    print("WHO CONTRIBUTES THE LOSS".center(92))
    print("=" * 92)
    print("Concentration - share of each peril's national loss coming from "
          "the worst districts,\nranked by CONTRIBUTION (households x EL), "
          "not by rate. A high rate in an empty\ndistrict contributes "
          "nothing.\n")
    print(f"{'peril':<19}{'top 1%':>9}{'top 5%':>9}{'top 10%':>9}"
          f"{'top 25%':>9}{'flat?':>9}")
    for k in sorted(keys, key=lambda k: -nat[k]):
        contrib = el[k] * hh
        order = np.argsort(-contrib)
        c = np.cumsum(contrib[order]) / contrib.sum()
        n = len(c)
        pct = [c[max(int(f * n) - 1, 0)] for f in (0.01, 0.05, 0.10, 0.25)]
        # a peril whose top 25% carries ~25% of the loss has no geography
        flat = "yes" if abs(pct[3] - 0.25) < 0.03 else ""
        print(f"{DRIVERS[k][0]:<19}" + "".join(f"{100 * p:>8.1f}%" for p in pct)
              + f"{flat:>9}")

    print("\nBy country (share of each peril's national loss):")
    countries = sorted(g["country"].unique())
    print(f"{'peril':<19}" + "".join(f"{c:>12}" for c in countries)
          + f"{'  (exposure)':>14}")
    exp_share = [100 * hh[(g['country'] == c).to_numpy()].sum() / tot_hh
                 for c in countries]
    for k in sorted(keys, key=lambda k: -nat[k]):
        contrib = el[k] * hh
        row = [100 * contrib[(g["country"] == c).to_numpy()].sum()
               / contrib.sum() for c in countries]
        print(f"{DRIVERS[k][0]:<19}" + "".join(f"{v:>11.1f}%" for v in row))
    print(f"{'-- exposure --':<19}" + "".join(f"{v:>11.1f}%" for v in exp_share))

    print(f"\nTop {args.top} contributing districts per peril "
          f"(share of that peril's national loss):")
    for k in sorted(keys, key=lambda k: -nat[k]):
        contrib = el[k] * hh
        order = np.argsort(-contrib)[:args.top]
        s = "  ".join(
            f"{g['name'].iloc[i]} {100 * contrib[i] / contrib.sum():.2f}%"
            for i in order)
        print(f"  {DRIVERS[k][0]:<18}{s}")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
