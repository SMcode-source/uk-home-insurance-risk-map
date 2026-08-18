# Handoff — UK Home Insurance Risk Map

**Written:** 2026-08-12, audited and refreshed 2026-08-16 · lives in the
repo (supersedes the old `%TEMP%\uk-risk-map-handoff.md`, which is now
just a pointer here)
**Repo:** https://github.com/SMcode-source/uk-home-insurance-risk-map ·
**Live:** https://smcode-source.github.io/uk-home-insurance-risk-map/

## Status: complete, deployed, EIGHT insured perils at TWO resolutions

**Phase 1 of the roadmap (attritional perils: theft → escape of water
→ fire → accidental damage) is COMPLETE.** Phase 2 is EPC/VOA exposure
realism — **2a (theft's residential denominator) is live since
2026-08-18**, 2c sits built-but-unpublished on its branch. Phase 3 is
the buildings/contents split.

The site publishes the model at **two grains side by side**:
`/map.html` over 2,736 postcode districts and `/sectors.html` over
10,398 derived postcode sectors. One template builds both pages, so
they cannot drift; the layout suite runs every map invariant against
both. **84 tests** (two of which skip only while a publish is
mid-transition — see the theft section), CI green, Pages live. The
methodology page draws the Hull comparison as an inline SVG generated
from the published GeoJSON at build time — a screenshot would go stale
at the next rebuild; this cannot.

**Two defects are open and UNFIXED** — the four vine perils take their
EL from the draws instead of analytically, and flood severity is
blended in log space. Neither is a publishing emergency (EL is
paid ÷ policies by construction) but both are real; read "Model audit
2026-08-18" below before touching the marginals, and re-measure with
`.venv/Scripts/python.exe scripts/analytic_el_check.py`.

Current headline figures (bot commit ca83519, 2026-08-18 — 2a moved
geography, not level, so these are the same numbers):
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

## PUBLISHED 2026-08-18: Phase 2a, theft's residential denominator

User decision: "2a only". LIVE at both resolutions (merge 6d24373,
sector output crossed in 8204346 from sector-model run 11 bot 1a8f2d7,
publish run 32085591133 bot commit ca83519). Theft's rate now divides by
households PLUS VOA non-domestic premises, so each unit is charged only
the residential share of its burglary points.

Effect. Exposure-weighted premium is UNCHANGED at £174.24 districts /
£174.02 sectors — the calibration re-pins the level, so only geography
moves — and el_th stays £29.03 to the penny at both grains. The p99.9
cap is demoted from doing the commercial correction's job to a genuine
tiny-denominator backstop: 6.22% → 3.400% (15 districts on it) and
8.29% → 4.230% (78 sectors). Every non-theft column is bit-identical at
both grains (49 of 68 sector columns untouched; only the theft-derived
chain moves). Churn 9.6% of sectors, 54 by two groups or more; every
large fall is a City of London sector (EC2N 4 −£266, EC2M 7 −£265,
EC4V 4/5 −£260) and the rises are the renormalisation landing elsewhere
at +£6 to +£7.

**Three defects found while publishing, all fixed — read these first:**

1. **The premises join had no coverage guard.** `prem_table.get(n, 0.0)`
   is the right fallback for a genuinely absent area (Scotland has no
   VOA premises and is overridden anyway), but it is also how a
   mis-keyed file vanishes without trace: every lookup misses, the
   denominator silently reverts to households-only, the correction
   un-applies, and the run reports success. That is the households.csv
   void-run trap. Now raises below 95% E&W coverage (both grains score
   100.0% / 99.9%), with two tests — one pinning what the correction
   does, one pinning that a sector-keyed file on a district build raises
   AND that an E&W-complete file with no Scottish row still passes, so
   the guard cannot be "fixed" by counting Scotland.

2. **`docs/` was stale on the branch and the local check said fresh.**
   The copy pass edited templates without rebuilding. Worse, verifying
   with `build_site.py` alone gives a FALSE PASS: build_site only
   *wraps* `map/uk_home_insurance_risk_map.html`, a gitignored
   intermediate produced by `build_map.py`. Re-wrapping a stale
   intermediate reproduces the stale page and the diff comes back clean.
   **To check docs/ freshness run the full chain CI runs: `build_map.py`,
   then `build_analysis.py`, then `build_site.py`.** Less is not a check.

3. **The peril table hand-wrote the theft cap** at 3.4% — the value 2a
   was expected to produce — while the prose two sections down injects
   `__TH_CAP_PCT__` from committed output. The page contradicted itself
   (table 3.4%, prose 6.2%) for as long as the branch sat unpublished.
   The cell now takes the same injection.

**One process lesson that cost a red run.** Crossing the sector output
in its own commit (8204346) left `docs/assets/sector_data.geojson` and
`uk_sector_risk.csv` behind the data they are built from, so tests went
red in the transition window (run 32085591045). The existing
mid-transition skip only covers template-ahead-of-columns, NOT
data-ahead-of-assets, so it did not catch this. The bot commit
reconciled it and a dispatched tests run on ca83519 is fully green
(both jobs). **Next time: rebuild docs/ in the same commit that crosses
the sector output**, or teach the skip guard this second window.

## Model audit 2026-08-18: reconciliation, and TWO UNFIXED defects

> **Both defects below are now FIXED**, along with two more found
> while fixing them, on branch `exp/el-and-flood-fixes` — see
> "Built 2026-08-19" further down. Still NOT published. The
> claim-count overshoot recorded here is deliberately untouched.

The user asked whether escape of water is being counted twice through
some other factor, and for an overall check that everything adds up to
100% of claims. Reproduce any of this with
`scripts/build_model.py`'s own constants — no simulation is involved
in the analytic column, which is the point.

**No double-counting.** Each of the eight perils has its own disjoint
ABI anchor and its own driver, and no driver feeds two perils. The one
place water could have been double-charged is freeze: `EOW_FREEZE_SHARE
= 0.15` puts a frost-day slice into EoW, and frost appears nowhere
else — flood is river/sea/surface-water zone fractions, weather is
gust/wind-driven-rain/precip, neither has a freeze term. Storm-driven
water ingress sits in `wx` and burst-pipe water sits in `eow`, which is
the ABI's own boundary.

**The money reconciles. The CLAIM COUNT does not.**

| | paid £m | avg £ | claims | %/policy |
|---|---|---|---|---|
| subsidence | 307 | 17,820 | 17,228 | 0.111% |
| weather | 244 | 2,450 | 99,592 | 0.643% |
| flood | 312 | 30,000 | 10,400 | 0.067% |
| theft | 450 | 3,800 | 118,421 | 0.764% |
| escape of water | 657 | 4,000 | 164,250 | 1.060% |
| fire | 434 | 14,000 | 31,000 | 0.200% |
| accidental damage | 227 | 1,650 | 137,576 | 0.888% |
| **modelled** | **2,631** | **4,548** | **578,466** | **3.732%** |
| ABI all-home | 3,400 | 6,071 | 560,000 | |

77.4% of the money — as documented — but **103.3% of the count**. The
unmodelled remainder (subsidence-adjacent, liability, legal expenses,
personal possessions away from home, alternative accommodation as a
standalone head) would have to be **−18,466 claims for £769m** to
close. It cannot be negative, so at least one of the four
frequency-implied anchors is too high, and the modelled mix average
(£4,548) sitting well under ABI's own £6,071 says the same thing from
the other side.

**The AD anchor is where the exposure is.** Theft, EoW and fire each
have a published *paid total* and a published *average*, so their
counts are derived. AD's is built the other way round: 24.53% of
560,000 × £1,650. It is the one leg constructed FROM the count, so it
is the one that can be moved without contradicting a published total.
At the bottom of theft's documented vintage envelope (0.58%/policy —
the "if claims fell with recorded burglary" end of DATA_SOURCES #25)
the count drops to 98.2% and the residual becomes a sane 10,055 claims
at £87,262 — still high, which is what you would expect of a remainder
containing total losses and long-tail liability.

**EL is immune to all of this**, which is why it is not a publishing
emergency: each peril's EL is paid ÷ policies by construction, so the
premium is right even if the implied count is not. What the count
mismatch threatens is any future work that *reasons from frequency* —
the buildings/contents split (Phase 3) is exactly that, so read this
before using a modelled claim count as evidence for anything.

### Defect 1: four perils take their EL from the DRAWS, not analytically

`th`, `eow`, `fire` and `ad` compute EL as p × E[sev]. `sub`, `wx`,
`fl` and `gw` take `ls.mean(axis=1)` — the mean of the simulated
losses. Analytic vs published, exposure-weighted over the 2,736
districts:

| peril | analytic | published | published vs analytic | analytic vs ABI |
|---|---|---|---|---|
| sub | 19.8065 | 22.2725 | **+12.45%** | −0.00% |
| wx | 15.7419 | 15.5256 | −1.37% | +0.00% |
| fl | 18.9125 | 16.4712 | **−12.91%** | −6.04% |
| gw | 1.3419 | 0.4118 | **−69.32%** | (no anchor) |
| th | 29.0323 | 29.0339 | +0.01% | +0.00% |
| eow | 42.3871 | 42.3865 | −0.00% | −0.00% |
| fire | 28.0000 | 28.0007 | +0.00% | +0.00% |
| ad | 14.6452 | 14.6457 | +0.00% | −0.00% |
| TOTAL | 169.8673 | 168.7480 | −0.66% | |

The analytic column lands on each ABI anchor to two decimal places, so
**the calibration is exact and the simulation is what wanders.** This
is the identical bug already fixed twice in this repo — for `el_er`
("20,000 years give under one event") and for theft ("a peril sharing
one uniform stream must take its EL analytically"): the districts share
a systemic draw, so their errors are COMMON and do not average out
across the map. Three seeds at production N_SIM on 400 districts moved
sub +11.7/+2.7/+68.2%, wx −0.6/−21.1/+29.5%, fl −15.1/+15.5/+70.2%,
gw −70.4/+6.0/+70.1% — the published values are one draw from that.
Groundwater is worst because it is the rarest leg. Note `el_year =
year_loss.mean(axis=1)` is a draw mean too, so **capital is exposed
by the same mechanism**; the tail columns should keep using draws,
which is what they are for.

### Defect 2: flood severity is blended in LOG space

```python
mu_fl = (p_rs * mu_rs + p_sw * mu_sw) / np.maximum(p_fl, 1e-12)
```

That is a weighted mean of logs — a GEOMETRIC mean of the two
severities. The intended quantity, and the one the published £30,000
average is held to, is the frequency-weighted ARITHMETIC mean of
£35,000 fluvial and £18,000 surface water. `exp` is convex, so the
modelled mean sits below target; the gap is **independent of sigma**
(the σ²/2 terms cancel) and runs −4% to −5% across plausible mixes.
Measured, it is the −6.04% in the table above: flood is the ONLY
calibrated peril whose analytic EL misses its own anchor, because
`ABI_TARGET_FREQ["fl"] = flood_paid / 30,000 / POLICIES` assumes a mean
severity the marginal does not deliver. The fix is to blend the MEANS
and then take the log.

**NEITHER IS FIXED.** Both are model changes: they need an experiment
branch, a priced evidence run at both grains, and the user's publish
decision — the same bar every peril cleared. Defect 2 raises the flood
level ~6% and is a straight correction; defect 1 mostly REDUCES
subsidence and RAISES groundwater, and its real prize is that the map
stops depending on the seed.

## Built 2026-08-19, NOT PUBLISHED: four defects fixed, evidence run done

Branch `exp/el-and-flood-fixes` (e025e46, 704866b). The two defects the
2026-08-18 audit left OPEN are fixed, plus two more found while fixing
them. Every scope decision was taken by the user before any code moved
(a nine-question grilling); nothing here has been published, and the
sector worktree and `main` are untouched.

**Defect 1 — the four vine perils published draw-mean ELs.**
`calibrate_frequency` solves `FREQ_SCALE[k] = ABI_TARGET_FREQ[k] /
raw[k]` against the exposure-weighted mean of the ANALYTIC p; no draw
enters that loop, and `_median_for_mean` pins `E[sev]`. So `p*E[sev]` IS
the calibration target and the draw mean was only ever an estimate of
it. The comment that stood at the `el_total` site claimed the ABI
scaling had been "solved against" those draw means. It had not. That
comment was wrong and is corrected in the code.

Groundwater is the case that proves it, and it was hiding in plain
sight: it published £0.412 against an analytic £1.342, a 3.3x gap. Its
p is 6.7e-5 — between erosion's 1.5e-5 and the attritional legs — and
its spatial loading is 0.70, the HIGHEST of the four, so districts claim
together and the effective sample is ~20,000 correlated years, not
2,736 x 20,000 district-years. That is precisely the trap this file
already documents for erosion, at 4.5x erosion's frequency. The three
commoner vine perils hid it because their noise looks like rounding.

Capital follows: `el_year`, itself a draw mean and already +0.54%
adrift, is replaced by `el_total` in `capital` and `capital_cc`.

**Defect 2 — flood severity blended GEOMETRICALLY.** Probability-
weighting `mu` makes `exp(w1*mu1 + w2*mu2)`, the weighted geometric mean
of the medians, which sits strictly below the arithmetic mean the ABI
anchor is stated on. Now moment-matched on mean AND variance, which
makes sigma per-district; `inv_mixed_cdf` broadcasts sigma as it already
broadcast mu. Closed the gap from -6.04% to -2.26%.

**Defect 3 — the published "Median severity" column was stale.** Six of
its nine cells were hand-written in the FIRST commit (28a0609), before
eb288ee introduced the ABI calibration, and never revisited: weather
read £3,500 against a true median of £1,338 (+162%), and groundwater and
erosion showed MEANS under a median header. The four Phase 1 rows added
later were correct, so the convention was right and only the old rows
drifted. All nine are now injected from `ABI` and `SEV_SIGMA` and cannot
go stale again. `SEV_SIGMA` is promoted to module level for that purpose
only; no sigma value changes and every per-peril justification stays at
its point of use.

**Defect 4 — flood's target frequency came from a headline the model
contradicts.** Found while measuring defect 2, which narrowed the gap
but did not close it. Decomposed: the `sw_sev` normalisation basis is
worth +0.16%, the fluvial/surface-water frequency mix -2.41%. The EA
zone areas make 66.33% of flood claims fluvial; the £30,000 blended ABI
headline implies 70.59%. `sev_flood` 30,000, `sev_flood_fluvial` 35,000
and `sev_surface_water` 18,000 CANNOT all be consistent with the EA
geography — any two determine the third.

Flood is the only peril whose severity is BUILT from components rather
than read from one ABI figure, so it is the only one where `E[sev]` can
differ from the number used to turn paid into a frequency. For the other
seven, `EL == paid / POLICIES` exactly. `calibrate_frequency` now
derives flood's target from the £29,322 its legs actually blend to,
restoring that invariant. The hard anchor is the published £312m paid;
£30,000 was only ever an intermediate, and it is the one of the three
figures the model does not otherwise use. Nothing is invented, no
published component severity moves, and the +2.31% frequency rise is
uniform so no district's ranking changes. Groundwater follows, pegged
at 10% of flood.

**Measured, analytic vs ABI:**

| stage | flood gap |
|---|---|
| as published on main | -6.04% |
| after defect 2 | -2.26% |
| after defect 4 | **+0.00%** |

sub, wx, th, eow, fire and ad are +0.00% at every stage.

**Evidence run (district, seed 42, full chain build_model ->
build_analysis -> build_site):**

| column | published main | new | change |
|---|---|---|---|
| el_sub | 22.2725 | 19.8055 | -11.08% |
| el_wx | 15.5256 | 15.7434 | +1.40% |
| el_fl | 16.4712 | 20.1290 | +22.21% |
| el_gw | 0.4118 | 1.3398 | +225.38% |
| el_th, el_eow, el_fire, el_ad, el_er | — | — | **bit-identical** |
| el_total | 168.7457 | 171.1136 | +1.40% |
| capital | 5.4956 | 5.5427 | +0.86% |
| premium | 174.2409 | 176.6581 | +1.39% |

The four attritional legs are bit-identical across all 2,736 districts,
max |delta| exactly 0.000e+00 — the U-draw order th->eow->fire->ad is
preserved, as it must be.

**The number that matters most.** Excluding groundwater, which has no
published anchor, the model now reproduces `ABI_LOSS_PER_POLICY`:
£169.7738 modelled against £169.7419 published, **+0.0188%**. Before
these fixes that reconciliation was 77.4% of £3.4bn with a claim-count
overshoot; the money side is now exact to two basis points.

**Second-seed check (RNG_SEED 43), and it is stronger than the bar we
set.** The bar asked that the four vine ELs "barely move" across seeds.
They cannot move at all: now that every EL is analytic, all TEN el_*
columns are bit-identical between seed 42 and seed 43, max |delta|
exactly 0.000e+00 across all 2,736 districts. Seed dependence has been
removed from the published expected-loss level entirely, which is the
real content of defect 1. The simulated columns move as they should:
`tvar99_euler` +0.431%, capital +1.228%, premium +0.039%.

One honest caveat: `tvar99_vine` moves +14.7% between seeds (12,172 ->
13,967). That is a portfolio-level far tail out of 20,000 years and is
inherently noisy; it is a published column but nothing in the premium
path reads it (premium uses `tvar99_euler`). I have NOT established
whether these changes made it more seed-sensitive than it was on main,
only that it is sensitive. Worth a look before anyone quotes it.

**Defect 5, found and NOT yet fixed — the reconciliation check that
should have caught defect 4 cannot.** `build_model.py`'s own check
prints `float(gdf["el_total"].mean())` — an UNWEIGHTED district mean —
against `ABI_LOSS_PER_POLICY`, a national per-policy figure, formatted
to ZERO decimal places, and `el_total` includes groundwater while
`ABI_LOSS_PER_POLICY` does not. Three mismatches at once. It reported
"-0%" while flood was 2.26% under its anchor. Its label also still says
"these four perils"; there are eight. Diagnostic only — no published
number reads it — but it is the guard that failed, so it should be
exposure-weighted, gw-excluded and printed to 2dp.

**Not done, deliberately.** The 103.3% claim-count overshoot is
untouched and still documented above: bundling a judgement-driven anchor
move with arithmetic fixes would make this run unattributable. Phase 2c
stays parked for the same reason.

**Also on this branch: the Phase 3 disclosure.** The same peril table
gains % of claim cost, and buildings/contents on the 57% of cost that
has a published anchor, with weather, escape of water and accidental
damage shown "unsplit" rather than given an invented number. Flood uses
the MCM convention (48/52), footnoted with Flood Re's 66/34 and the EA's
25/75 and why MCM is preferred — it is the only one of the three that
measures damage to the property. NO portfolio headline figure: the
honest bound is 31.8%-79.5% buildings, and a 43-point band is not a
headline.

**Publishing is the user's call and has NOT been given.** Remaining, in
order: fix defect 5, sector rebuild in the worktree, copy output across,
merge to main, rebuild with commit=true, verify live.

## Phase 2 status: 2a PUBLISHED 2026-08-18, 2c built and NOT published

Both experiment branches were built, verified and priced. The user chose
**"2a only"**: 2a is live (see the section above), 2c stays on its branch.

- **2a - theft commercial denominator** - **PUBLISHED, now on main**
  (`exp/theft-commercial`, eebb5c2+c22aa06; evidence run 32033558205): rate = burglaries /
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
- **They COLLIDE in prime London** (2a cut W1J, 2c raises it). 2a went
  first, so **2c's evidence run is now stale**: to revisit it, rebase
  `exp/ct-severity` onto published main, re-run the evidence (the churn
  numbers above are measured against the pre-2a baseline and will move),
  do the site copy pass for the severity prose, and take the OUTWARD D
  seam for ct_bands.csv on sector-model - premises.csv already has it
  (fetch_premises.py, 9e777f8: 9,700 sectors, 100.0% placed).
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
