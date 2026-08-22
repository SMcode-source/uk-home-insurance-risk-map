"""Do the seven per-peril level anchors fit inside the ABI's own book?

The model calibrates each peril's frequency to its OWN paid total, so no
single leg is ever checked against the others. Do it here: every leg
implies a claim COUNT (paid / average), and those counts must fit inside
the ABI's 560,000 home claims with room left over for the categories the
model does not price. They do not.

    modelled  578,466 claims for GBP 2,631m   103.3% of the count,
    ABI       560,000 claims for GBP 3,400m    77.4% of the money

Both halves are the same fault seen twice: the modelled book's average
claim is GBP 4,548 against the ABI's GBP 6,071, so seven perils buy 103%
of the claims with 77% of the money. And the sign is wrong - what the
model omits (legal expenses, personal possessions, liability) is the
CHEAP end of the book, so the modelled subset's average should sit ABOVE
GBP 6,071, not a quarter below it.

Six of the seven counts are pinned by something outside the leg itself.
Theft is not: it divides a 2018 paid total by a 2025 average, and it
alone exceeds the entire budget the other six leave. It is over on every
reading of its own documented envelope, so it is the largest single
cause - but it cannot be the only one, because even at that envelope's
floor the budget is still short.

Nothing here changes the model. It reads build_model's own ABI dict, so
it cannot drift from what ships.

    .venv/Scripts/python.exe scripts/anchor_budget.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm

A, POL = bm.ABI, bm.POLICIES

# The two all-home context figures from the same ABI 2025 release the
# per-peril anchors come from (build_model.py:238).
N_ABI = 560_000
P_ABI = A["total_home_paid"]

# For each leg: which of {paid, count, severity} is the BY-PRODUCT of the
# other two, and what pins the count. A count pinned only by "this leg's
# own paid divided by this leg's own average" is not pinned at all.
LEGS = [
    ("storm", A["storm_paid"], A["sev_weather"], "count",
     "ABI 2025 paid AND ABI 2025 average, one release"),
    ("flood", A["flood_paid"], A["sev_flood"], "count",
     "ABI 2025 paid AND ABI 2025 average, one release"),
    ("subsidence", A["subsidence_paid"], A["sev_subsidence"], "count",
     "ABI 2025 paid AND ABI 2025 average, one release"),
    ("esc water", A["eow_paid"], A["sev_eow"], "sev",
     "GoCompare 29.38% of 560k - VERIFIED, and closes the triangle"),
    ("fire", A["fire_paid"], A["sev_fire"], "paid",
     "Home Office FIRE0201 attended GB dwelling fires 2024/25"),
    ("acc damage", A["ad_paid"], A["sev_ad"], "paid",
     "GoCompare 24.53% of 560k - VERIFIED (at home + outside)"),
    ("theft", A["theft_paid"], A["sev_theft"], "count",
     "NOTHING: 2018 paid / 2025 average, no independent count"),
]

# GoCompare's 2025 quote-declared claims table, the one independent
# count-based source in DATA_SOURCES (#26, #28). Away-from-home
# accidental damage is real and sits inside the ABI's 560,000, but is
# deliberately out of the model's scope (build_model.py:296) - so it is
# a charge against the remainder, not against a modelled leg.
AD_AWAY_PCT = 6.46

# DATA_SOURCES.md:402. The ABI's 2025 full-year release reports weather
# as one line instead of per-peril totals.
WEATHER_LINE = 758e6


def rule(title):
    print("=" * 82)
    print(title.center(82))
    print("=" * 82)


def main():
    n = {name: paid / sev for name, paid, sev, _, _ in LEGS}
    tot_n = sum(n.values())
    tot_p = sum(paid for _, paid, _, _, _ in LEGS)

    rule("THE COUNT OVERSHOOT AND THE MONEY UNDERSHOOT ARE ONE FAULT")
    print(f"  modelled      {tot_n:9,.0f} claims  GBP {tot_p / 1e6:6,.0f}m  "
          f"average GBP {tot_p / tot_n:6,.0f}")
    print(f"  ABI all-home  {N_ABI:9,.0f} claims  GBP {P_ABI / 1e6:6,.0f}m  "
          f"average GBP {P_ABI / N_ABI:6,.0f}")
    print(f"  ratio          {100 * tot_n / N_ABI:8.1f}%          "
          f"{100 * tot_p / P_ABI:8.1f}%              "
          f"{100 * (tot_p / tot_n) / (P_ABI / N_ABI):5.1f}%")
    print()
    print("  Seven perils buy 103% of the claims with 77% of the money")
    print("  because the modelled average claim is a quarter too cheap.")
    print("  The sign is wrong: legal expenses, personal possessions and")
    print("  liability are the cheap end of the book, so removing them")
    print("  should push the modelled average ABOVE the ABI's, not below.")
    print()
    res_n, res_p = N_ABI - tot_n, P_ABI - tot_p
    print(f"  implied remainder: {res_n:+,.0f} claims for "
          f"GBP {res_p / 1e6:,.0f}m")
    print("  A remainder cannot have negative claims, so at least one")
    print("  count is too high.")
    print()

    rule("WHAT ACTUALLY PINS EACH LEG'S CLAIM COUNT")
    print(f"{'peril':12}{'claims':>10}{'% of 560k':>11}  by-product  "
          f"what pins the count")
    for name, paid, sev, derived, note in LEGS:
        print(f"{name:12}{n[name]:10,.0f}{100 * n[name] / N_ABI:10.2f}%  "
              f"{derived:10}  {note}")
    print()

    six = tot_n - n["theft"]
    left = N_ABI - six
    print(f"  the six legs other than theft      {six:9,.0f}  "
          f"{100 * six / N_ABI:6.2f}%")
    print(f"  leaves for theft AND everything    {left:9,.0f}  "
          f"{100 * left / N_ABI:6.2f}%")
    print(f"  theft as it ships                  {n['theft']:9,.0f}  "
          f"{100 * n['theft'] / N_ABI:6.2f}%")
    print(f"  theft alone overruns that budget by "
          f"{n['theft'] - left:,.0f} claims, before a")
    print("  single unmodelled category is allowed for.")
    print()

    rule("AND THE REMAINDER IS NOT EMPTY")
    budget = 100 * left / N_ABI
    print(f"  budget left by the six pinned legs        {budget:6.2f}%")
    print(f"  less accidental damage AWAY from home     {AD_AWAY_PCT:6.2f}%"
          "   GoCompare, same table;")
    print("                                                     "
          "out of scope by")
    print("                                                     "
          "build_model.py:296")
    budget -= AD_AWAY_PCT
    print("  less liability, legal expenses, personal       ?     "
          "no published share,")
    print("       possessions, alternative accommodation         "
          "but not zero")
    print(f"  LEFT FOR THEFT                            {budget:6.2f}%"
          f"   = {budget / 100 * N_ABI:,.0f} claims")
    print()
    print(f"{'theft on each reading of its own envelope':46}"
          f"{'%/policy':>10}{'claims':>9}{'% 560k':>9}  fits?")
    for label, freq in [
        ("as it ships: 2018 paid / 2025 average", n["theft"] / POL),
        ("2018 paid at the 2018 average, as published", 0.0097),
        ("floor: if claims fell with recorded burglary", 0.0058),
    ]:
        c = freq * POL
        print(f"{label:46}{100 * freq:9.2f}%{c:9,.0f}"
              f"{100 * c / N_ABI:8.2f}%   "
              f"{'yes' if 100 * c / N_ABI <= budget else 'NO'}")
    floor = 0.0058 * POL
    print()
    print(f"  Even the FLOOR is {100 * floor / N_ABI - budget:.2f}pp over "
          f"= {floor - budget / 100 * N_ABI:,.0f} claims, with")
    print("  nothing left for liability or legal expenses. Theft is the")
    print("  largest single cause and is over on every reading - but it")
    print("  cannot be the only one. The next-largest count with no")
    print(f"  independent check is storm at "
          f"{100 * n['storm'] / N_ABI:.2f}% of all home claims,")
    print("  derived the same way: a paid total divided by an average.")
    print()

    rule("A SEPARATE MONEY-SIDE CONTRADICTION IN THE WEATHER ANCHORS")
    sf = A["storm_paid"] + A["flood_paid"]
    print("  DATA_SOURCES.md:402 records that the ABI's 2025 full-year")
    print("  release reports one GBP 758m 'weather-related damage to")
    print("  homes' line, and says it covers storm, flood AND escape of")
    print("  water. Beside the anchors themselves that cannot hold:")
    print(f"    the weather line                       "
          f"GBP {WEATHER_LINE / 1e6:6,.0f}m")
    print(f"    less model storm + flood               GBP {sf / 1e6:6,.0f}m")
    print(f"    leaves for escape of water             "
          f"GBP {(WEATHER_LINE - sf) / 1e6:6,.0f}m")
    print(f"    but the EoW anchor is                  "
          f"GBP {A['eow_paid'] / 1e6:6,.0f}m")
    print()
    print("  That was flagged as a contradiction on 2026-08-22. It is not")
    print("  one, and the rest of this section is the correction.")
    print()
    print("  RESOLVED 2026-08-23 against the primary releases: the water")
    print("  component of the weather line is BURST PIPES only, not the")
    print("  whole EoW book. The 2024-04 release itemises 2023 as storm")
    print("  GBP 133m + flood GBP 286m + burst pipes GBP 153m = GBP 572m")
    print("  against a GBP 573m total, so the 2025 residual of GBP 202m is")
    print("  burst pipes and is a SUBSET of the GBP 657m EoW anchor. No")
    print("  contradiction with that anchor. What survives: DATA_SOURCES")
    print("  :472 and :518 double-count the GBP 202m overlap, overstating")
    print("  the fire and AD headroom by that much - not by GBP 657m.")
    print()
    print(f"  Side effect worth pricing: burst pipes were GBP 153m of a GBP "
          f"{A['eow_paid'] / 1e6:,.0f}m")
    print(f"  EoW book in 2023 ({153 / (A['eow_paid'] / 1e6):.2f}) and GBP 202m "
          f"in 2025 ({202 / (A['eow_paid'] / 1e6):.2f}). The model's")
    print(f"  EOW_FREEZE_SHARE is {bm.EOW_FREEZE_SHARE:.2f}. Neither year "
          f"supports it.")
    print()

    rule("THE LEVEL IS FITTED TO ONE YEAR - IS THAT VISIBLE IN THE DATA?")
    print("  data/abi_annual.csv carries the ABI's own published annual")
    print("  totals. Set the modelled book against them:")
    print()
    obs = {}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "abi_annual.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        import csv
        for r in csv.DictReader(fh):
            if r["basis"] in ("published", "derived"):
                obs.setdefault(r["metric"], {})[int(r["year"])] = \
                    float(r["value_gbp_m"])
    print(f"{'year':8}{'ABI all-home paid':>20}{'modelled 7 perils':>20}"
          f"{'model as % of it':>19}")
    for y, v in sorted(obs.get("home_paid_total", {}).items()):
        print(f"{y:<8}{v:>17,.0f}m{tot_p / 1e6:>17,.0f}m"
              f"{100 * (tot_p / 1e6) / v:>18.0f}%")
    print()
    print("  At face value the model's EXPECTED loss for seven perils")
    print("  exceeds the ABI's ACTUAL total for every home claim in 2022")
    print("  and 2023. That looks damning and mostly is not: those are")
    print("  2022 and 2023 pounds against a 2025-anchored model. The ABI's")
    print("  average home claim rose 15% in 2025 ALONE. Index the older")
    print("  years to 2025 and the comparison changes completely:")
    print()
    print(f"{'claims inflation assumed':28}{'2022 -> 2025':>14}"
          f"{'2023 -> 2025':>14}   model as % of each")
    hp = obs.get("home_paid_total", {})
    for rate in (0.00, 0.05, 0.10, 0.15):
        a = hp.get(2022, float("nan")) * (1 + rate) ** 3
        b = hp.get(2023, float("nan")) * (1 + rate) ** 2
        print(f"{100 * rate:>24.0f}%/yr{a:>14,.0f}{b:>14,.0f}   "
              f"{100 * (tot_p / 1e6) / a:.0f}%  /  "
              f"{100 * (tot_p / 1e6) / b:.0f}%")
    print()
    print("  At anything from about 8%/yr upward the model sits BELOW every")
    print("  observed year, which is where a seven-peril subset of an")
    print("  eleven-category book belongs. The apparent overshoot was")
    print("  mostly a price-basis artefact.")
    print()
    print("  This repo has no claims-inflation index and no stated 'as at'")
    print("  date for the premium. Until it has both, no multi-year level")
    print("  can be built and comparisons like this one cannot be")
    print("  resolved. That is the finding here - not that the level is")
    print("  too high.")
    print()
    print(f"{'year':8}{'ABI storm':>12}{'ABI flood':>12}{'sum':>10}"
          f"{'model anchor':>15}{'model %':>10}")
    anch = (A["storm_paid"] + A["flood_paid"]) / 1e6
    yrs = sorted(set(obs.get("storm_homes", {})) & set(obs.get("flood_homes", {})))
    for y in yrs:
        s, f = obs["storm_homes"][y], obs["flood_homes"][y]
        print(f"{y:<8}{s:>12,.0f}{f:>12,.0f}{s + f:>10,.0f}"
              f"{anch:>15,.0f}{100 * anch / (s + f):>9.0f}%")
    if yrs:
        m = sum(obs["storm_homes"][y] + obs["flood_homes"][y]
                for y in yrs) / len(yrs)
        print(f"{'mean':8}{'':12}{'':12}{m:>10,.0f}{anch:>15,.0f}"
              f"{100 * anch / m:>9.0f}%")
        print()
        print(f"  Storm and flood are anchored {100 * anch / m - 100:.0f}% "
              f"above their own {len(yrs)}-year average.")
        print("  Do NOT read that as proof the level is too high. The")
        print("  anchor IS the model's mean by construction, the simulated")
        print("  distribution is strongly right-skewed (cv ~0.9, median")
        print("  ~25% below mean), and most years fall below the mean of a")
        print("  skewed distribution. Three years averaging below it is")
        print("  what that looks like, not evidence against it.")
        print("  scripts/backtest_coverage.py runs the actual test - a")
        print("  bootstrap of 3-year windows - and it does not reject the")
        print("  level.")
        print()
        print("  What DOES stand, and needs no data to see: E[loss] is")
        print("  fitted to a SINGLE year. One year is one draw. The")
        print("  systemic loadings W_* get multi-decade series while the")
        print("  level gets n=1, which is backwards - every year gives you")
        print("  a total, so the mean is the better-evidenced quantity of")
        print("  the two. That is a methodology defect whether or not the")
        print("  current value happens to be close.")


if __name__ == "__main__":
    main()
