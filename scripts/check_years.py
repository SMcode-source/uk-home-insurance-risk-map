import json

a = json.load(open("data/year_analysis.json"))
print("mean annual cost/policy:", a["mean_total"])
for b in a["buckets"]:
    print(f"{b['label']:13} mean={b['mean_total']:8.1f} wx={b['mean_wx']:7.1f} "
          f"fl={b['mean_fl']:7.1f} sub={b['mean_sub']:7.1f} "
          f"gw={b.get('mean_gw', 0):6.1f} "
          f"incW={b['inc_wx_pct']:5.2f}% incF={b['inc_fl_pct']:5.2f}% "
          f"incG={b.get('inc_gw_pct', 0):5.2f}% "
          f"extra={b['extra_vs_typical']:+8.1f} indep={b['indep_mean_total']:8.1f}")
print("worst year:", a["worst_year"])
