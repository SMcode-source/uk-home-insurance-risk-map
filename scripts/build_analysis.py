"""Assemble the good-vs-bad-years analysis page.

Injects data/year_analysis.json into analysis/template.html ->
analysis/uk_risk_year_analysis.html (fully self-contained).
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def main():
    with open(os.path.join(ROOT, "analysis", "template.html"), encoding="utf-8") as f:
        template = f.read()
    with open(os.path.join(ROOT, "data", "year_analysis.json"), encoding="utf-8") as f:
        data = json.dumps(json.load(f), separators=(",", ":"))

    hist_path = os.path.join(ROOT, "data", "history.csv")
    if os.path.exists(hist_path):
        import csv
        with open(hist_path, newline="", encoding="utf-8") as f:
            rows = [{k: (v if k == "year" else float(v))
                     for k, v in r.items()} for r in csv.DictReader(f)]
        hist = json.dumps(rows, separators=(",", ":"))
    else:
        hist = "null"

    sens_path = os.path.join(ROOT, "data", "sensitivity.json")
    if os.path.exists(sens_path):
        with open(sens_path, encoding="utf-8") as f:
            sens = json.dumps(json.load(f), separators=(",", ":"))
    else:
        sens = "null"

    html = (template
            .replace("__DATA__", data.replace("</", "<\\/"))
            .replace("__SENS__", sens.replace("</", "<\\/"))
            .replace("__HISTORY__", hist.replace("</", "<\\/")))
    out = os.path.join(ROOT, "analysis", "uk_risk_year_analysis.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {out} ({os.path.getsize(out) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
