"""Assemble the what-happened analysis page.

Injects data/year_analysis.json, the two ABI series
(data/abi_annual.csv, data/abi_subsidence.csv), the hazard history and
the sensitivity table into analysis/template.html ->
analysis/uk_risk_year_analysis.html (fully self-contained).
"""

import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def read_csv(name):
    with open(os.path.join(ROOT, "data", name), newline="",
              encoding="utf-8") as f:
        return list(csv.DictReader(f))


def source_label(vintage):
    """'2025-02 release comparative' -> 'ABI 2025-02'. The odd vintages
    ('2024-11 and 2025-01 winter advice') keep their own words."""
    m = re.match(r"\d{4}-\d{2}", vintage)
    return "ABI " + (m.group() if m else vintage)


def abi_payload():
    """The two ABI series, as the page's chart and table read them.

    The `note` column - the quoted press-release wording each figure was
    recovered from - stays OUT of the page payload on purpose: it is
    provenance, not content, and the sources strip links straight to the
    CSVs that carry it. Rows are sorted and sources deduped by URL so
    the output is byte-stable across rebuilds.
    """
    annual = sorted(
        ({"y": int(r["year"]), "m": r["metric"],
          "v": float(r["value_gbp_m"]), "basis": r["basis"],
          "vintage": r["vintage"]}
         for r in read_csv("abi_annual.csv")),
        key=lambda r: (r["y"], r["m"], r["vintage"]))

    seen, sources = {}, []
    for r in (read_csv("abi_annual.csv") + read_csv("abi_subsidence.csv")):
        url = r["source"].split()[0]
        if url.startswith("http") and url not in seen:
            seen[url] = True
            sources.append({"label": source_label(r["vintage"]), "url": url})
    sources.sort(key=lambda s: (s["label"], s["url"]))

    sub = sorted(
        ({"p": r["period"], "m": r["metric"], "v": float(r["value"]),
          "unit": r["unit"], "basis": r["basis"],
          "prov": r["provenance"], "vintage": source_label(r["vintage"])}
         for r in read_csv("abi_subsidence.csv")),
        key=lambda r: (r["p"], r["m"], r["vintage"]))

    return ({"annual": annual, "sources": sources}, {"rows": sub})


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

    abi, abi_sub = abi_payload()
    html = (template
            .replace("__DATA__", data.replace("</", "<\\/"))
            .replace("__SENS__", sens.replace("</", "<\\/"))
            .replace("__HISTORY__", hist.replace("</", "<\\/"))
            .replace("__ABI__", json.dumps(abi, separators=(",", ":"))
                     .replace("</", "<\\/"))
            .replace("__ABI_SUB__", json.dumps(abi_sub, separators=(",", ":"))
                     .replace("</", "<\\/")))
    out = os.path.join(ROOT, "analysis", "uk_risk_year_analysis.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {out} ({os.path.getsize(out) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
