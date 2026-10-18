"""Compare an experiment rebuild against the published model.

The evidence half of the experiment-branch pattern (HANDOFF.md): change
one input on a branch, run the rebuild workflow with commit=false,
download the model-output artifact, then

  python scripts/compare_rebuild.py <artifact districts_risk.geojson>

against the committed data/districts_risk.geojson. Reports the premium
level, rating-group churn, and the biggest movers with their score
columns — the numbers both the SUP_WEIGHT dose-response (2026-08-08)
and the ERA5->MIDAS gust decision (2026-08-10) were made on.
"""

import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load(path):
    with open(path, encoding="utf-8") as fh:
        gj = json.load(fh)
    return {f["properties"]["name"]: f["properties"] for f in gj["features"]}


def main(exp_path):
    base = load(os.path.join(ROOT, "data", "districts_risk.geojson"))
    exp = load(exp_path)
    assert base.keys() == exp.keys(), "district sets differ"

    names = sorted(base)
    col = lambda src, k: np.array([src[n][k] for n in names], dtype=float)
    hh = np.array([base[n].get("households", 1) for n in names], float)
    prem0, prem1 = col(base, "premium"), col(exp, "premium")
    g0, g1 = col(base, "group"), col(exp, "group")

    w0 = np.average(prem0, weights=hh)
    w1 = np.average(prem1, weights=hh)
    churn = g0 != g1
    print(f"exposure-weighted premium: £{w0:.2f} -> £{w1:.2f} "
          f"({100 * (w1 / w0 - 1):+.2f}%)")
    print(f"rating-group churn: {int(churn.sum())} of {len(names)} districts "
          f"({100 * churn.mean():.1f}%), "
          f"{100 * hh[churn].sum() / hh.sum():.1f}% of households; "
          f">=2 groups: {int((np.abs(g1 - g0) >= 2).sum())}")
    for score in ("sub_score", "wx_score", "fl_score", "gw_score"):
        s0, s1 = col(base, score), col(exp, score)
        if not np.allclose(s0, s1):
            print(f"{score}: correlation {np.corrcoef(s0, s1)[0, 1]:.3f}, "
                  f"mean {s0.mean():.3f} -> {s1.mean():.3f}")

    d = prem1 / prem0 - 1
    order = np.argsort(np.abs(d))[::-1]
    print("biggest premium movers:")
    for i in order[:12]:
        n = names[i]
        print(f"  {n:6s} £{prem0[i]:6.0f} -> £{prem1[i]:6.0f} "
              f"({100 * d[i]:+5.1f}%)  group {int(g0[i])}->{int(g1[i])}  "
              f"sub {base[n]['sub_score']:.2f}->{exp[n]['sub_score']:.2f} "
              f"wx {base[n]['wx_score']:.2f}->{exp[n]['wx_score']:.2f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
