# Handoff — UK Home Insurance Risk Map

**Written:** 2026-08-12, audited and refreshed 2026-08-16 · lives in the
repo (supersedes the old `%TEMP%\uk-risk-map-handoff.md`, which is now
just a pointer here)
**Repo:** https://github.com/SMcode-source/uk-home-insurance-risk-map ·
**Live:** https://smcode-source.github.io/uk-home-insurance-risk-map/

## Status: complete, deployed, EIGHT insured perils at TWO resolutions

**Phase 1 of the roadmap (attritional perils: theft → escape of water
→ fire → accidental damage) is COMPLETE.** Phase 2 is EPC/VOA exposure
realism; Phase 3 the buildings/contents split.

The site publishes the model at **two grains side by side**:
`/map.html` over 2,736 postcode districts and `/sectors.html` over
10,398 derived postcode sectors. One template builds both pages, so
they cannot drift; the layout suite runs every map invariant against
both. **84 tests** (two of which skip only while a publish is
mid-transition — see the theft section), CI green, Pages live. The
methodology page draws the Hull comparison as an inline SVG generated
from the published GeoJSON at build time — a screenshot would go stale
at the next rebuild; this cannot.

Current headline figures (bot commit 08be7f1, 2026-08-17):
exposure-weighted premium **£174.24** over 27.26m households; loss
cost £169.75 ≈ 77% of the £219 all-home-claims cost; climate
uplift diluted a fourth time by AD's flat ~£14.65 (each attritional
peril dilutes these — same £ of repricing on a bigger base; the site
injects them, only this file and README carry them by hand).

## Published 2026-08-16: theft, the fifth insured peril (Phase 1)

User decision: "publish theft with the p99.9 cap." Live at both
resolutions since run 31974060403 (merge c8f315f, bot commit 04bed84).
Premium £59.07 → **£88.11** (+£29.04: el_th £29.03 to the penny on the
ABI calibration, capital +£0.01 — an independent stable peril earns
nearly the full diversification credit). Every weather-peril output
stayed bit-identical through the change (verified column by column,
and the published rebuild matches the evidence artifact value-for-value
across all columns). Churn was large and REAL: 77.9% of districts
changed rating group, 1,281 by ≥2 — theft geography is nearly
orthogonal to cat geography (corr 0.04), city cores went to group 10
(B2 £25→£240).

How it is built (all of it on main now):
- `scripts/fetch_burglary.py` → `data/burglary.csv`: 668,609 burglaries
  from the police.uk 36-month archive (2023-07..2026-06) spatially
  joined to the model's own polygons — the SAME script emits
  sector-keyed counts on the sector-model branch because it reads
  `load_districts()`. Traps and anchors in DATA_SOURCES.md #25 (snap
  points, commercial contamination, BTP's Scottish leak, the
  2018-vintage ABI theft-paid figure and why propensity cancels).
- Independent compound leg OUTSIDE the vine (burglary has no weather
  root), its uniform drawn LAST in the seeded stream. Rates winsorised
  at the household-weighted p99.9 (6.22% districts / 8.29% sectors —
  the cap re-solves per resolution over its own exposure distribution;
  office cores are burgled as shops, not homes); Scotland OVERRIDDEN
  (not filled) with the national housebreaking rate, 0.29%/yr.
- Site copy (759c841): every theft number injected from committed data
  (`__TH_*__` in build_site.load_stats — the cap recovered as the max
  surviving rate, the Scotland override as the most frequent exact
  rate); popup shows the measured burglary rate, not a fake 0–1 score;
  theft bronze `--th` contrast-checked both themes; the years page
  stays four-peril episodic on purpose and says so.

**Two lessons from the evidence runs, for EoW/fire/AD (both now
guarded by tests):**
1. **A factor loading has enormous leverage at rare-event
   thresholds.** W_THEFT=0.20 on "weakly systemic" intuition implied
   worst years claiming 8–14× the mean — no burglary data shows that.
   Derive it: CV(national claim count) ≈ sqrt(w)·φ(z_p)/p; targeting
   the observed ±10-15% year-to-year variation gives W_THEFT=0.0013
   (1-in-100 systemic year ≈ 1.3× claims).
2. **A peril whose districts share ONE uniform stream must take its
   EL analytically** (p·E[sev], the el_er cure): the ~150
   threshold-clearing draws carry a COMMON error, so the whole map
   came out +17% over the calibrated level at once. Draws still feed
   the tail columns.

**And one from the publish itself:** rebuild.yml's pre-flight runs the
suite against COMMITTED state, so any change that adds a template-read
column, or lands one resolution's output before the other, deadlocks
the pre-flight against the very run that reconciles it (run
31973685105 died there). The two output-contract guards now SKIP,
self-re-armingly, while the committed state is visibly mid-transition
(f491e66) — safe because build_map.web_asset hard-fails any build
whose model output lacks a template-read column. Expect exactly those
two skips during every future peril publish, and zero after.

**Phase 1 since this section**: EoW and fire are both live (see their
sections below); AD remains.
The VOA non-domestic premises count is the proper fix for the
commercial contamination (Phase 2), replacing the winsorisation cap
with an actual commercial-exposure adjustment.

