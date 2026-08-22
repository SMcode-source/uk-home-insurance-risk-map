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
    print("  DATA_SOURCES.md:472 and :518 then size the fire and")
    print("  accidental damage triangles against a remainder built by")
    print("  adding the GBP 758m weather line and the GBP 657m EoW anchor")
    print("  as SEPARATE items. On line 402's own reading that")
    print("  double-counts escape of water.")
    other = A["subsidence_paid"] + A["theft_paid"] + A["fire_paid"]
    print(f"    headroom as those two lines compute it GBP "
          f"{(P_ABI - WEATHER_LINE - A['eow_paid'] - other) / 1e6:6,.0f}m")
    print(f"    headroom if the weather line holds EoW GBP "
          f"{(P_ABI - WEATHER_LINE - other) / 1e6:6,.0f}m")
    print()
    print("  Which reading is right decides whether storm and flood are")
    print("  double-counted against EoW, or the headroom the fire and AD")
    print("  triangles were sized against is 1.8x what was documented.")
    print("  Settling it needs the ABI release itself.")


if __name__ == "__main__":
    main()
