"""Analytic EL (p x E[sev]) per peril vs the PUBLISHED el_* columns.

calibrate_frequency and marginal_params are deterministic given the
scores, so this is the level the calibration ASKS FOR, with no Monte
Carlo anywhere in it. Two things it measures:

  published vs analytic  - simulation error. Should be ~0 for a peril
                           that takes its EL analytically (th/eow/fire/ad
                           do; sub/wx/fl/gw do not - see HANDOFF's
                           "Model audit 2026-08-18", defect 1).
  analytic vs ABI        - calibration error. Should be 0.00% for every
                           peril with a published anchor. Flood is not,
                           because its severity blend is geometric
                           (defect 2).

The score assembly below deliberately RE-DERIVES what build_model.main()
does rather than importing it: an audit that shares code with the thing
it audits cannot catch a bug in the shared part. check_scored_columns()
is called as a cheap staleness guard - if main() grows a column, this
script fails loudly instead of silently checking a different model.

    .venv/Scripts/python.exe scripts/analytic_el_check.py
"""
import sys, os, json, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import build_model as bm

g = bm.load_districts()
bng = g.to_crs(27700)
pts = bng.geometry.representative_point()
targets = np.column_stack([pts.x.values, pts.y.values])
(g["sub_score"], g["geol"], g["sup_frac"], g["sup_geol"]) = bm.subsidence_score(bng)
g["wx_score"], wx_raw = bm.weather_from_metoffice(targets)
# carried only so check_scored_columns() passes - the marginals ignore them
g["wind_ms"] = wx_raw["wind"]
g["wdr_idx"] = wx_raw["wdr"]
g["rain10_days"] = wx_raw["rain10"]
g["precip_mm"] = wx_raw["precip"]
g["gust_rp50"] = wx_raw["gust_rp50"]
(g["fl_score"], g["f_high"], g["f_low"],
 g["sw_high"], g["sw_low"]) = bm.flood_from_agencies(g["name"].values)
g["gw_score"], g["gw_frac"] = bm.groundwater_from_ea(g["name"].values)
g["country"] = bm.load_country(g["name"].values)
g["er_score"], er = bm.erosion_from_ncerm(g["name"].values)
for c, v in er.items():
    g[c] = v
g["er_frac"] = g["er_head"]
g["households"] = bm.load_households(g["name"].values)
g["sw_sev"], g["sw_depth_m"] = bm.sw_depth_severity(
    g["name"].values, g["sw_high"].values, g["sw_low"].values,
    g["households"].values)
g["th_rate"] = bm.theft_from_police(g["name"].values, g["households"].values)
g["frost_days"] = bm.frost_from_metoffice(targets)
fmean = np.average(g["frost_days"], weights=g["households"])
g["eow_rate"] = bm.ABI_TARGET_FREQ["eow"] * (
    (1.0 - bm.EOW_FREEZE_SHARE)
    + bm.EOW_FREEZE_SHARE * g["frost_days"] / fmean)
fire_raw = bm.fires_from_mhclg(g["name"].values, g["households"].values)
g["fire_rate"] = bm.ABI_TARGET_FREQ["fire"] * fire_raw / np.average(
    fire_raw, weights=g["households"])
cs = bm.children_from_census(g["name"].values, g["households"].values)
g["ad_rate"] = bm.ABI_TARGET_FREQ["ad"] * (
    (1.0 - bm.AD_CHILD_SHARE) + bm.AD_CHILD_SHARE * cs / np.average(
        cs, weights=g["households"]))

bm.check_scored_columns(g)
bm.calibrate_frequency(g)
m = bm.marginal_params(bm._fields(g))

n = len(g)
def emean(s):
    return np.exp(np.asarray(s["mu"], dtype=float) + 0.5 * s["sigma"] ** 2)

pub = {f["properties"]["name"]: f["properties"] for f in
       json.load(io.open(bm.OUT, encoding="utf-8"))["features"]}
names = list(g["name"])
w = g["households"].values
print(f"\ndistricts scored={n} published={len(pub)} matched="
      f"{sum(1 for x in names if x in pub)}")

PAID = {"sub": "subsidence_paid", "wx": "storm_paid", "fl": "flood_paid",
        "th": "theft_paid", "eow": "eow_paid", "fire": "fire_paid",
        "ad": "ad_paid"}
print(f"\n{'peril':6}{'analytic':>10}{'published':>11}{'pub vs ana':>12}"
      f"{'ABI/policy':>12}{'ana vs ABI':>12}")
ta = np.zeros(n); tp = np.zeros(n)
for k in ("sub", "wx", "fl", "gw", "th", "eow", "fire", "ad"):
    ana = np.broadcast_to(np.asarray(m["p_" + k] * emean(m["sev_" + k]),
                                     dtype=float), (n,))
    pb = np.array([pub[x]["el_" + k] for x in names], dtype=float)
    ta = ta + ana; tp = tp + pb
    a = float(np.average(ana, weights=w)); p = float(np.average(pb, weights=w))
    abi = bm.ABI[PAID[k]] / bm.POLICIES if k in PAID else float("nan")
    print(f"{k:6}{a:10.4f}{p:11.4f}{100*(p/a-1):+11.2f}%{abi:12.4f}"
          f"{100*(a/abi-1):+11.2f}%" if k in PAID else
          f"{k:6}{a:10.4f}{p:11.4f}{100*(p/a-1):+11.2f}%{'-':>12}{'-':>12}")
a = float(np.average(ta, weights=w)); p = float(np.average(tp, weights=w))
print(f"{'TOTAL':6}{a:10.4f}{p:11.4f}{100*(p/a-1):+11.2f}%")