## Published 2026-08-17: escape of water, the sixth insured peril (Phase 1)

User decision: "publish escape of water." Live at both resolutions
since run 31982713790 (merge d195d60, bot commit 224fb3f). Premium
£88.11 → **£131.59** (+£42.39 EL — exactly £657m/15.5m policies —
+£1.10 capital). All five prior perils bit-identical through the
change at both grains; the sector rebuild (run 8, bot 453cef2 on
sector-model) reproduced the same £42.39 weighted mean, because the
level is calibrated and resolution cannot move it.

The design, in one line each:
- **Level**: anchor triangle from three public routes — ABI "£1.8m/day"
  ≈ £657m/yr; 29.3% of 2025's 560k home claims ≈ 164k → £4,005 avg,
  1.06%/policy — self-consistent, that's the cross-check
  (DATA_SOURCES.md #26).
- **Geography**: flat base + 15% freeze-attributable slice on HadUK
  air-frost days (the only open spatial predictor the peril supports;
  EPC dwelling age is the Phase 2 upgrade). Spread ×1.66, INVERTED vs
  cat geography (corr −0.32) — the Highlands are dear, the stormy
  southwest cheap. 21.5% of districts changed rating decile, 564 of
  589 by one.
- **Capital**: W_EOW=0.026 derived from winter 2010 (103k claims/£680m
  in six weeks ≈ 2× year → CV 0.43 at p=1.06%). Twenty times theft's
  loading; EoW buys real capital (2.6% of its EL) where theft buys
  none.
- **EL analytic** (shared-stream, same as theft), draws feed the tails.

**Two new lessons, both now guarded:**
1. **Feed the marginal a RATE, not an O(1) relativity.** The 0.5
   frequency clip in marginal_params saturates on a relativity ~1
   during the calibration pass — the level solves 2× hot and the
   geography flattens. `eow_rate` = anchor × relativity (normalised in
   main(), where the exposure weights live; never per-chunk);
   calibration re-pins the level and solves ×1.000. Caught before the
   evidence run by reasoning, pinned by a test after.
2. **Don't hard-code which peril is in flight in transition guards.**
   The nesting guard keyed on `el_th` failed (not skipped) for the EoW
   window; it now compares the full `el_*` sets (d195d60). Also:
   tests.yml's site-rebuild check had NO transition guard, so the
   merge push's tests run went red (31982708021) until the bot commit
   reconciled it — that check now skips itself in exactly the
   template-ahead-of-committed-output window, reusing
   build_map.columns_read_by_template as the single source of truth.
   Expect ZERO red runs on the fire/AD publishes.

Also fixed in the copy pass: the landing page still claimed theft was
among the perils "none of which this models" (a leftover the theft
pass missed — it was live). The claims-cost share is now INJECTED
(`__EL_CLAIMS_SHARE__`, ABI context imported from build_model), and
"Five findings"/"a fifth peril" style counting prose was reworded to
survive future additions.

## Published 2026-08-17: fire, the seventh insured peril (Phase 1)

User decision: "publish fire." Live at both resolutions since run
32020681458 (merge 74ac2d8, bot commit 2ce5928). Premium £131.59 →
**£159.60** (+£28.01: el_fire £28.00 to the penny, capital **+£0.00**
— the purest diversifier in the book). All six prior perils
bit-identical through the change at both grains (44 sector columns
verified column-by-column against run 8).

The design, in one line each:
- **Level**: no public domestic fire total exists any more, so the
  anchor is a documented triangle — 31,001 GB attended dwelling fires
  2024/25 (Home Office FIRE0201: Eng 25,465 + Sco 4,104 + Wal 1,432)
  → 0.20%/policy; ABI ~£10,200–£11,000 average payout (2019 vintage)
  indexed ~+27% → £14,000 severity; ≈ £434m ≈ 12.8% of 2025's £3.4bn
  → **£28.00/policy**. Severity is the documented weak leg
  (DATA_SOURCES.md #27). Sigma 1.3, heaviest attritional tail (~2% of
  claims >£100k), median £6,000.
- **Geography**: LSOA-level incident counts (England low-level
  geography ODS), FRA-level Wales (StatsWales cube), council-level
  Scotland, all spread over the model's own postcode lookup;
  hh-weighted p99.9 winsorisation (0.35% districts / 0.71% sectors —
  the cap re-solves per resolution). Cheapest DN39, dearest FY1
  (Blackpool's HMO belt). 1,685 districts (61.6%) changed rating
  group, but the evidence decomposition attributed only ~21% to real
  relativity movement — a flat +£28 requantiles the deciles.
- **Capital**: W_FIRE=0.000039, derived the theft way — FIRE0201's
  45-year series declines −2.5%/yr secularly; detrended YoY residual
  CV ≈2% with no spike years. Fire buys NO capital; it exists in the
  premium purely as expected loss.
- **EL analytic** (shared-stream), U_fire drawn AFTER U_eow so every
  prior peril simulates bit-identically — additive evidence diffs.

**Three lessons, all now embodied in code or comments:**
1. **The identity test is part of the wiring.** The first evidence run
   died at minute 55 because el_total = Σ el_* didn't know about
   el_fire (fixed 766603f). Then the SECTOR run died on the same test
   a different way: the 0.30 tolerance was a six-leg rounding budget,
   and one sector's seven 1dp legs stacked to exactly 0.30 + 1e-13.
   The bound is now 0.40 and states its derivation (8 × 0.05), so the
   eighth peril's author widens it in the same commit as the wiring
   (caaa15c). The sector run's raw artifact — uploaded BEFORE the
   gate, by design — was verified locally and committed by hand
   (05c5447); no rebuild needed.
2. **`table:number-rows-repeated` compresses sorted ODS rows.** The
   first parse of the England incident file silently dropped 39% of
   fires; the FIRE0201 reconciliation (exact to the incident) caught
   it. Parse content.xml directly and honour the repeat attribute.
3. **Check lookup keys against the existing map.** "ef" was already
   flood; fire is "efi". A duplicate dict key would have silently
   replaced flood in every district decomposition — Python keeps the
   last writer and says nothing.

**Next in Phase 1**: AD (accidental damage), the last attritional
peril, then Phase 2 (EPC/VOA exposure realism). *(Done — see the next
section.)*

## Published 2026-08-17: accidental damage, the eighth insured peril — Phase 1 COMPLETE

User decision: "publish AD." Live at both resolutions since run
32029400331 (merge 5e07868, bot commit 08be7f1). Premium £159.60 →
**£174.24** (+£14.64: el_ad £14.65 to the penny minus a rounding
epsilon, capital **+£0.00** — ties fire as the purest diversifier).
All seven prior perils bit-identical through the change at both
grains (sector run 32026714678 verified column-by-column against run
9; the gated and raw artifacts were byte-identical this time — the
(N+1)×0.05 identity budget, widened to 0.45 for eight legs IN THE
SAME COMMIT as the wiring, held with no manual override).

The design, in one line each:
- **Level**: no UK domestic AD total has EVER been published, so the
  anchor is a third documented triangle — ABI 560k home claims (2025)
  × 24.53% at-home AD share (GoCompare claims mix: 23.35% at-home AD
  + 1.18% at-home accidental loss; the 6.46% away-from-home slice
  EXCLUDED as personal-possessions cover) × Aviva £1,650 average
  payout (interpolated 2025 from published £1,148/2022 and
  £1,869/2026) ≈ **£227m** → el_ad £14.65, freq 0.8876%/policy.
  Cross-check: Aviva says AD is 32% of its home claims, GoCompare's
  table sums to 31%. Weak leg: the severity interpolation
  (DATA_SOURCES.md #28).
- **Geography**: the gentlest in the book, because the only published
  demographic driver is Aviva's "children cause 8% of AD claims" — a
  flat base + 8% slice scaled by census dependent-children share
  (E&W TS003 via NOMIS at LSOA, Scotland UV113 at 2022 OA through
  NRS's postcode index; 27,291,882 households conserved exactly at
  BOTH grains). District EL spread only £13.6 (L2) – £15.7 (B8); an
  8%-of-claims driver cannot honestly move more. NO winsorisation —
  a census share is bounded by construction. Cat-EL correlation
  −0.16.
- **Capital**: W_AD=0.00012, derived from the cleanest natural
  experiment available: lockdown 2020–21 — the hardest a behavioural
  peril can be shocked — moved home AD declarations only ~6%
  (GoCompare, 26 Oct 2021) → CV 3% → loading 0.012%. AD buys NO
  capital. **Search trap on the record**: the "+39% AD after
  lockdown" figure everyone quotes is Admiral MOTOR, not home.
- **EL analytic** (shared-stream), U_ad drawn AFTER U_fire so every
  prior peril simulates bit-identically — additive evidence diffs,
  fourth application of rate-not-relativity (FREQ_SCALE solves
  ×1.000), lookup key "ea" ("ee" was already escape of water — the
  duplicate-key lesson holds).

Churn at publish: 46 districts (1.7%) moved one rating group, none
two; 202 sectors (1.9%), none two — AD is nearly flat, so unlike
fire's +£28 requantiling, the deciles barely breathe. Zero red runs
end-to-end: the fire lessons (identity budget scales with legs,
tolerance widened with the wiring, raw artifact uploaded before the
gate) all held without being needed.

## Phase 3 REVISED (2026-08-18, later): 57% of the book CAN ship

The "anchors don't exist" verdict below stands for the full per-peril
split, and everything in it is still true. But it asked the wrong
question. Having exhausted every free route (DATA_SOURCES #31 third
pass, #32 the whole ABI web archive) and priced nothing, the user's
call was: **use easily accessible data, or do a high-level breakdown by
risk type.** Done — with no new data at all, and no invented parameter.

The calibrated (analytic) EL per policy, split where a published anchor
exists and left explicitly unsplit where none does. Flood and
groundwater shown on the MCM convention, the middle of the three:

| risk type | £/policy | % of cost | buildings | £ bldg | £ contents |
|---|---|---|---|---|---|
| escape of water | 42.39 | 25.0% | — | *unsplit* | *unsplit* |
| theft | 29.03 | 17.1% | 25% | 7.26 | 21.77 |
| fire | 28.00 | 16.5% | 78% | 21.84 | 6.16 |
| subsidence | 19.81 | 11.7% | 100% | 19.81 | 0.00 |
| flood | 18.91 | 11.1% | 48% | 9.08 | 9.83 |
| weather | 15.74 | 9.3% | — | *unsplit* | *unsplit* |
| accidental damage | 14.65 | 8.6% | — | *unsplit* | *unsplit* |
| groundwater | 1.34 | 0.8% | 48% | 0.64 | 0.70 |
| **anchored subtotal** | **97.09** | **57.2%** | **60%** | **58.63** | **38.47** |
| **unsplit subtotal** | **72.77** | **42.8%** | | | |
| **TOTAL** | **169.87** | **100.0%** | | | |

**The finding that matters, and it inverts the entry below.** This file
spends a paragraph on flood's three contradictory conventions (66 / 48
/ 25). Swinging flood across all three moves the portfolio buildings
share by **4.9 percentage points**. The three unanchored perils move it
by **42.8**. The flood argument is a rounding error on the real
problem; it was agonised over because it was the tractable part, not
the important one. **Escape of water alone is 25.0% of claim cost —
five times the entire flood-convention uncertainty.** Any future effort
should go at EoW and nothing else.

**What this means for the portfolio number.** It is a bound, not an
estimate: **31.8%–79.5% buildings** depending on flood convention and
on where the unanchored 42.8% falls. A 43-point band is not a headline
figure and must never be published as one. What IS publishable is the
table above — per-risk-type claim cost that sums to 100%, a cover split
on the 57.2% that has anchors, and the other 42.8% named and left
blank. That is honest, needs nothing bought, and is strictly more than
the site says today (which is nothing).

**Still true, and still the reason not to go further:** a fixed
per-peril fraction cannot vary by geography, so even a complete split
would move no district's *ranking* — it would re-label the premium, not
re-rate it. Publishing the table is a disclosure improvement, not a
model change, and needs no evidence run. **Not built into the site;
that is the user's call.**

## Phase 3 verdict (2026-08-18): the mechanism WORKS, the anchors DON'T EXIST

Phase 3 was to split each district's premium into buildings and contents
cover. **The engineering succeeded and the evidence failed.** Read this
before anyone tries it again.

**What works, and is committed** (`exp/buildings-contents`, c4b12a8): a
fixed per-peril buildings fraction `SPLIT_BUILDINGS` decomposes both EL
and Euler capital *exactly*, because `tot_v` and `cond` are linear sums
of the eight per-peril arrays. Both covers condition on the SAME `bad`
years — that is the correct Euler basis, since an insurer holds capital
against the whole portfolio, not against one section of it. Proven
empirically: on a 60-district synthetic frame all 30 pre-existing
`simulate()` columns are **bit-identical** to main, three new columns
appear, and both covers' bad-year margins are strictly positive so the
`max(...,0)` capital floor cannot break additivity. Two tests guard it
(`test_cover_split_is_a_pure_reweighting_of_the_same_losses`,
`test_cover_split_fractions_are_shares`). **Rejected on the way:**
splitting capital pro-rata by EL — buildings losses are cat-driven and
contents idiosyncratic, so they earn very different diversification
credits, which is the entire reason this model uses Euler.

**Why it cannot ship.** No published UK source gives a peril x cover-type
matrix (DATA_SOURCES #31). Anchors exist for four perils — theft ~25%
buildings (ONS CSEW nature-of-crime damage share 24.2%), fire ~78% (Home
Office cost-of-fire), subsidence ~100%, flood 48–66% (three contradictory
conventions). **Storm, groundwater, escape of water and accidental damage
have no anchor at all, and they are 43.2% of this model's claim cost** —
escape of water alone is 25.1%, the largest single peril in the book.

Sensitivity, computed against the model's own exposure-weighted claim mix:

| assumption on the unanchored four | portfolio | buildings | contents |
|---|---|---|---|
| all contents (floor) | 36.9% bldg | £64.27 | £109.97 |
| central guess | 67.2% bldg | £117.11 | £57.13 |
| all buildings (ceiling) | 80.1% bldg | £139.61 | £34.63 |

On a £174.24 premium the buildings figure ranges **£64 to £140**. That is
not a model output, it is an opinion with a currency symbol in front of
it — and it fails the house rule that killed Phase 2b: *a parameter
without a published anchor does not ship*.

**The one genuinely robust finding**, worth keeping: the *geography* of
the split survives the uncertainty even though the *level* does not.
Across 16 corner cases of the four unanchored perils, district rank
correlation against the central case stays **0.94–0.99**. Which districts
are contents-weighted is driven by peril mix, which the model knows well:
city cores (LS2, EC4M, B2, EC3V ~0.44) are contents-weighted, rural and
subsidence-exposed districts (PE16, BH31, PE35 ~0.77) buildings-weighted.
A *relative* cover-mix presentation is therefore defensible where an
absolute pounds split is not. **Not built — that is a user decision.**

Recommended if resumed: present as a dose-response/sensitivity layer (the
SUP_WEIGHT precedent), not a single shipped split. Or unblock it properly
with the IFoA's withdrawn GI papers (`webarchive@actuaries.org.uk`) or a
claims triangle.

## Phase 2 status (2026-08-17, later): 2a and 2c evidence COMPLETE, decisions pending

Both experiment branches are built, verified and priced. NEITHER is
merged - publishing is the user's decision, and none has been given.

- **2a - theft commercial denominator** (`exp/theft-commercial`,
  eebb5c2+c22aa06; evidence run 32033558205): rate = burglaries /
  (households + VOA premises), premises from NDR stock by LSOA
  (fetch_premises.py, data/premises.csv, DATA_SOURCES.md #29 on that
  branch). All non-theft columns bit-identical; el_th mean pinned
  29.03; premium/capital unchanged to the penny. Churn 229 districts
  (8.4%), 9 by >=2 groups - ALL commercial cores, all DOWN (EC3M
  10->1, W1J 394->249). Cap re-solves 6.22%->3.40%, 15 at it.
  Scottish el_th +9% via FREQ_SCALE renormalisation (flat override
  absorbs more of the pinned level - mechanism, not bug).
- **2c - CT band severity relativities** (`exp/ct-severity`, 185485c;
  evidence run 32039330290): band mix (CTSOP1.1 E&W + NRS Scotland
  2023-at-DZ2011) -> value relativity 0.69-1.94, statutory charge
  ratios normalised WITHIN nation, scaling th/eow/fire/ad severities
  with claim-weighted normalisation (fetch_ct_bands.py,
  data/ct_bands.csv, DATA_SOURCES.md #30 on that branch). Weather
  legs and every rate bit-identical; all four attritional EL means
  pinned to the penny; premium 174.24 unchanged. Churn 69.1%, 929 by
  >=2 groups: prime London up to +282 (W1J), low-band city cores
  -78 (BD1/SR1). New test pins severity-not-frequency scaling.
- **They COLLIDE in prime London** (2a cuts W1J, 2c raises it):
  whichever publishes second must rebase and re-run evidence.
  Suggested order: 2a first (smaller, promised in the theft section).
- **Publishing either also needs**: sector-grain input via the
  OUTWARD D seam on sector-model (premises.csv / ct_bands.csv), a
  site copy pass (2a: the 6.22% cap figures; 2c: severity prose),
  then merge -> rebuild commit=true -> live verify.
- Known stale, untouched (predates both): dependence_check.py and
  sensitivity.py never gained the attritional rate columns, so both
  fail at _fields today.

## Phase 2 plan (2026-08-17): sources verified, design set, nothing built yet

Every source below was probed this session — grain, licence, size and
edition confirmed, not assumed. All are OGL v3, no registration:

- **CTSOP 1.1 / 3.1 / 4.1** (VOA, England & Wales, snapshot 31 Mar
  2025, published 2025-09-25; next edition summer 2026): dwelling
  counts by **council tax band / property type / build period at LSOA
  grain**, direct zips 0.7–7.5 MB from assets.publishing.service.gov.uk
  (URLs in the fetcher when it lands). Counts rounded to 10, <5
  suppressed as "–", <1% unknown type/age — handle both in the parser.
- **Scotland dwellings by council tax band, detailed** (NRS via
  statistics.gov.scot, 10.6 MB zip, updated 2025-08-13): band × **2011
  data zone** to 2023; **the 2024 year switches to 2022 data zones**
  mid-series — use 2023 at 2011 DZ (postcode joins exist) or acquire
  the 2022-DZ postcode index first. "Dwellings by Type" is a sibling.
- **NDR stock of properties by MSOA/LSOA** (VOA, 2025 edition,
  `ndr_stock_oa_2025.zip`, 7.1 MB): **non-domestic property counts at
  LSOA** — the licence-clean route to the theft commercial fix.
  Scotland needs nothing: theft there is already the flat national
  override, so the commercial correction does not apply.

Examined and NOT chosen (record so nobody re-treads):
- **EPC bulk** (epc.opendatacommunities.org): registration wall, mixed
  licence (address fields are Royal Mail copyright — unusable in a
  public OGL repo), multi-GB, and coverage is only certificate-holding
  stock (sold/let/built since 2008 — biased newer/rented). CTSOP4.1
  gives build period for the FULL stock at the same grain with none of
  that. EPC's unique add is floor area; defer until something needs it.
- **VOA rating-list bulk** (voaratinglists.blob.core.windows.net):
  free but under restricted terms, not OGL — the statistical LSOA
  release replaces it. The data.gov.uk "VOA non-domestic" entry is a
  dead 2016 record with no links.

The design, in publish order (one experiment branch + priced evidence
each; the user decides each publication):
- **2a — theft commercial-exposure correction** (smallest first, and
  already named "the proper fix" in the theft section): police.uk
  burglary points include commercial break-ins; weight each district's
  points by its residential share hh/(hh + non-domestic premises) from
  NDR-stock-by-LSOA before the rate is formed, keeping the p99.9 cap
  as backstop. Expect the cap to stop binding where it was doing crude
  duty (W1J prices at the cap today).
- **2c — severity relativities from council-tax band mix**: bands are
  a sum-insured proxy. CRITICAL TRAP: the three nations' bands are
  incompatible regimes (England A–H on 1991 values, Wales A–I on 2003
  values, Scotland A–H on 1991 with its own ratios) — normalise WITHIN
  nation to mean 1.0, then renormalise the district multiplier
  exposure-weighted to 1.0 nationally (the depth-multiplier pattern:
  relativities only, ABI level pinned by construction).
- **2b — EoW dwelling-age slice**: CTSOP4.1 pre-war share as a second
  slice beside the 15% freeze slice — but ONLY if a published anchor
  for the age→EoW-frequency relationship can be found; without one it
  is an undocumented knob and stays out, per house rules.

## Audited 2026-08-16: every published claim re-derived from the data

A full don't-trust-the-docs pass. The code and data were CLEAN: the
model source re-read line by line with no defects found, a full
rebuild reproduced `docs/` byte-for-byte, and every headline figure
(£59.07 / 27.26m, +10.5% / +11.2%, DN32 +200% / PO6 9 +308%, 184 vs 1
improving, CB8 8.1x, HU8's four sectors, IoU 0.706/0.689, 191
stations, 33% terminated rows) verified exactly against the committed
outputs.

What had drifted was hand-written prose — numbers measured once and
never re-read after the extents were re-fetched or the exposure bug
was fixed: rivers/sea shrinkers were quoted as 61 (2.9%, −11.3pp) but
are 52 (2.5%, −11.2pp, worst HU8); surface-water decreases 10 → 5
(worst W1F −1.2pp); band growth +37.4/+28.7 → +37.7/+28.8 (prose now
names the statistic: mean district zone-fraction, not area); sector
aggregation "0.964 / 0.6%" → 0.965 / 0.4% (pre-exposure-fix values);
households.csv "2,995 districts" → 2,866; RM10 was 33→47, not 37→53;
dependence CI −9.0% to +12.8%; "21 datasets" → 24; sensitivity churn
now 6.6%–34.8% across scenarios; "71 tests" → 72.

The structural fix: the methodology page's climate-delta, aggregation
and household figures are now **computed in `build_site.py` and
injected** (`climate_band_stats()`, `__AGG_CORR__`, `__HH_DISTRICTS__`
etc.), like every other published claim. **Only README.md still
carries hand-written copies** (markdown has no build step) — re-verify
its climate/sensitivity/dependence numbers whenever the fraction CSVs,
`sensitivity.json` or `dependence.json` are regenerated. Two docstring
corrections in the same pass: `sensitivity.py` (stale churn spread)
and `validate_sectors_scotland.py`, which claimed sector IoU "can
never beat" district IoU — not a theorem, and its own output
(0.706 > 0.689) refutes it.

Why it was worth doing: aggregated back to districts the sector model
reproduces the published one (0.965 correlation, level within 0.4%),
but **19% of districts hide sectors that differ by more than 2x** in
premium - worst CB8 at 8.1x (GBP 29 to GBP 237). A district price
charges both halves of a district the average of a risk only one half
has. The splits are physical: a river through half a district, a clay
boundary under the other.

That work also turned up a real bug in the exposure weights - homes
apportioned to postcodes that no longer exist - now fixed in both
models; see below. Nothing is half-finished and nothing is waiting on
anyone. The list at the bottom is what is *blocked or optional*, not
work in progress.

## Previously (2026-08-10): the model's gust source changed

**The gust component runs on Met Office MIDAS station
observations**, not ERA5 reanalysis — the first
model change since `a1cacd0`, user-approved on priced evidence
(commit `de19471`, published by Actions run 15). Everything else from
the 2026-08-08 pick-up list also landed: layout regression tests in CI,
the popup redesign, the 5 MB map page cut to 209 KB, a full keyboard
route through the map, and postcode-sector polygons derived for all of
GB from open data.

## What the model is now, in one paragraph

Five perils per postcode district from open hazard data, joined by a
5-dim C-vine (weather at the root). Four are insured — subsidence (BGS
bedrock blended with 625k superficial at `SUP_WEIGHT` 0.5), weather
(Met Office climatologies + a 1-in-50 gust Gumbel-fitted at **191 MIDAS
stations**, ≥20 years' coverage, ≤300 m altitude), flood (severity
conditioned on EA depth bands), groundwater — calibrated per peril to
ABI 2025 payouts, exposure-weighted by census households apportioned
across LIVE postcodes only, capital Euler-allocated from the portfolio,
premiums on TVaR₉₉. Coastal erosion is in the vine but deliberately
outside the premium. A climate scenario reprices on the EA's future
flood extents: **+10.5%** exposure-weighted over the 2,087 English
districts the EA models, worst DN32 (Grimsby) +200%. Exposure-weighted
premium **£59.07** over 27.26m households. All figures re-verified from
the committed output on 2026-08-12, after the gust swap and the
exposure fix.

## Added 2026-08-12: the climate layer at sector resolution

Both maps now carry every layer. The EA's climate-change editions were
re-rasterised over the 10,398 sectors - surface water and depth bands
on runners (~66 min via the workflow's `climate=true` pass), rivers/sea
from the laptop because the EA 403s runner IPs for that WMS - and both
simulations rebuilt in the cloud. 8,730 of 10,398 sectors are covered.

National agreement holds (**+11.2%** exposure-weighted over covered
sectors vs **+10.5%** over covered districts) but the tails diverge:
worst district **DN32 +200%**, worst sector **PO6 9 +308%**, and where
the district model finds **one** district whose flood risk falls under
the scenario, the sector model finds **184**. The EA's future run is a
separate model, not a uniform uplift, so those improvements were always
in the data - district-level averaging just cancelled them against
worsening neighbours.

**Two traps this pass cost:** a workflow run checks out the SHA it was
DISPATCHED with, so a job cannot see a commit you push after
dispatching (a model job was building a no-climate model for exactly
this reason - cancel and take its artifacts instead). And
`flood_future()` needs the flood AND surface-water climate editions
together, returning no repricing view if either is missing, which is
why a partial pass degrades safely instead of publishing half a
scenario.

## Fixed 2026-08-12: households were apportioned to DEAD postcodes

ONSPD retains terminated postcodes - **897,835 of 2,694,205 rows, 33%**
- and `fetch_households.py` spread LSOA household counts across all of
them, crediting roughly 730,000 homes to addresses that no longer
exist. Every exposure weight in the model was slightly wrong, and had
been from the start.

It surfaced only because of the sector build: a dead postcode has no
Code-Point centroid, so wholly-dead sectors got no polygon and 2.7% of
exposure had nowhere to land. That mismatch was the symptom; the
phantom homes were the disease, and they were in the district model
too.

Fixed by filtering on `doterm`, priced first on `exp/live-postcodes`
(now deleted) and then applied to both resolutions: premium level
**-0.25%**, **40 districts (1.5%) change rating group**, none by more
than one, movers concentrated in rural/remote districts with the most
postcode churn per live address. National total unchanged - LSOA
totals are fixed, only their apportionment moved. **The sector/district
exposure gap closed from -2.75% to -0.06%**, and the nesting test's
tolerance was tightened from 4% to 0.5% so phantom exposure cannot
creep back.

**Trap worth remembering:** `rebuild.yml` does NOT run
`fetch_households.py` - it reads the committed CSV. The first attempt
to price this patched only the fetcher, reproduced main byte-for-byte,
and looked exactly like "no impact". Regenerate and commit the CSV,
then dispatch.

## The experiment-branch pattern (how model decisions get made here)

Three times used, three times decisive — reuse it for any future model
input change:

1. branch `exp/<name>`, change ONE input, push;
2. `gh workflow run rebuild.yml --ref exp/<name> -f commit=false`
   (~8 min on a free runner);
3. `gh run download <id> --name model-output`, then
   `python scripts/compare_rebuild.py <artifact geojson>`;
4. put the numbers in front of the user; **the swap is their call**;
5. approved → apply on main, dispatch with `commit=true`, delete the
   branch. The published output is content-identical to the evidence
   artifact (byte-compare fails on CRLF checkout — known, not a drift).

Decisions taken this way, so far:

- **SUP_WEIGHT stays 0.5** (2026-08-08). Dose-response at 0.35/0.25 was
  linear with no cliff — premium level moves <0.3%, central London
  sub_score climbs back linearly. No empirical basis to move; the data
  cannot distinguish weights because 625k publishes no thickness.
- **ERA5 → MIDAS gusts, swapped** (2026-08-10). Premium level −0.36%,
  wx_score correlation 0.974, 28.8% of districts change group but only
  20 move ≥2; relativities shift toward measured coastal exposure
  (Fraserburgh/Blyth/Whitby/Norfolk up; SY23/SY25 −18%, Brighton −16%).
  Surface evidence: `scripts/compare_gust_surfaces.py`.
- **Terminated postcodes excluded from exposure** (2026-08-12). −0.25%
  premium, 40 districts (1.5%) change group, none by >1. Applied to
  BOTH resolutions in one landing so the two maps never disagreed about
  how many homes exist. Detail in the section above.

## Corrections since the last handoff — do not reintroduce

The full historical list lives in the previous handoff's sections and
the auto-memory; these are the NEW ones:

- **Stations above 300 m are excluded from the gust reduction.** The
  first MIDAS run's top extreme was Cairngorm summit (1,237 m, fitted
  rp50 283 km/h), IDW-smeared across valley districts. A summit
  anemometer measures a climate nobody lives in. Gate + selftest in
  `gusts_from_midas.py`.
- **The map's fetch URL must stay a literal in the fetch() call** — the
  asset test extracts quoted fetch arguments. And never put a quoted
  example of a guard-matched pattern in a shipped comment: a `'...'`
  placeholder in one was chased as a filename, "existed" on Windows
  (trailing dots vanish in path lookups) and failed on Linux CI.
- **The popupopen handler must be registered BEFORE the deep-link block**
  — the deep link opens a popup synchronously, so a handler attached
  after it never sees that popup. Deep-linked popups shipped un-dodged
  for two commits because of this.
- **Never measure Leaflet geometry mid-animation.** The keep-clear pass
  once ran during the deep link's zoom animation, measured the popup at
  x=−96, "fixed" it, and the final animation frame undid everything.
  `keepClearWhenSettled()` defers on `_animatingZoom`/`_panAnim`.
- **Esc restores focus in the keydown handler, not in popupclose** — the
  popup's DOM teardown is not synchronous with `closePopup()`, and a
  focus-fell-to-body check races it (and lost, in the tests).
- **Plain arrows in the popup are reserved for scrolling** its focusable
  content; district-walking is Ctrl/Alt+arrow. The search box acts on
  'change', never 'input' — district names nest (YO2 prefixes YO25).
- **flex-basis applies to HEIGHT once flex-direction flips to column** —
  the vine diagram's row proportions collapsed every stacked panel to
  zero height on phones until the media query reset them.
- **Never iterate a SET when writing a build artifact.** Python
  randomises string hashing per process, so the map assets' JSON keys
  came out in a different order every run: my build and CI's disagreed
  by construction and CI failed as "docs/ is stale" with an unreadable
  diff. `build_map.web_asset` sorts its columns; verified by building
  twice in separate processes and comparing md5.
- **Quantise any transcendental that feeds a build artifact.** libm's
  `cos` differs by one ULP between MSVC and glibc, so the Hull figure's
  projection produced 2 different SVG path lines on Linux CI than here —
  the same "docs/ is stale" failure as the set bug, from a different
  root. Verified by perturbing `cos` one ULP (exactly those 2 lines
  changed); fixed with `round(math.cos(...), 6)` in `_panel()`
  (`3e59e7e`). Everything downstream is + − × ÷, which IEEE 754 pins.
- **Hand-written numbers rot; injected ones cannot.** Every stale figure
  the 2026-08-16 audit found was hand-written prose describing data that
  had since been regenerated. When publishing a number, compute it in
  `build_site.py` and inject it via a placeholder (the placeholder test
  polices both directions); reserve prose numbers for genuinely
  historical statements ("the first run kept Cairngorm summit").
- **A layer with no data is OMITTED, not drawn blank.** The sector map
  shipped without the climate layer until its EA extents were fetched
  (they since have been, so `OMIT_METRICS` is empty again) - because
  offering it would have painted the country grey under a legend
  reading "not modelled — England only", a false statement about *why*
  it was empty. Keep the mechanism: the next dataset to arrive late
  will need it.
- **The EA WMS throttles GitHub runners like BGS does.** Surface water,
  depth and erosion all fetched fine from Actions over the 10,398
  sectors, but rivers/sea served ~3.5 h and then 403'd every request at
  any backoff. That one is a laptop job; the fetcher's refusal to write
  an incomplete result is what stopped it shipping a hole.

## Evidence tooling now in the repo

- `scripts/compare_rebuild.py` — experiment artifact vs published model
  (premium level, churn, movers). Both model decisions above used it.
- `scripts/compare_gust_surfaces.py` — two gust point sets IDW'd to
  district level through the model's own code path.
- `scripts/compare_sector_model.py` — sectors vs districts: aggregation
  consistency, within-district spread, and the widest-range districts.
  Defaults to the two published outputs; pass paths on the branch.
- `scripts/validate_sectors_scotland.py` — derived sectors vs NRS's
  official Scottish ones, reporting district-IoU beside sector-IoU so
  boundary-set disagreement is separated from the method's own error.
  Writes `data/sector_validation.json`, which the site injects.
- `scripts/derive_sectors.py` + `fetch_codepoint.py` — the sector
  geometry itself, from OS Code-Point Open.
- `tests/test_layout.py` — the browser-level invariants (Playwright;
  skips without it), run against BOTH map pages.
  `tests/test_midas.py` — the BADC-CSV selftest.

## Environment

The durable machine notes live in the auto-memory
(`uk-risk-map-environment`); headlines: this machine sleeps mid-run
(checkpoint everything, judge progress by log lines not wall-clock);
use the harness's own background runner, never `nohup`; `python -u`
plus a log file; PowerShell-from-bash quoting is a minefield (write a
script file); layout measurement needs Playwright or the live site,
never `file://`; CRLF makes checked-out files hash differently from
served ones; Windows silently strips trailing dots in path lookups, so
a path-existence test can pass here and fail on Linux CI.

MIDAS specifics: the 8.4 GB mirror sits in gitignored `data/midas/`
(refetch: `fetch_midas.py`, needs a fresh CEDA token in
`~/.ceda_token` — tokens live ~72 h and are never committed or
printed). `data/gusts_midas.csv` is committed; `fetch_gusts.py` (ERA5)
remains the no-account fallback and regenerates the pre-swap surface.

## What remains, honestly

- **Sector geometry is derived, not official**, and always will be for
  England & Wales. Measured cost: none beyond the district outlines it
  inherits (NRS Scotland, sector IoU 0.706 vs district IoU 0.689) - but
  those district outlines are themselves community approximations, and
  0.689 is now the number to quote for them.
- **A claims triangle** (data-sharing agreement with an insurer; not
  purchasable) unblocks fitting the copulas and frequency/severity from
  data — the single highest-value missing dataset.
- **PAF/AddressBase** (licensed, ££) unblocks sub-district exposure,
  sum insured and construction type.
- **BGS superficial thickness** (licensed) would make `SUP_WEIGHT`
  physical instead of a bounded prior.

Everything else that was ever on a pick-up list is done and live.

## No secrets in this repo

`gh` uses a keyring token; the CEDA token lives only in `~/.ceda_token`
(outside the repo, expired within days of use); nothing sensitive
appears in the code, data, workflows or this file.
