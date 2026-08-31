# Handoff — UK Home Insurance Risk Map

**Written:** 2026-08-12, audited and refreshed 2026-08-16 · lives in the
repo (supersedes the old `%TEMP%\uk-risk-map-handoff.md`, which is now
just a pointer here)
**Repo:** https://github.com/SMcode-source/uk-home-insurance-risk-map ·
**Live:** https://smcode-source.github.io/uk-home-insurance-risk-map/

## Status: complete, deployed, EIGHT insured perils at TWO resolutions

**A new workstream opened 2026-08-27: temperature-driven subsidence and
freeze.** Five gates, agreed with the user after a full stress-test of
the plan: **(0)** acquire the ABI quarterly subsidence series and the
CEDA HadUK-Grid daily record, and measure what `theta_ws` costs, with
no model change; **(1)** the subsidence level alone, so the premium
move has exactly one cause; **(2)** geography — an SMD curve for
subsidence and a cold-spell/thaw index replacing air-frost days;
**(3)** structure — burst-pipe breakout, three non-water freeze
variants priced side by side, snowmelt; **(4)** a year-view conditional
claim count and value. The dependence re-specification is deliberately
its own later phase. **Every gate has now reported.** Gate 0 closed
(ABI series in, `theta_ws` costs GBP0.65, HadUK on disk). Gate 1
published 2026-08-28 (severity fix taken, level held at GBP307m, 0.6
pence). **Gate 2 measured 2026-08-30 — the freeze half closes as a
no-reorder, the SMD half is a real different map; section below.**
Gate 3 closed as a no-ship (no anchor, and sigma provably moves
nothing). Gate 4 measured (a bad year is dearer claims, not more
claims).

**All three decisions the workstream left to the user are now closed,
2026-08-31.** The SMD curve is PUBLISHED at both grains (`cwd_yr` at
`SUB_DROUGHT_SHARE = 0.565`, premium GBP169.6477). The freeze re-aim is
ANSWERED NO — measured, then priced anyway, and `EOW_FREEZE_SHARE`
stays 0.31 because the model is structurally blind to the frost level
and the map sits inside its own noise floor. Tab 4 SHIPPED as
`/temperature.html`. So the premium moved 0.8 pence across the whole
workstream, which is the honest headline: five gates of temperature
work found one real map (subsidence geography) and no level.

**What the workstream leaves open**, in its own sections below: the
frost SHARE is distributional and unanchored (0.17 pence across a 2x
range, but 353 districts re-rate — there is no UK per-era attribution
to settle it); the PET bias is level-not-map at both resolutions; and
the published climate scenario is flood-only, so it cannot show
subsidence worsening or escape of water easing. The dependence
re-specification was always a later phase and has not started.

**The HadUK archive state, 2026-08-30:** 12 km AND 5 km daily
tasmin/tasmax/rainfall 1960-2025 are complete on this laptop under
`data/haduk/` (gitignored); the 1 km set was streamed on CI and reduced
to `data/haduk_district_annual_1km.csv` without ever fitting anywhere
(174 GB, run 33319459184). Both per-district year tables — 5 km local,
1 km from CI — are complete, schema-identical and gitignored; the
scripts regenerate them. The CEDA token (secret `CEDA_TOKEN`, also
`~/.ceda_token`) **expires 2026-09-01 16:27 UTC and is being allowed to
lapse** — nothing planned needs it, and the four HadUK workflows say so
in their own headers. **This is an expiry, not a budget decision**: CEDA
is free and a renewal is one registration away, exactly like MIDAS Open
was, so if a future question needs the daily grids the answer is "get a
new token", not "we cannot afford it". The dead secret is harmless where
it is; delete it only if you want the settings page tidy. Daily data
ends **2025-12**, so the ABI's 2026 quarters
have no matching weather year. `snowLying` exists at 12 km and was Gate
3's snow driver before Gate 3 closed.

**The whole roadmap is now published, at both grains.** Phase 1
(attritional perils: theft → escape of water → fire → accidental
damage) completed 2026-08-17. Phase 2 is EPC/VOA exposure realism —
**2a (theft's residential denominator) live 2026-08-18**, **2c
(council-tax band severity relativities) live 2026-08-27**. **Phase 3
(the buildings/contents cover split) went live the same day.** Two
anchor corrections went live 2026-08-25: theft's paid total and the
escape-of-water freeze share.

**The budget is zero, decided 2026-08-31, and it is a standing rule
rather than a mood.** Nothing licensed, nothing paid-tier, nothing
needing a commercial agreement. DATA_SOURCES opens its blocked-data
section with what this closes permanently — PAF/AddressBase, BGS
superficial thickness — and, more usefully, what it does NOT close:
free-but-gated sources are still fair game, which is how MIDAS Open
went from "blocked" to carrying the gust component. Test any future
source on "does it cost money", never on "is it inconvenient". The
consequence for the model is that the assumed θ(s) copula forms, the
compound Bernoulli×LogNormal, `SUP_WEIGHT`'s 0.5 prior and
census-households exposure are permanent limits, not a backlog.

**Branches, trimmed 2026-08-31.** Only `main` and `sector-model` exist
now. The six merged experiment branches were deleted after checking
that nothing unique lived on them (what looked unique was pre-vector
-tiles leftovers — Leaflet assets and the GeoJSON that PMTiles
replaced — deliberately gone from main), and after lifting
`year_claim_view.py` and `price_eow_sigma.py` onto main, which were the
only real content stranded. `sector-model` is synced to main and stays;
it is never merged INTO main.

**Shipping is not the same as settling.** Two objections were stated,
overruled by the user, and remain open: council tax tracks MARKET value
while insurance pays REINSTATEMENT (Phase 2c), and three perils worth
42.5% of claim cost carry an unanchored split guess (Phase 3). Neither
is a defect to fix quietly — both are recorded decisions, in their own
sections below. Anyone revisiting the model should start there.

The site publishes the model at **two grains side by side**:
`/map.html` over 2,736 postcode districts and `/sectors.html` over
10,398 derived postcode sectors. One template builds both pages, so
they cannot drift; the layout suite runs every map invariant against
both. **86 tests** (two of which skip only while a publish is
mid-transition — see the theft section), CI green, Pages live. The
methodology page draws the Hull comparison as an inline SVG generated
from the published GeoJSON at build time — a screenshot would go stale
at the next rebuild; this cannot.

~~**Two defects are open and UNFIXED**~~ — **both were FIXED and
published 2026-08-19**, along with three more found while fixing them;
see "Built AND PUBLISHED 2026-08-19: five defects fixed" below. The
four vine perils now take their EL analytically and flood severity is
no longer blended in log space. Re-measure any marginal change with
`.venv/Scripts/python.exe scripts/analytic_el_check.py`.

Current headline figures (**2026-08-28 publish**, CI 33138216612 +
33138240678 verified): exposure-weighted premium **£169.66**
(169.6558) over 27.26m households; loss cost £164.12 ≈ 75% of the £219
all-home-claims cost. The last move was Gate 1's subsidence severity
fix, worth **−0.6 pence** and entirely capital — `el_total` is
bit-identical across it. Before that, the fall from £176.66 was theft's
level correction (−3.96%); the EoW freeze share moved geography only
and cost the level nothing. Climate
uplift is diluted a fourth time by AD's flat ~£14.65 (each attritional
peril dilutes these — same £ of repricing on a bigger base; the site
injects them, only this file and README carry them by hand).

## Gate 2 MEASURED 2026-08-30: freeze reorders nothing; the SMD curve is a real, different map

Run `scripts/gate2_geography_shape.py` (against either resolution's
table) and `scripts/compare_haduk_resolutions.py`. Data: the full 5 km
extraction locally (`haduk_district_daily.py`, 84 min, 66 years x 2,736
districts) and the full 1 km extraction on CI — four probe-sized slices
streaming 174 GB none of which ever touched a disk whole
(`.github/workflows/haduk-1km.yml`, run 33319459184, 4.5 h wall, every
slice green first try). Everything below was computed at BOTH
resolutions and agreed to the second decimal, which is the cleanest
possible answer to "was 1 km worth it": **1 km confirms 5 km rather
than changing it** — per-year cross-district rank agreement +0.97 to
+0.997 on every comparable column, and the districts 5 km genuinely
cannot separate number **14** (7 groups, mostly co-cell small urban
pairs), inside which 1 km spreads the drought indices by only 1-3%.
The old "84% of households share a 12 km cell / 40% a 5 km cell"
statistic measured CELL sharing, not value degeneracy — area-weighted
overlap already separates nearly every district.

**FREEZE HALF, CLOSED — a cold-spell/thaw index does not reorder the
map.** At all 2,736 districts, like-for-like on the same instrument and
window (5 km, 1991-2020): spells +0.993, days-in-spells +0.984,
worst-spell severity +0.971 Spearman against plain air-frost days; the
1 km table repeats them (+0.994/+0.985/+0.972). The ERA5 22-point
provisional answer holds at full coverage, now INCLUDING the Scottish
districts ERA5 could not see. A relativity that reorders nothing cannot
move a premium, so the swap buys no geography and the physical argument
(pipes burst on the thaw after a sustained freeze) is true but
priced-in by rank. Instrument agreement corroborates: the 5 km
1991-2020 frost climatology matches the model's 1 km HadUK layer at
+0.98, means 40.5 vs 40.0 days. What survives is the LEVEL question the
provisional section already posed — frost days fell ~20% between eras
while the map stayed +0.98 rank-stable — i.e. should `EOW_FREEZE_SHARE`
be time-varying at all. That is a re-aim for the user, not a geography
experiment.

**SUB HALF — the drought climatology is genuinely different geography,
unlike the freeze swap.** The model's subsidence surface is geology
alone (`p_sub = 0.002 + 0.028*sub_score^1.5`); no weather enters it.
Against that geology the drought climatologies correlate at rho ~ 0.69
— clay country and dry country overlap (both are the southeast) but are
far from one map. An `EOW_FREEZE_SHARE`-style blend
`p_sub * (1-share + share*rel)` at share 0.31 keeps rank rho ~ 0.987
yet moves **523** districts (JJA-mean SMD) to **1,284** (per-year peak
deficit) by more than 10% in subsidence frequency. Extremes are
physically right without being told: wettest-lowest all west Highlands
(PH50, PH43/44/49, HS3/5, IV54), driest-highest Thames estuary and
Bedfordshire/Cambridgeshire clay (DA8/9/17/18, RM17-20, SS0/4/8, MK42,
SE28). Nationally, the household-weighted per-year deficit
(`cwd_yr_max_mm`) recovers **5 of the 6 canonical subsidence years** in
its top ten — 1976, 1995, 2003, 2018, 2022, missing only 2006 — and
the JJA-mean SMD 4 of 6. The index family works.

**Which index: `cwd_yr_max_mm`.** The capped bucket (`smd_max_mm`)
saturates (94-96% of districts peg, spread 0.60-1.06); the uncapped
RUN integral (`cwd_run_max_mm`) carries multi-year memory that turns
its national top ten into 2016-2025 — a trend, not a year index (and
across CI slice restarts it is not even comparable; the workflow
header documents that). The per-year reset keeps the discrimination
(relativity p5/p95 = 0.33/1.41) without the ratchet.

**What blocked pricing — BOTH CLEARED BY MEASUREMENT 2026-08-31, see
the next section:**

- **The PET level is inflated ~a third** — Hargreaves-Samani gives UK
  annual PET 668-697 mm against a true 450-550 (known weakness in humid
  maritime climates, recorded at `haduk_district_daily.py`'s commit).
  Rankings are sound; the LEVEL is not shippable without MORECS/MOSES
  PET or a citable UK Hargreaves coefficient. A uniform bias does NOT
  cancel out of a deficit, because the deficit subtracts rainfall.
  *Cleared: measured to move the level only — the map survives.*
- **The share has no published anchor.** `EOW_FREEZE_SHARE = 0.31`
  cleared this hurdle with the ABI's own weather-attribution arithmetic
  agreeing across two releases (0.311/0.307). The subsidence equivalent
  — what fraction of subsidence frequency rides the drought curve
  rather than the geology base — has no such number yet. BGS/ABI both
  attribute the large majority of UK subsidence claims to clay
  shrink-swell, but "large majority" is not a parameter. Candidate
  routes: the ABI quarterly series' H2 concentration (78% of 2022
  notified claims in H2 is itself an attribution measurement), or a
  dose-response presentation like SUP_WEIGHT's.
  *Cleared: the ABI's own arithmetic yields 0.565 by two agreeing
  routes; priced at 0.40/0.565/0.70 so the table shows sensitivity.*

## PUBLISHED 2026-08-31 (second): the temperature tab, and the freeze re-aim answered

Two things the user asked for together ("do all of these"): the freeze
LEVEL question Gate 2 left open, and what the fourth content tab
publishes now that the workstream has reported.

**The freeze re-aim: do not re-aim.** `measure_frost_era.py` on the
66-year daily extraction. The decline is real and strongly significant
- **-0.326 days/yr, p=0.0002, -7.5% of the mean per decade**, 49.0 days
in 1961-1990 against 38.9 in 1991-2020 - and the model cannot feel any
of it, because `eow_rate` divides frost by its own exposure-weighted
mean and a proportional decline cancels exactly. So only the SHAPE and
the SHARE can price.

The shape was read against **within-era controls** - same climate,
different sample - because a shorter recent window is a noisier
estimate as well as a more current one, and without a control any
re-aimed window shows movement that looks like signal:

  candidate            |drel| p95     control (same n)
  1996-2025 [n=30]        0.045       0.158  (two 15y halves)
  2006-2025 [n=20]        0.091       0.158
  2016-2025 [n=10]        0.187       0.178  (two disjoint decades)
  1961-1990 [n=30]        0.185       0.158

Both windows worth considering are far inside the noise; the recent
decade only matches its own sample-size control; and the 1961-1990 map
- a genuinely different climate 30 years back - differs from today's by
no more than two arbitrary decades inside the published window differ
from each other. 1 km and 5 km agree to the third decimal.

**Then it was priced anyway, because a prediction is worth testing**
(CI run 33431160741, six variants, 23 min):

  variant           share   premium    d prem  capital   el_eow  churn
  baseline          0.310  169.6483    +0.00p   5.5270  42.3871      0
  share_200         0.200  169.6499    +0.16p   5.5285  42.3871    353
  share_266         0.266  169.6490    +0.07p   5.5277  42.3871    158
  share_400         0.400  169.6466    -0.17p   5.5253  42.3871    288
  daily_1991_2020   0.310  169.6484    +0.01p   5.5271  42.3871    168
  era_2006_2025     0.310  169.6482    -0.01p   5.5269  42.3871    220

el_eow identical to ONE ULP everywhere - the construction proving
itself. The era isolated against its own instrument control is **0.02
pence**. Nearly doubling the share moves the premium 0.17 pence but
moves 353 districts a rating group, +/-GBP15 at the extremes
(Inverness-shire and the frostiest districts down as the dial drops,
the Isles of Scilly up). **A distributional question wearing a pricing
question's clothes**, with no UK per-era attribution to settle it.
EOW_FREEZE_SHARE stays 0.31; LIMITATIONS section 4 records the gap.

**The trap, and it cost a whole run.** The first attempt (33427929182)
reported ~2 pence of movement and flagged el_eow drifting 5.4e-4. That
was the harness, not the model: build_model normalises the four
attritional council-tax severity multipliers with CLAIM weights
(households x that peril's OWN rate), so `ct_eow` is a function of
`eow_rate`. Overwrite eow_rate on an already-scored frame and the
severity normalisation left behind belongs to the old rate - the level
then drifts with the SHAPE of the relativity and reads exactly like a
priced effect. main() is correct and always was (it computes ct_eow
after eow_rate); only a harness can get this wrong. **Any future
harness that overwrites a `*_rate` column must renormalise that peril's
`ct_*` before calibrating.** The fix needs no fresh read of
ct_bands.csv - renormalising the frame's own column on the new weights
is exact, because the old constant cancels.

**The temperature tab is live** at `/temperature.html`, fifth content
tab, never titled "prediction" and saying so in its opening line. Two
server-rendered charts (household-weighted national series, 1960-2025)
from `data/temperature_series.json`. Drought +3.6%/decade (p=0.036)
with 5 of 6 canonical surges in the index's own top ten; frost
-7.5%/decade with the blindness explained rather than hidden; Gate 4's
"a bad year is dearer claims, not more claims"; and a limits section
saying the climate scenario is flood-only, so it cannot show subsidence
worsening or escape of water easing.

**"Every figure injected, none typed" is what this entry said, and it
was false in the one section that most needed it.** The bad-year
section carried TEN hand-typed numbers - 1.38x count, 2.63x value, the
1.25x/2.11x shift-share, the storm and flood shares and their per-peril
ratios - directly under a `temperature_bits()` docstring citing defect
3 as the reason nothing is ever typed. They were measured before Gate 2
and every one had drifted by publication: count 1.38 -> 1.36, value
2.63 -> 2.67, mix 1.25 -> 1.24, within 2.11 -> 2.15, flood 2.18/2.83 ->
2.13/2.88. The page was quoting a model that no longer existed, which
is defect 3 exactly, on the page whose own comment warns about it.

Fixed by injection, and without a simulation: the committed
`data/year_analysis.json` buckets already carry UNROUNDED
`claims_*_per_100k` and `cost_*_per_claim` - `year_claim_view.py` added
those columns precisely because the rounded `inc_*_pct` ones cannot
support the division - so `temperature_bits()` recomputes the whole
decomposition from committed data at build time. The shift-share holds
each peril's typical cost per claim fixed and moves only the mix; mix x
within multiplies back to the total exactly (1.2435 x 2.1477 = 2.6707),
which is what makes quoting both honest rather than one number twice.
The prose survived the new figures unchanged in meaning - storm still
nearly flat, flood still the engine.

`year_claim_view.py` (Gate 4) and `price_eow_sigma.py` (Gate 3) were
brought onto main in the same commit. Both lived ONLY on unmerged
experiment branches far behind main, so a published claim and a
recorded no-ship had their provenance sitting on branches a cleanup
would have deleted.

**Then the whole site was swept for the same defect, and the same page
had three more.** A scan of every template for typed model outputs
found `£169.66` written into the drought section - the PRE-Gate-2
premium, when the published figure is 169.6477, so the page rounded to
a penny the model no longer charges - plus `43.5%`/`56.5%` restating
`SUB_DROUGHT_SHARE` and `31%` restating `EOW_FREEZE_SHARE`. All three
now inject, the two shares straight from `build_model` by the local
-import idiom the file already uses elsewhere. A new `__PREM_MEAN__`
lives in `load_stats()` beside `__PREM_MIN__`/`__PREM_MAX__`,
household-weighted to two decimals, because this project routinely
reports sub-penny results and rounding to the pound would hide the
differences the gates exist to measure.

The sentence around it had to change too: it read "the headline premium
stayed at GBP169.66", and Gate 2 moved it 0.8 pence. Injection alone
would have produced "stayed at GBP169.65" - true numbers inside a false
claim. It now reads "moved by less than a penny, to GBP169.65". **A
placeholder does not make a sentence honest; the prose around it has to
survive the substitution.**

Everything else the scan flagged in `methodology.template.html` is a
SOURCE constant - ABI shares, VOA counts, published anchors - which is
prose about the world rather than output of the model, and is correctly
typed.

**The last asymmetry closed too, and closing it caught a fourteenth
wrong number.** sub-level, eow-sigma and freeze-share had each
committed a pricing JSON; the SMD curve had not, so its churn was
quoted from run 33410640013 with no artifact behind it. That run's
artifact had not expired, so it is now `data/smd_curve_pricing.json`
and the churn injects. `build_site` looks the row up by the SHIPPED
index and share - `cwd_yr` at `SUB_DROUGHT_SHARE` - not by variant key,
and raises unless exactly one priced variant matches, so re-tuning the
share cannot leave the page quietly describing a variant the model no
longer runs.

Wiring it exposed the error. The page read "455 districts moved one
rating group, one moved two", and `price_smd_curve.py` defines
`churn` as ANY group change and `churn2` as `|delta| >= 2` - a SUBSET,
not a separate population. The old sentence implied 456 movers; the
truth is 455, one of which moved two. It now reads "455 of 2,736
districts changed rating group, 1 of them by two". HANDOFF's own Gate 2
churn line said the same thing loosely and has been made explicit; the
prose at "This is a pure geography change" was already correct.

Two guards were widened rather than worked around.
`test_site_placeholders_all_resolve` scanned a **hard-coded pair** of
templates, so all 23 of the new page's placeholders read as "defined but
unused" - the guard could not see the page it guards. It now enumerates
`site/*.template.html` with a count assertion. `test_layout` gained the
page in both its page list and its SVG readable-size list; that second
one is what proves the wide/narrow chart swap actually defeats the
3.4px bug. 42 layout tests green including phone viewports, 67 model
tests green.

**Then the publish push went red, and the stale-intermediate trap at
"docs/ was stale and the local check said fresh" below had bitten a
second time - worse than the first.** I ran `build_site.py` alone to
add the nav link. It re-wrapped `analysis/uk_risk_year_analysis.html`
and `map/*.html`, gitignored intermediates my checkout had left at
their PRE-Gate-2 state, so commit 5b56296 silently REVERTED four
committed pages - map, relative, sectors, years - to the subsidence
numbers the SMD curve had just replaced (`claims_sub_per_100k` 72.6
back to 72.83, and the exceedance curves with it). Re-wrapping a stale
intermediate does not merely fail to update a page; **it overwrites a
correct page with old output, and the diff it produces looks like an
ordinary one-line nav change.** Nothing local objected: 67 tests and 42
layout tests passed on the reverted docs, because no test compares
docs/ against the committed data - only CI's freshness step does, and
that is what caught it. Fixed by running the full chain and committing
the result, which is reproducible across two passes; the four pages now
differ from 6f323aa by exactly the one nav line they were supposed to.

**The live site was never wrong, and it is worth being precise about
why**, because the reason is also the reason nobody would have noticed.
`pages.yml` deploys a build ARTIFACT it constructs from `data/` and
`site/`; it never serves `docs/`. It also did not run on either push -
its path filter covers data, templates and `scripts/build_*.py`, and a
docs-only commit matches none of them. So the reverted numbers sat in
the repository while `smcode-source.github.io` kept serving 72.6
throughout (checked). `docs/` is the fallback the workflow header
describes - what Pages serves if the repository's Pages source is ever
set back to a branch - plus the reviewable record of what the site
says. A stale one is a live-site regression armed but not fired.

So the rule below is not a tidiness preference: **never commit docs/
built by `build_site.py` alone. Run `build_map.py`, `build_tiles.py`,
`build_analysis.py`, `build_site.py`, in that order, every time.** The
intermediates are gitignored, so a fresh clone cannot reproduce this -
only a long-lived checkout like this one can, which is exactly why it
recurs here and not in CI.

## PUBLISHED 2026-08-31: the Gate 2 SMD curve, both grains in one push

The user chose option 1 of the priced menu: ship `cwd_yr` at
`SUB_DROUGHT_SHARE = 0.565`. What went live, all numbers from rebuilds
rather than the harness (its baseline level sits 7e-6 high; see the
Gate 1 publish note):

  el_sub     19.805475 -> 19.807342  +0.009%: calibrate_frequency
             re-pins the level (harness drift <= 1 ULP); the residue
             is the geojson's per-district rounding under reshuffled
             weights
  el_total   164.120266 -> 164.121733  +0.0009%
  capital    5.533736 -> 5.526963   -0.122%
  premium    169.655786 -> 169.647739  -0.8 pence (harness said
             169.6483 - the gap is the geojson's 1dp premium write)
  sectors    169.6636    cross-grain drift +0.0094% (bound 0.5%)
  nesting    median |sector-mean/district - 1| 1.16% (bound 3%), p95 6.6%
  sub_rel    wmean exactly 1.000000 both grains; district 0.538-1.310,
             sector 0.537-1.307
  churn      455 of 2,736 districts change rating group, 1 of them by
             two (churn2 is a SUBSET of churn, not an addition to it)
  movers     up DA15/DA6/SE23 (+GBP8-13), down CF61/CF62/LL44

Wiring is the eow_rate pattern exactly: `drought_from_haduk` loads
`data/smd_climatology.csv` with exact name coverage (wrong grain =
SystemExit), `sub_rel` is normalised on the live frame in main() and is
a REQUIRED `_fields` column — a frame without it fails loudly rather
than silently pricing geology-only (commit 8a8727e; test
`test_sub_frequency_carries_the_drought_relativity`).

The sector grain surfaced one real defect: 13 sectors came back NaN —
exactly the 13 empty-geometry polygons (no centroid -> NaN latitude ->
NaN Hargreaves Ra -> NaN PET; their daily met had silently come from an
arbitrary fallback cell, so the whole row was untrustworthy). Each now
takes its parent district's climatology via
`make_smd_climatology.py --fill-empty-from`, printed per sector
(children.csv posture). Two more features LOOK empty in
sectors_risk.geojson but are GeometryCollections (IV51 9, ZE2 9) and
extracted fine. Coherence after the fill: Spearman +0.9964,
median rel diff 0.000 (commit c0596e8, DATA_SOURCES #34).

Assembly followed the one-push procedure: sector-model got exp/smd-curve
merged IN plus the sector-keyed climatology, `sector-model.yml
skip_fetch=true` built on CI (run 33422250428 -> commit c8fac97), the
output was crossed in as data/sectors_risk.geojson (fd97f77), and
rebuild.yml commit=false re-rendered EVERYTHING on CI (run 33424274229)
so docs carry both grains — the district geojson came back bit-identical
to the previous verified rebuild (33418764800), which is the determinism
check working. One trap for next time: actions/upload-artifact@v4 drops
hidden files by default, so the artifact's docs/ was missing .nojekyll —
restore it before committing or Pages breaks.

## Gate 2 PRICED 2026-08-31: the SMD curve costs the level nothing and re-rates modestly — the user shipped it (see PUBLISHED above)

Branch `exp/smd-curve` (commit 9d0a917, CI run 33410640013; artifact
`smd-curve-pricing`, JSON also at `data/smd_curve_pricing.json` in the
run). Seven full 20,000-year simulations off one scored frame:
baseline + {cwd_yr, smd_jja} x shares {0.40, 0.565, 0.70}, the Gate 1
harness pattern. The lever is `sub_rel` — a per-district frequency
relativity on `p_sub`, exposure-weighted mean 1, normalised on the
live frame like `eow_rate`; the column is absent from the real
pipeline and provably bit-neutral when missing; dependence still reads
`sub_score`.

**The two blockers were closed with numbers first:**

- **PET (measured, both resolutions):** `check_pet_sensitivity.py`
  re-ran the drought integrals at PET x 0.85 and x 0.70 — at 1 km on
  CI (workflow `haduk-1km-pet.yml`, run 33404395072, re-extracting
  only 1991-2020 = 81 GB in the four probe-calibrated slices, done
  ~1 h; branch `exp/haduk-1km-pet`) and at 5 km locally
  (`haduk_district_daily.py --pet-sensitivity`, 70 min). Verdict
  identical at both: the bias moves the LEVEL (cwd_yr climatology
  240 -> 121 mm at x 0.70) and NOT the MAP — Spearman vs k=1.00 at or
  above +0.9983 (cwd_yr) and +0.9940 (smd_jja) everywhere. The level
  is exactly what calibration re-pins, so the priced relativity
  survives the PET formula. If a shipped leg ever needs the level's
  physics, the citable fix is Hydro-PE (PM PET on this same HadUK-Grid
  met, 1 km daily 1969-2021, CC-BY,
  doi:10.5285/9275ab7e-6e93-42bc-8e72-59c98d409deb). Run before the
  CEDA token expired 2026-09-01 16:27 UTC; nothing planned needs CEDA
  now.
- **Share (derived, not guessed): 0.565 from the ABI's own releases**
  by two agreeing routes — the 2018-12 release's 2,500 claims/quarter
  pre-surge baseline (=> 10,000/yr) against 2022's 23,000 total with
  13,000 drought-attributed (=> 13/23 = 0.565), cross-consistent with
  2022's own H1 of 5,000 = base/2. Zurich's attribution (60% of upheld
  claims root-induced clay shrinkage in an average year, ~85% in a
  surge year) brackets it. Same derivation style as
  `EOW_FREEZE_SHARE`'s 0.311/0.307.

**The table (exposure-weighted GBP/policy; churn = districts changing
premium decile vs baseline; el_sub pinned at 19.8065 in every variant,
drift at most one ULP):**

| variant      | share | capital | premium  | vs base | churn | >=2 grp |
|--------------|-------|---------|----------|---------|-------|---------|
| baseline     | —     | 5.5337  | 169.6551 | —       | 0     | 0       |
| cwd_yr 0.40  | 0.400 | 5.5290  | 169.6504 | -0.003% | 336   | 0       |
| cwd_yr 0.565 | 0.565 | 5.5270  | 169.6483 | -0.004% | 455   | 1       |
| cwd_yr 0.70  | 0.700 | 5.5252  | 169.6466 | -0.005% | 547   | 1       |
| smd_jja 0.40 | 0.400 | 5.5310  | 169.6524 | -0.002% | 234   | 0       |
| smd_jja 0.565| 0.565 | 5.5298  | 169.6512 | -0.002% | 330   | 0       |
| smd_jja 0.70 | 0.700 | 5.5288  | 169.6502 | -0.003% | 386   | 0       |

Top movers, every variant: UP the Thames-estuary/Essex clay (cwd_yr:
DA15/DA6/SE23 +GBP8-13; smd_jja: SS12/SE23/SS13 +GBP4-6), DOWN wet
western coasts (CF61/CF62/LL44 and LL43/IV48, -GBP4-10). The same
districts Gate 2's shape measurement called out in advance.

**Reading it honestly:** the level cannot move by construction and did
not (drift <= 7.1e-15); the tiny premium dips are capital reallocating
as frequency shifts toward districts whose tail contribution differs.
This is a pure geography change: at the anchor share 0.565 with the
better index (cwd_yr — 5/6 canonical years), 455 of 2,736 districts
change decile, exactly ONE by two or more groups. Compare Phase 2c
(70.5% churn, 974 districts >= 2 groups, held) and the MIDAS gust swap
(28.8%, 20 districts >= 2, published): this sits far below both. The
open decisions are the user's: ship cwd_yr at 0.565 (with the PET
verdict and the share derivation as the published justification),
present the dose-response, or record it as a priced refusal for
Tab 4 — the harness, evidence and derivations are all on the branch
either way.

Two streamer defects fixed before the CI run (commit on
`exp/haduk-1km-ci`): `append_csv` wrote every year's rows TWICE (came
in with the memory-fix rewrite; the local 1960-62 CSV predates it and
was checked clean), and the progress line called
`shutil.disk_usage('C:/')`, which would have thrown FileNotFoundError
on the first completed year of any Linux run.

## Gate 0 CEDA strand CLOSED 2026-08-29: HadUK-Grid daily is on disk

The token was regenerated by the account holder and the fetch ran clean:
**2,376 files, 1,508 MB** under `data/haduk` (gitignored) - tasmin,
tasmax and rainfall at 12 km, 792 files each, **66 complete years
1960-2025, no gaps**, release v20260512 of v1.3.2.ceda. Verified by
opening three files with xarray rather than trusting the fetcher's
magic-byte check: 112x82 grid, correct units, physical ranges.

That retires the last blocker on Gate 0 and gives Gate 2 the source ERA5
could not provide - ERA5 was unusable for frost in Scotland, and the
model's existing frost/rain layers are 1991-2020 CLIMATOLOGIES with no
year-to-year variation at all.

**The subsidence signal is present, and it discriminates.** UK-land-mean
JJA rainfall, 1960-2025, median 245 mm (matches the published figure;
driest 107 mm in 1995, wettest 380 mm in 2012):

| driest JJA | mm | % of median | mean summer tasmax |
|---|---|---|---|
| 1995 | 107 | 43.6% | 20.7 C |
| 1976 | 108 | 44.0% | 21.1 C |
| 1983 | 128 | 52.3% | 20.1 C |
| 1984 | 146 | 59.5% | 19.6 C |
| 2022 | 164 | 66.8% | 20.5 C |
| 2018 | 174 | 70.9% | 20.6 C |

1976 and 1995 are the two driest summers AND the two warmest - the two
canonical UK subsidence catastrophe years, recovered from the data
without being told to look for them. 1975 also makes the driest ten,
which is the consecutive-summer desiccation that made 1976 so severe.
2018 and 2022, the modern surge years, are both there.

**Two counter-cases matter more than the hits**, because they are why
the leg must be built on PET/SMD and not a temperature index: **2023**
is the 10th warmest summer at **118% of median rainfall** (warm and wet
- should produce no subsidence), and **1981** is in the driest ten at
the coolest tasmax of that group, 17.6 C. Neither variable alone
separates a subsidence year from a non-subsidence one. That is the
empirical case for Hargreaves-Samani PET off the daily tasmax-tasmin
range, which is precisely what this download makes possible.

METHOD NOTE, because I got it wrong once. The first pass computed
`a.sum("time").mean()`, which turns the NaN sea mask into zeros and
dilutes the spatial mean by ocean - it reported a median of 46 mm
against a true 245 mm. Rankings and ratios were unaffected (the land
mask is identical every year, so the dilution factor cancels) and came
out bit-identical on the corrected run, but the LEVEL was wrong. Take
the spatial mean first, then sum over time.

Token expires 2026-09-01 16:27 UTC. The 5 km per-district relativity
pass is ~14x the volume per file and was NOT taken - 12 km is what Gate
2 needs, and 5 km should earn its place before a fresh token is spent
on it.

## Gate 4 MEASURED 2026-08-29: a bad year is dearer claims, not more claims

`exp/year-claim-view`, CI run 33258862898, one 20,000-year simulation off
one scored frame. `year_analysis` now emits `claims_<peril>_per_100k` and
`cost_<peril>_per_claim` per bucket, from the UNROUNDED arrays, alongside
the `mean_*`/`inc_*_pct` it already published. The four vine perils, as a
multiple of the typical year:

| bucket | claims/yr | count x | GBP/claim | value x | cost/policy |
|---|---|---|---|---|---|
| good | 102,636 | 0.70x | 4,235 | 0.58x | £28.00 |
| typical | 147,112 | 1.00x | 7,357 | 1.00x | £69.80 |
| bad | 186,856 | 1.27x | 11,399 | 1.55x | £137.40 |
| catastrophic | 203,673 | 1.38x | 19,352 | 2.63x | £254.30 |

**Value beats count roughly two to one.** A catastrophic year costs 3.64x
a typical one, and 2.63 of that is the size of the average claim against
1.38 from the number of them. Count also saturates — 1.27x to 1.38x from
bad to catastrophic — while value keeps climbing, 1.55x to 2.63x. The
identity holds: count x times value x reproduces the cost ratio to within
0.12% in every bucket, which is the arithmetic check the harness prints.

**The value effect is itself two effects, and the smaller one is mix.**
Holding every peril at its typical-year cost per claim and moving only
the claim MIX to each bucket's:

| bucket | value x | of which mix | of which severity |
|---|---|---|---|
| good | 0.58x | 0.79x | 0.73x |
| bad | 1.55x | 1.13x | 1.37x |
| catastrophic | 2.63x | 1.25x | 2.11x |

Storm falls from 74.7% of claims in a typical year to 66.2% in a
catastrophic one while flood rises 9.2% -> 14.4% and subsidence
15.3% -> 18.2%, so cheap claims give way to dear ones. That is worth
1.25x. The remaining 2.11x is genuine severity inside the perils.

**Storm is not what makes a bad year bad.** It is two thirds to four
fifths of all claims and is nearly flat in both dimensions — 1.23x count
and 1.06x value at catastrophic. Flood is the engine: 2.18x count AND
2.83x value, compounding to 6.2x its typical cost per policy (£24.10 ->
£148.70). Subsidence is second, 1.65x by 1.84x.

Two caveats, both real:

- **Groundwater's value multiplier is non-monotonic** — 1.34x at bad,
  1.20x at catastrophic. It is the smallest leg by far (1.1% of claims,
  ~2,300 a year) and so the noisiest; do not read a story into that
  reversal without more simulated years. It is also exactly the leg the
  rounding floor below made unreadable.
- **This is the four vine perils only**, £56.90 of the £164.12 EL. The
  four attritional legs (theft, EoW, fire, AD) are outside the year view
  by design, disclosed and reasoned at `analysis/template.html:86`. So
  this answers why a bad WEATHER-AND-GEOLOGY year is expensive, not why
  a bad year for the book is. Sanity check against the ABI's 2025
  actual — 560,000 home claims across all perils — holds: 147,112
  typical and 203,673 catastrophic for a subset of perils both come in
  under it.

**Why the fields had to be added rather than derived.** `inc_<peril>_pct`
publishes at 2 dp of a PERCENT, smallest step 0.01% — about 1,550 claims
across a 15.5m book. Dividing `mean_*` by it to recover a cost per claim
inherits 0.6–0.9% error on weather, 2.6–12.5% on flood, 2.1–7.1% on
subsidence and **25–50% on groundwater**, whose incidence rounds to
0.00/0.01/0.01/0.02 across the four buckets. That is a resolution floor,
not sampling noise: more simulated years would not have moved it.

`test_year_view_claim_count_and_value` guards the identity
`mean_<peril> == claims_<peril>_per_100k / 1e5 * cost_<peril>_per_claim`
and was checked to bite — it fails when the conditioning divide is
removed. Counts are CLAIMS, not claimants: a policy claiming on two
perils counts twice, which is the basis the ABI's own figure uses.

Committed to main as 6a0db2a and **inert** — `build_model` is not in
tests.yml's docs-freshness path (only build_map/build_analysis/build_site
run there), so `data/` and `docs/` are untouched until someone rebuilds.
Nothing here changes the premium. Publishing any of it is the user's
call; the numbers above are quotable, the site does not yet show them.

## Gate 3 PRICED 2026-08-28: the answer is exactly zero, and provably

`exp/eow-sigma`, CI run 33217184873, four full 20,000-year simulations
off one scored frame: `SEV_SIGMA["eow"]` at **0.96 / 1.00 / 1.20 /
1.41**, spanning both ABI readings.

| sigma | EL | tvar99_euler | capital | premium | churn |
|---|---|---|---|---|---|
| 1.00 | 164.121341 | 256.3502754466515 | 5.533736 | 169.655077 | — |
| 0.96 | 164.121341 | **256.3502754466515** | 5.533736 | 169.655077 | 0 |
| 1.20 | 164.121341 | **256.3502754466515** | 5.533736 | 169.655077 | 0 |
| 1.41 | 164.121341 | **256.3502754466515** | 5.533736 | 169.655077 | 0 |

`tvar99_euler` is identical **to the last bit** in all four. That is not
a broken harness — sigma demonstrably reached the model, because
`el_eow` wobbles by 2.8e-14, exactly the ULP signature of the
`M / exp(s^2/2) * exp(s^2/2)` round trip. It is the right answer.

**Why.** Both places the premium comes from take the severity's MEAN and
nothing else:

    simulate()        el_eow = p_eow * exp(mu + s^2/2)
    cond_expected()   q * exp(mu + s^2/2)   -> year_loss -> tvar99_euler
                                            -> capital -> premium

and `mu = log(_median_for_mean(M, s)) = log(M) - s^2/2`, so
`exp(mu + s^2/2) == M` and **sigma cancels in both**, exactly, per
district. I had checked the first identity and assumed the second did
not hold. It does.

**This is deliberate and it is already on the published page** — the
methodology's "Averaging expectations, not accidents" gives the formula
as `Phi(...) x E[severity_i]`. Averaging REALISED losses over the worst
200 of 20,000 years made the Euler allocation correlate **0.49** with
itself across seeds; conditioning on the systemic draw took it to
**0.9985**. The price of that fix, never stated until now, is that
**capital responds to frequency CLUSTERING and never to severity
DISPERSION**.

**So the whole `SEV_SIGMA` table is invisible to the premium** — not
just EoW's. It reaches only `tvar99_vine`, `tvar99_indep` and
`var995_*`, which are diagnostics. That is now written at the
definition site in `build_model.py` and guarded by
`test_severity_sigma_cannot_move_capital`, so the next person does not
spend a CI run rediscovering it.

**What this does and does not settle.** Gate 3 is closed: neither the
burst-pipe leg (no anchor, and no geography for one) nor the sigma
variant (no effect, provably) can ship. It does NOT say severity
dispersion is irrelevant to a home insurer — it says THIS model does not
charge for it, by a choice made for seed stability. If that should
change, the test named above is the one to change, and changing it means
re-opening the 0.49-vs-0.9985 result.

**Process note, since it cost a CI run.** The answer was derivable by
reading `cond_expected` before launching anything. I verified the EL
identity analytically and took the capital path on trust. The run was
not wasted — it is the evidence behind the guard — but it should have
been a confirmation, not a discovery.

## Gate 3 prep 2026-08-28: the burst-pipe breakout has NO shippable anchor

Gate 3 proposes splitting burst pipes out of the escape-of-water leg as
its own peril. Desk research on the ABI's public releases, all figures
now in `data/abi_annual.csv` with their bases kept apart. **Verdict: do
not build the leg.** The reasons are worth keeping, because two of them
are findings in their own right.

**There are THREE ABI series here and they are not the same thing.**

1. *The annual weather line* (the release the model's storm/flood/
   subsidence anchors come from). Its home-weather total less storm less
   flood gives **153 (2023), 174 (2024), 202 (2025)**. The residual
   method is validated: for 2023 it reproduces the published GBP153m to
   within 1 (573-133-286 = 154).
2. *The winter-advice releases*, a **settled-claims** basis: 2023
   **12,000 claims averaging over GBP17,000**; 2024 **~8,000 claims,
   ~GBP33,000, GBP250m total**.
3. The model's own EoW anchor, GBP657m from the ABI's "GBP1.8m a day".

Series 1 and 2 do not reconcile: 12,000 x 17,000 = **GBP204m vs the
weather line's GBP153m (+33%)**, and 8,000 x 33,000 = GBP264m (the ABI
says GBP250m) **vs GBP174m (+44%)**. Same peril, same year, two ABI
publications, a third apart. This is the paid-vs-notified problem Gate 1
hit, in a new place.

**Finding 1: the 2025 "burst pipes" figure is not burst pipes.** The
2026-02 release's footnote says the weather figures "cover damage caused
by burst or frozen pipes, **escape of water**, as well as damage as a
result from storms and flooding". So the GBP202m residual is burst pipes
*and* weather-attributed escape of water. The likeliest reading is that
the **basis is the same in both years** and the 2023 release's "burst
pipes" label for its own residual was simply loose — and the evidence
for that is `EOW_FREEZE_SHARE`'s own derivation, which got **0.311 from
2023 and 0.307 from 2025**. Two different bases would not agree to
0.004. So this does not undermine `EOW_FREEZE_SHARE = 0.31`; if anything
it explains why it held up.

**Finding 2, and this is the useful one: the burst-pipe tail is already
representable inside the existing EoW lognormal, and the model's sigma
now has a published cross-check for the first time.** Split at the 2024
figures, burst pipes would be **4.9% of EoW claims but 40% of EoW paid**
— a 13x severity ratio. That sounds like it needs its own leg. It does
not. Asking what lognormal sigma puts that much value in that few claims:

| ABI reading | claims | avg | % of EoW count | % of EoW paid | implied sigma |
|---|---|---|---|---|---|
| 2023 (12k x >GBP17,000) | 12,000 | 17,000 | 7.3% | 31.1% | **0.96** |
| 2024 (8k x ~GBP33,000) | 8,000 | 33,000 | 4.9% | 40.2% | **1.41** |
| the model today | — | — | — | — | **1.00** |

`SEV_SIGMA["eow"] = 1.00` was a judgement call and has never had an
anchor. It now has one, and the anchor is a **lower bound**: the ABI
says the 2023 average *exceeded* GBP17,000, so the sigma that reading
implies is **at least 0.96**, not equal to it. The model's 1.00 is
therefore consistent with 2023 rather than confirmed by it — but
"consistent with a published figure" is strictly more than this
parameter had yesterday, and the bound rules out the low end.

**Why the leg still cannot ship.** Two observations, and they disagree by
47% on sigma. The average claim nearly **doubled** (17,000 -> 33,000)
while the count fell **a third** (12,000 -> 8,000) — the signature of a
small catastrophe-driven book, not a severity anchor. And the 2024 pair
could not be verified against the ABI primary: the cold-weather page
404s on fetch and only secondary reports carry it. Under the house rule
that a parameter without a published anchor does not ship, this is not
close.

**Sigma is not a clean substitute for the leg, and saying so needs a
correction to the paragraph above.** In the model, frost enters escape
of water through **frequency only** — `eow_rate` is the anchor level
times the frost relativity — while EoW severity is
`ABI["sev_eow"] * ct_eow`, a council-tax factor, with **one sigma
everywhere**. So a cold district gets more EoW claims at the same
average cost. Raising sigma would add cost concentration **uniformly**;
a real burst-pipe leg would tie it to frost geography. Those are
different models, and the ABI publishes **no geography at all** for
burst pipes — so the leg is unanchored in a second, independent way, not
just on severity. That strengthens the verdict rather than weakening it,
but the sigma option is a different question, not a cheaper version of
the same one.

**And it is a pure capital question — WRONG, and the CI run says so.**
I wrote here that sigma leaves EL unchanged and "only the tail, and
hence capital, moves", bounded by the GBP5.53 capital charge. The bound
is not a fraction of GBP5.53. **It is zero.** See the section below.

**What would change the answer.** A third year on the winter-advice
basis, which arrives each winter; or an ABI release that states burst
pipes and escape of water separately on the same basis; or any public
source for burst-pipe **geography**, which is the gap nothing here
fills. Until then the honest Gate 3 experiment is **not** a new leg but
the one-parameter question — is `SEV_SIGMA["eow"]` right at 1.00, given
2023 implies at least 0.96 and 2024 implies 1.41 — and that is
priceable today with the existing harness, on CI rather than this
laptop.

## Gate 2 shape check 2026-08-28 (PROVISIONAL, 22 of 57 points — superseded by "Gate 2 MEASURED 2026-08-30" above)

Run `scripts/freeze_index_shape.py`. It works off whatever
`fetch_era5_daily.py` has cached, which is what that fetcher's
farthest-point traversal is for — every prefix is a national sample. At
**22 points** it already answers two of Gate 2's three questions, and
the answers point somewhere other than where the gate was aimed.

**Q1: a cold-spell/thaw index does not reorder the map.** Spearman
against the `frost_days` the model uses today:

| index | rho vs frost_days |
|---|---|
| spells (>=3 consecutive frost days) | **+0.994** |
| days inside those spells | **+0.992** |
| freeze-degree-days inside them | **+0.990** |
| thaw events | **+0.994** |
| mean thaw jump (degC) | +0.772 |

Foreseeable in hindsight — every one of these is a monotone function of
"how cold is it here" — but it is now measured rather than assumed. The
physical argument for the swap (pipes burst when a SUSTAINED freeze
THAWS, not on days the air dipped below zero) is sound and still buys
**no spatial differentiation**. A relativity that reorders nothing
cannot move a premium. Only `thaw_jump` is a genuinely different
ranking, and it is the weakest-motivated of the six.

**Q2: the level is moving; the map is not.** 1960-1992 vs 1993-2025,
frost days **36.3 -> 29.2 (-19.6%)** and sustained spells **4.06 -> 3.44
(-15.2%)** — but rank correlation between the two eras is **+0.98**.
Britain is getting uniformly less frosty, not differently frosty.

**So Gate 2's freeze half looks like a LEVEL question, not a geography
question** — whether `EOW_FREEZE_SHARE` (the freeze-sensitive slice of
escape of water) should be time-varying at all, rather than which
districts carry it. That is a different experiment from the one the gate
describes, and it is the user's call whether to re-aim it.

**Q3, and this one changes what the ERA5 fetch is worth. ERA5 is not a
usable freeze instrument in Scotland.** Against the model's HadUK-Grid
1 km layer, both restricted to 1991-2020:

| | n | ERA5 | HadUK | bias | Pearson | mean abs diff |
|---|---|---|---|---|---|---|
| England & Wales | 8 | 25.7 | 33.1 | -22% | **+0.902** | 7.8 d |
| Scotland | 14 | 30.8 | 53.5 | -42% | **+0.547** | **32.9 d** |

The two largest errors have **opposite signs** — IV4 -68 days, PH33
(Lochaber) **+68** — which is the signature of a ~31 km cell landing on
the wrong terrain rather than a bias anything could correct. The
islands and far-north coastal districts (KW1/KW14/KW17, ZE1/ZE3, PA42,
IV51) are all strongly negative, as a cell that is mostly sea should be.

Consequences:

- **CEDA HadUK-Grid is not a nice-to-have for Gate 2, it is the only
  viable source.** ERA5 cannot cross-check freeze where freeze exposure
  is highest.
- The ~35 remaining ERA5 points (about a week of grinding) buy a decent
  cross-check for England & Wales and little for the Highlands and
  islands. Worth finishing, not worth waiting on.
- This is **not** evidence the model's frost layer is wrong. It is
  evidence ERA5 point-sampling is the wrong instrument for it — which is
  the reason `fetch_haduk.py` exists.

**Read the sample honestly.** 14 of the 22 points are Scottish, because
farthest-point traversal maximises geographic spread and the north is
sparse. The all-points "-37%" therefore overstates the
population-weighted error. Re-run at 57 before quoting any of this as
settled; Q1's +0.99 is the one number unlikely to move.

## PUBLISHED 2026-08-28: Gate 1's severity fix, both grains in one push

**User decision: "take the severity fix and hold the level at 307."**
`sev_subsidence` 17,820 -> **17,264**; `subsidence_paid` stays at the
published FY2025 GBP307m. Districts from CI **33138216612**, sectors
from **33138240678**, assembled and landed together.

| | published before | now | change |
| --- | --- | --- | --- |
| `el_total` | 164.120266 | 164.120266 | **bit-identical** |
| `capital` | 5.540486 | 5.533736 | -0.122% |
| `premium` | 169.661936 | **169.655786** | **-0.6 pence** (-0.0036%) |
| buildings / contents | — | 113.29 / 56.36 | — |
| sector premium | — | 169.6704 | drift **0.0086%** vs districts |

**2 districts of 2,736 change rating group; none moves two.** The
headline stays **GBP169.66** at 2dp, which is the honest way to say
that this correction removes a documented period mismatch without
moving the price.

**The full rebuild confirmed the identity that was argued from the
algebra.** `el_total` came back **bit-identical district by district**
to the file it replaced — a copula-free way of saying the same thing
the Gate 1 derivation said: `sev` cancels out of
`p_sub(i)*paid/(POLICIES*raw)`, so the whole 0.6 pence is capital.

**One caveat on the pricing harness — DIAGNOSED 2026-08-28, it is
output rounding, not an error.** `price_sub_level.py` predicted capital
5.533736 and the real rebuild delivered **5.533736**, exact to six
decimals; but its *baseline* `el_total` was 164.1213406 against the
published 164.120266, **+0.0011**. Both calibration functions are
idempotent and `el_total` is analytic, so neither was the suspect.

The cause is `build_model.main()`'s write block: `el*` and `premium` are
rounded to **1 dp** per district before the GeoJSON is written, while
`capital` falls through to **4 dp**. The published means are therefore
means of *rounded* columns — verified: the stored file has
`max |x - round(x,1)| = 0` for `el_total` and `premium`, and
`max |x - round(x,4)| = 0` for `capital`, and its exposure-weighted
means are exactly the three figures quoted above.

Quantised that way, 1-dp rounding puts **SD 0.00067** on the
exposure-weighted mean of 2,736 districts, so the observed gap is
**1.65 SD** — ordinary. 4-dp rounding puts SD 6.7e-7 on capital's mean,
which is precisely why the harness matched capital to the digit and
missed `el_total` by 1e-3. **The gap scales with each column's
granularity, which is the signature of rounding and of nothing else.**

Two consequences that outlive Gate 1:

- The harness is not offset. It reports UNROUNDED means; the file
  reports rounded ones. Paired differences were always trustworthy, and
  now absolute levels are too — to **±0.0013** (95%) on `el_total` and
  `premium`, and to ~1e-6 on `capital`.
- **`el_total` and `premium` read out of `districts_risk.geojson` are
  only good to about ±0.0013.** Quoting either to six decimals from that
  file is spurious precision. The £169.66 headline is safe by a factor
  of four; a future gate arguing over a tenth of a penny is not, and
  should re-derive from an unrounded run.

**Assembly followed the documented one-push procedure.** `rebuild.yml`
ran with `commit=false` precisely so it could not land the district
grain on its own; `sector-model.yml` ran on `sector-model` after main
was merged INTO it, and committed its output there; the sector file was
then crossed into main as `data/sectors_risk.geojson`. Locally only
`build_map` / `build_analysis` / `build_site` were run — **never
`make_images`**, whose PNG encoder differs from CI's and would fail the
next run as "docs/ is stale". 93 tests green, including both cross-grain
guards, and the level guard passed with 58x margin.

**What this does NOT do.** The claim-count budget got worse, exactly as
priced: subsidence 17,228 -> 17,783 implied claims, spare down from
10,060 to **9,505** against a remainder that needs 36,176. That is a
property of the ABI series rather than of this choice — every
consistent severity pairing pushes the same way — and it is now
recorded in `anchor_budget.py`, whose subsidence row also stopped
claiming the two figures came from "one release" when they never did.

## Fixed 2026-08-28: the published calibration figures had drifted twice

Right after the Gate 1 publish I grepped the **live** page for
GBP17,820 — a number that should no longer have existed anywhere — and
found it. The eight-row ABI calibration table on the methodology page
was hand-written, and it had drifted **twice**:

- **subsidence**, that same day, by my own severity change; and
- **theft**, stale since **2026-08-25**. It read GBP450m / ~118,000 /
  0.76% when the model had been moved to GBP341.6m / 89,895 / 0.58%
  three days earlier. Its footnote was worse than stale: it argued that
  "the resulting frequency (0.76%) sits inside the envelope" when the
  model had deliberately been put at the envelope's **floor**, so the
  page was defending a choice the model no longer made.

The landing page carried the same theft error in prose — "theft to the
last published theft total (~GBP450m)".

**Every numeric cell in both is now injected from `build_model.ABI`**
(`build_site.py`, the `__CAL_*__` keys), so there is one place to change
an anchor and it is the model. Three-significant-figure rounding is done
with a negative `ndigits` — that is what turns 99,592 into ~99,600 — and
the keys are spelled out as **literals**, because
`test_site_placeholders_all_resolve` greps `build_site.py` for quoted
tokens and an f-string-built key is invisible to it.

README's copy of the table cannot be derived — markdown has no build
step — so it is **pinned by a test** instead:
`test_readme_calibration_table_matches_the_model` parses the rows and
checks paid, average claim and implied count against `ABI`. Verified it
bites, by reverting one cell and watching it fail by name.

**A red commit, and why.** b5db786 went to main with
`test_site_placeholders_all_resolve` failing. The cause was mine and
worth naming: `pytest ... | tail -3 && git commit && git push` — `tail`
exits 0, so the `&&` chain never saw pytest's failure. 50244f8 fixed the
test; every push since reads pytest's own exit code. 94 green.

## Gate 1 priced 2026-08-27: the subsidence level, four ways

**CI run 33135605979**, 18.6 minutes, five full 20,000-year simulations
off ONE scored frame (`scripts/price_sub_level.py`, workflow
`.github/workflows/sub-level.yml`). Paired by construction: same
geology, same rasters, same seed, so nothing between these rows is
scoring noise. **Nothing is published — this is a table, and the
decision is the user's.**

| variant | paid GBPm | sev GBP | claims | EL | capital | premium | vs base | churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline (as shipped) | 307 | 17,820 | 17,228 | 164.1213 | 5.5405 | **169.6618** | — | — |
| severity fix only | 307 | 17,264 | 17,783 | 164.1213 | 5.5337 | **169.6551** | -0.004% | 2 |
| FY2024 derived | 280 | 17,264 | 16,219 | 162.3794 | 5.4473 | **167.8267** | -1.08% | 190 |
| FY2024 from quarters | 237 | 17,264 | 13,747 | 159.6267 | 5.3151 | **164.9419** | -2.78% | 520 |
| 2026 annualised | 288 | 17,264 | 16,682 | 162.8955 | 5.4727 | **168.3682** | -0.76% | 136 |

**Zero districts move two rating groups or more, in any variant.**

**The severity period mismatch costs 0.7 PENCE.** DATA_SOURCES #33
records that `sev_subsidence` = GBP17,820 is a **Q1 2026** average
paired with a **FY2025** paid total. Correcting it to the 2025 H1
average (GBP17,264 — same year, same basis, and independently
corroborated: H1's GBP153m over 9,000 supported households is
GBP17,000, and paid is seasonally flat at 49.8/50.2) moves the premium
by **-0.004%**, all of it capital (-0.12%), and shifts two districts a
group. This was predicted before it was measured, and the algebra is
the reason:

    FREQ_SCALE["sub"] = (paid / sev / POLICIES) / raw
    EL_sub(i)         = p_sub(i) * FREQ_SCALE["sub"] * E[sev]
                      = p_sub(i) * paid / (POLICIES * raw)

`sev` cancels, per district, exactly. What the severity actually
controls is the FREQUENCY/SEVERITY SPLIT at a fixed expected loss —
more, cheaper claims are thinner-tailed at the same mean, which is the
whole of the -0.12% capital move.

**The identity was verified across a 30% range of the level, not just
asserted.** Every variant's EL lands on `baseline_EL - (delta paid) /
POLICIES` to within **6e-14**. GBP307m -> GBP280m predicts -GBP1.742
and delivered -GBP1.7419.

**One correction to how that test was written.** The first run printed
`WARNING: the severity-cancels derivation is WRONG`. It was not. The
check used `np.array_equal`, and the difference was **2.8e-14 on
164.12 — one unit in the last place of a float64**, because the code
divides by `sev` and multiplies back by `exp(mu + sigma^2/2)` with
`mu = log(sev / exp(sigma^2/2))`, which is not a bit-exact round trip.
Demanding bit-equality of an algebraic identity computed in floating
point is a test bug. The check now asserts the stronger and more useful
form — EL == paid/POLICIES at EVERY level — and the script carries a
comment telling the next person not to put the bit test back.

**The level is the only real question, and its honest envelope is
GBP164.94 to GBP169.66 — GBP4.72, or 2.78% of premium.** All four
candidates are on the paid basis so they are comparable:

- **307** FY2025, published (ABI 2026-02). What ships.
- **280** FY2024, but DERIVED as 307-27 from a comparative line. Its
  own three published quarters sum to 178, implying a Q4 of 102 —
  **1.55x the largest quarter ever published**. Recorded unreconciled.
- **237** the same FY2024 annualised from those three quarters instead.
  The disagreement between 280 and 237 IS the size of that open gap.
- **288** 2026 annualised from Q2. Legitimate only because paid has no
  seasonality (2025: 49.8% H1 / 50.2% H2); the NOTIFIED series is 78%
  H2 and must never be annualised this way.

**Every candidate lands on buildings, which is the correctness check
that matters.** Buildings premium 113.30 -> 108.56 across the range
while contents holds at 56.37 -> 56.39. Subsidence is a 100% buildings
peril (`build_model.py:554`), so anything else would have been a defect
in the cover split.

**Two things this does NOT settle, both recorded rather than resolved.**

1. *The severity fix makes the claim-count budget worse.* Subsidence
   goes 17,228 -> 17,783 claims, and `anchor_budget.py` has only 10,060
   spare against a remainder needing 36,176. Every consistent severity
   choice pushes the same way — see DATA_SOURCES #33. A lower LEVEL
   pushes back (237 frees 3,481 claims), but picking a level to fix a
   budget elsewhere would be reverse-engineering the evidence, and is
   not a reason to prefer one.
2. *Paid LAGS, so no single paid year is a steady-state year.* The 2022
   surge (23,000 claims notified, GBP219m incurred) was settled across
   2023-25, so FY2025 paid contains run-off from it. `anchor_budget.py`
   already calls single-year anchoring a methodology defect; subsidence
   is the most volatile peril in the book, which makes it the worst
   place to have that defect. Fixing it properly needs the incurred
   basis and a claims-inflation index, and this repo has neither.

**A limitation of the table itself, stated rather than buried.** The
corrected severity GBP17,264 is held fixed across all four levels
because no 2024 or 2026 average on the paid basis has been published.
Pairing a 2025 average with a 2024 total is the same class of mismatch
this exercise is correcting. It is accepted here only because the
algebra above proves the severity cannot move the level anyway — the
mismatch costs capital at the third decimal place and nothing else.

**The laptop could not run this and that is worth recording.** Two
local attempts died with `_ArrayMemoryError` on **8.31 MiB** and then
**1.53 MiB**: the machine sat at 66.9 GB of a 68.4 GB commit limit with
`mc-fw-host` holding 25 GB on its own. BATCH and thread count were
halved first and changed nothing — at 1.5 MB it is not a footprint
problem. The workflow triggers on push to `exp/subsidence-series`
rather than by dispatch, because `workflow_dispatch` only fires from
the default branch and a measurement that may never ship does not
belong on main.

## Gate 0 measurement 2026-08-27: what `theta_ws` costs — GBP0.65

**The answer: `theta_ws` is worth GBP0.65 per policy — 0.39% of the
premium, but 11.8% of the entire capital charge.** Measured, not
argued, on throwaway branch `exp/theta-ws-measure` (commit 1f0854e,
CI run 33129830672). **DO NOT MERGE that branch** — it exists only to
produce this number and is retired below.

**What was changed.** One function. `theta_ws()` in `build_model.py`
was replaced by `np.full(..., 1.0)`, i.e. the weather-subsidence
pair-copula degenerates to independence (Gumbel at theta = 1 IS the
independence copula, exactly, not approximately). Nothing else moved.

**The intervention is clean and the measurement is well-identified.**

| column | published | theta_ws = 1 | change |
| --- | --- | --- | --- |
| `el_total` | — | — | **bit-identical, district by district** |
| `tail_dep_ws` | 0.4628 | 0.0000 | -100% |
| `theta_ws` | 1.6221 | 1.0000 | -38.4% |
| `tvar99_euler` | 256.46 | 245.56 | **-4.25%** |
| `capital` | 5.5406 | 4.8863 | **-11.81%** |
| `premium` | **169.66** | **169.01** | **-0.39%** |

`el_total` being bit-identical everywhere is the proof that only
dependence moved: a copula cannot touch marginals, and here it
demonstrably did not. So the whole GBP0.65 is a tail-dependence price,
with no expected-loss contamination.

**Read `tvar99_euler`, ignore `tvar99_vine`.** The standalone vine
columns move the *other* way (`tvar99_vine` +1.60%, `tvar99_vine5`
+1.54%, `var995_vine` +3.03%, `tvar99_gauss` +2.76%). That is NOT a
diversification finding — it is noise. The seed sweep (section below,
2026-08-22) put `tvar99_vine`'s relative SD across seeds at **12.4%**,
so a 1.6% move is a fifth of one standard deviation. `tvar99_euler`'s
relative SD is **0.33%**, so its -4.25% move is about 13 sigma. One of
these two numbers can carry a 0.39% conclusion and the other cannot.

**Where it lands.** 2,423 districts fall, **194 RISE**, 119 are flat.
The risers are Euler reallocation, not a modelling error: removing a
coupling shrinks the portfolio tail, and the Euler allocation then
redistributes a smaller pot on different shares. Rating-group churn is
90 of 2,736 (3.3%), **zero districts move two groups or more**. The
biggest movers are all high-`sub` coastal Essex/Kent/Hampshire — ME11,
CO14, ME12, CT5, CO12 at -1.2% — exactly the districts where a
subsidence-weather coupling would bite hardest. The cover split feels
it asymmetrically: buildings capital -13.9%, contents capital -4.9%,
which is right, since subsidence is a buildings peril.

**What this does NOT say.** The earlier claim in this session that
`theta_ws` is "physically backwards" was WRONG and is withdrawn. The
measurement contradicted it: the correlation between the subsidence
and windstorm drivers is **r = -0.09**, indistinguishable from zero,
and 2018 — the surge year — ranks **8th of 35** for storminess, not
quiet. The real finding is subtler and still open:

- the model **imposes** Kendall tau of 0.311-0.452 (mean **0.380**)
  across published districts, where the data supports **approximately
  zero**; and
- there is a genuine **negative** dependence it cannot represent at
  all — `jja_deficit` vs `rain5d`, **r = -0.604** — because a Gumbel
  copula admits only theta >= 1, i.e. only positive dependence.

That is a re-specification question, and by the user's own sequencing
decision it belongs to its own later phase, not to Gates 1-4. GBP0.65
is what it is worth fixing; the 194 risers are what makes it worth
doing deliberately rather than in passing.

**Branch retired 2026-08-27**, per the throwaway-measurement pattern:
worktree `.worktrees/theta-measure` removed, `exp/theta-ws-measure`
deleted locally and on origin. The number survives here; the code does
not need to.

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
| escape of water | 42.39 | 25.8% | — | *unsplit* | *unsplit* |
| fire | 28.00 | 17.1% | 78.0% | 21.84 | 6.16 |
| theft | 22.04 | 13.4% | 24.2% | 5.33 | 16.70 |
| flood | 20.13 | 12.3% | 48.0% | 9.66 | 10.47 |
| subsidence | 19.81 | 12.1% | 100.0% | 19.81 | 0.00 |
| weather | 15.74 | 9.6% | — | *unsplit* | *unsplit* |
| accidental damage | 14.65 | 8.9% | — | *unsplit* | *unsplit* |
| groundwater | 1.34 | 0.8% | 48.0% | 0.64 | 0.70 |
| **anchored subtotal** | **91.31** | **55.6%** | **63%** | **57.28** | **34.03** |
| **unsplit subtotal** | **72.81** | **44.4%** | | | |
| **TOTAL** | **164.12** | **100.0%** | | | |

**Recomputed 2026-08-25** against the published basis after theft's
level correction and the EoW freeze share went live. Three things moved
and all three point the same way. Theft fell from 17.1% of claim cost to
**13.4%**, so an ANCHORED peril shrank and the anchored subtotal fell
from 57.2% to **55.6%** — the split now covers less of the book, not
more. Fire is the second-largest cause. And the buildings fractions
themselves were corrected: `SPLIT_BUILDINGS` had carried the
placeholders written with the mechanism (theft 0.20, fire 0.70, flood
0.65, groundwater 0.80) rather than the anchors the later search
established (0.242 / 0.78 / 0.48 / 0.48), so the previous table's
"anchored" column was partly not.

**The finding that matters, and it inverts the entry below.** This file
spends a paragraph on flood's three contradictory conventions (66 / 48
/ 25). Swinging flood across all three moves the portfolio buildings
share by **4.9 percentage points**. The three unanchored perils move it
by **44.4**. The flood argument is a rounding error on the real
problem; it was agonised over because it was the tractable part, not
the important one. **Escape of water alone is 25.8% of claim cost —
more than five times the entire flood-convention uncertainty.** Any
future effort should go at EoW and nothing else.

The 2026-08-25 recompute sharpens this rather than softening it: the
unanchored block grew from 42.8% to **44.4%** of claim cost, because the
peril that shrank (theft) was one of the anchored ones. The gap between
what can be split and what cannot is widening, not closing.

**What this means for the portfolio number.** It is a bound, not an
estimate: on the recomputed basis **31.9%–81.6% buildings** across both
free choices together — the flood convention (EA 25/75 at one end,
Flood Re 66/34 at the other) and where the unanchored 44.4% falls.
Holding flood at the middle MCM convention narrows it only to
34.9%–79.3%, which is still a 44-point band — and a 44-point band is not
a headline figure and must never be published as one. What IS
publishable is the table above — per-risk-type claim cost that sums to
100%, a cover split on the 55.6% that has anchors, and the other 44.4%
named and left blank. That is honest, needs nothing bought, and is strictly more than
the site says today (which is nothing).

### BUILT 2026-08-25: the disclosure ships, the mechanism does not

The table above is now a section on the methodology page
(`site/methodology.template.html` id="cover", rows injected by
`build_site.cover_split`). **Not published — it lives on
`exp/buildings-contents` and merging it is the user's call.**

**The structural finding that made it shippable:** the table needs no
model change at all. It is the per-peril ELs the model already publishes
multiplied by five constants that have sources, so `build_site.py`
computes it from the committed GeoJSON and never reads `el_buildings`,
`capital_buildings` or anything else this branch adds. That cleanly
separates the disclosure, which is defensible today, from the mechanism,
which cannot ship while three of eight fractions do not exist. The
mechanism stays here, exact and unpublished.

`SPLIT_ANCHORED` and `PERIL_LABELS` were added to `build_model.py` so
"which perils have an anchor" is data rather than a comment — that one
line is what the whole phase turns on.

**Three guards, one of which caught a real bug on the way in:**
`test_every_split_peril_has_a_published_anchor` pins each anchored peril
to its documented value so the placeholder-as-anchor mistake cannot
recur; `test_the_published_cover_table_adds_up` reconciles the table to
`el_total` (tolerance set by the published file's one-decimal rounding,
still forty times tighter than the smallest peril); and the layout suite
rejected the table for overflowing on phone until it used the existing
`.tablewrap`/`.data` convention.

**A second draw-mean defect was found and fixed while doing this.**
`capital_buildings` was computed against `el_year_b`, a draw mean, while
the `capital` it splits uses the analytic `el_total` — the same
substitution the 2026-08-18 audit made for `capital`, with this sibling
missed. In the all-buildings corner `capital_buildings` must equal
`capital` and came back 0.30% and 0.23% low. **The additivity assertion
sitting three lines below it could never have caught this**, because
`capital_contents` is defined as the remainder and so adds up whatever
basis the buildings leg used. The block is extracted to
`apply_cover_split()` so the corners are testable at all, and the new
test was checked against the old formula first: it fails there.

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

**A second ordering lesson, from the 2026-08-19 publish.** The four
publishes before it crossed the sector output to main FIRST, then
merged the model change. This one merged to main first, which put
fixed district numbers and pre-fix sector numbers on the live site at
the same time — the two grains disagreed by ~1.39% on premium for as
long as the sector rebuild took. Nothing broke and no test can see it,
because each grain is internally consistent; only the pair is wrong.
**Rule: when a model change touches both grains, cross the sector
output to main BEFORE merging the model change, so main never
publishes a mixed pair.** If the sector run must come after (it needs
the merged `build_model.py`, as it did here), merge into
`sector-model` first, run it, and hold the main merge until its output
is ready to cross in the same push.

## Model audit 2026-08-18: reconciliation, and TWO UNFIXED defects

> **Both defects below are now FIXED and PUBLISHED**, along with three
> more found while fixing them — see "Built AND PUBLISHED 2026-08-19"
> further down. The claim-count overshoot recorded here is
> deliberately untouched and remains live.
>
> **The attribution below is WRONG and was corrected 2026-08-22.** This
> section blames the accidental-damage anchor as "the one that can be
> moved without contradicting a published total". That is true of AD's
> *paid* total and false of the quantity actually in dispute, which is
> its *count* — AD's count is 24.53% of 560,000 from the same verified
> GoCompare table that pins escape of water's 29.38%, so it is one of
> the legs that cannot be moved. See "Claim-count overshoot: attributed
> 2026-08-22" below, and run `scripts/anchor_budget.py`.

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

## PUBLISHED 2026-08-27: Phase 3, the buildings/contents cover split

Published on the user's explicit decision, with the objection stated
and not resolved. **Three of the eight perils have no published split
and are 42.5% of claim cost**; `SPLIT_BUILDINGS` gives them a central
guess (wx 0.85, eow 0.75, ad 0.45) so the mechanism runs. The branch's
own comment says the portfolio buildings share is a **31.8%-79.5%
BOUND, not an estimate**, and must never be a headline. It is not one:
the published figure is 66.5%, it appears only as columns in the data
file, and the methodology table still renders those three perils as
named-and-blank rather than filled in. That is the disclosure that
ships; the guess ships underneath it.

**Priced** (district run 33090028212): premium **£169.6619 -> £169.6619
(+0.00%), zero districts changing rating group**. Correct and expected
— the split is a pure reweighting of losses the model already had, so
`el_total`, `capital` and `premium` are untouched and only columns are
added. Reconciliation on the published file: `el_buildings +
el_contents - el_total` max 0.1, `premium_buildings + premium_contents
- premium` max 0.05, both 1-dp publishing rounding. Sector grain (run
33090025105) £169.6772, **+0.0090%** apart.

### Three things the merge surfaced, all of them the same shape

**The published theft figure was inconsistent with itself.**
`build_site.COVER_BLD` restated the split fractions as literals instead
of deriving them, and the copies had drifted: theft **25** there
against **0.242** in `SPLIT_BUILDINGS`, both citing the same ONS
nature-of-crime table. Shipping the cover section would have put 25% in
the peril table and 24% in the cover table, on the same page, from the
same source. Now derived from `SPLIT_BUILDINGS`/`SPLIT_ANCHORED`,
membership included, so a peril gaining or losing an anchor cannot
leave the two tables disagreeing about what is splittable. **The
published theft split moves 25% -> 24%.**

**The cross-grain guard would have disarmed itself.** The peril-set
skip treated every `el_`-prefixed column as a peril. Phase 3 adds
`el_buildings`, `el_contents` and `el_year_b` to the district file, so
a district-only Phase 3 publish would have looked like a peril
transition and **silently skipped both the level and shape checks** —
the precise failure that test exists to catch, defeated by the test's
own escape hatch. Restricted to actual peril legs. That skip was
written for a new peril reaching one grain first, and nothing else
should be able to trigger it.

**`_cover_split_frame` could no longer be built.** Phase 2c made
`marginal_params` read `ct_th/ct_eow/ct_fire/ct_ad`, and the two cover
tests' shared fixture predated it, so they died on a `KeyError` rather
than a failed assertion. Neutral 1.0s, so those tests keep testing the
cover split alone.

All three are the pattern this week has kept producing: not a missing
check, but a check that had quietly stopped being able to fail, or two
statements of the same fact that had drifted apart.

## PUBLISHED 2026-08-27: Phase 2c, council-tax band severity relativities

The user approved this with the market-vs-reinstatement question still
open and stated. It is recorded here as their decision, not as a
resolved modelling argument: council tax tracks MARKET value, insurance
pays REINSTATEMENT, and land is not insured. That objection is the
reason the branch sat held, and publishing does not answer it.

**What shipped.** The four attritional severities (theft, escape of
water, fire, accidental damage) stop being flat national anchors and
carry the district's council-tax band value relativity. Normalisation
is per peril with CLAIM weights, so each ABI severity level is pinned
by construction and only the geography of severity moves.

**Priced** (district run 33023989958, `commit=false`):

| | before | after |
|---|---|---|
| exposure-weighted premium | £169.6633 | £169.6619 (**-0.00%**) |
| rating-group churn | — | 1,928 of 2,736 (70.5%), 968 moving >=2 groups |

Level-neutral to four decimal places, exactly as the mechanism claims.
The movers are the whole point: SW1X +70.4%, W1K +67.0%, W1J +64.7%,
SW1Y +62.1%, SW7 +58.0% — Belgravia, Mayfair, St James's, South
Kensington — and AB13 (Milltimber) +56.6%. Downward: the Rhondda and
Ayrshire sectors at -18 to -20%. That is a property-value relativity
doing what it says.

**Sector grain** (run 33023951845, `skip_fetch=true`): £169.6772 over
10,398 sectors, **+0.0090%** from the district grain, in line with the
0.0085% the two have historically held.

### The sector grain nearly blocked this, and should have been checked first

`ct_bands.csv` is keyed on districts (`AB10`). Every sector row
(`AB10 1`) would have missed, and `ct_value_from_bands` turns a >20%
miss into a `SystemExit` — so the sector build would not have produced
a wrong number, it would have refused to run. Good design, but it means
Phase 2c was never crossable to both grains as it stood, and nothing in
the branch's own evidence said so. **A model change that adds a
name-keyed data file needs a sector-grain edition of that file before
it is callable "priced".**

Rebuilt at sector grain: 10,849 keys, 30,021,848 dwellings placed
(100.0%), covering 10,375 of 10,398 published sectors; the 23 that miss
(0.22%) take the neutral 1.0. Value geography sanity: dearest SW1X 8
2.00, cheapest CF43 4 / NP23 7 / KA25 6 at 0.69.

**The CI job for it lasted one run.** 33023456613 died on its first
request with `RemoteDisconnected`, three seconds in, before any data
moved; the identical fetch from a laptop placed 100%. The VOA host
refuses runner IPs, same as BGS and the EA. So it follows the precedent
already in `sector-model.yml` for the EA climate flood edition —
fetched off-runner, committed, documented — rather than leaving a job
that can only be red.

### The publish order was right this time, and the guard was still not enough

Both grains landed in ONE push. First time.

But this publish exposed the limit of the guard tightened two days ago.
**ct-severity is level-neutral, so a mixed pair across it sits 0.009%
apart on level** — inside 0.5%, inside 5%, inside any level bound that
would still permit an honest grain difference. The two files can agree
perfectly on the national premium while disagreeing about 70% of the
districts in the country. A single national number cannot see a
re-rating; it was only ever going to catch a re-levelling.

So the cross-grain test now also checks SHAPE: every district against
the household-weighted mean of its own sectors. Calibrated on this
publish, with both pairs on disk at the same time:

| pair | median deviation | p95 | districts >10% |
|---|---|---|---|
| consistent | 1.09% | 6.43% | 47 |
| mixed | 7.21% | 20.36% | 964 |

Bound at a **3% median** — 2.7x above the honest grain difference, 2.4x
under a stale pair, the same balance as the level bound. Median, not
max: 47 districts exceed 10% even when the pair is correct, so a
max-based bound would be noise. Verified as a LIVE negative control
rather than a synthetic one — it failed on the real mixed pair sitting
in the tree mid-assembly, and passed once the sector output crossed.

### Assembling a one-push publish locally: do not run make_images

Measured on unchanged data: `build_map`, `build_analysis` and
`build_site` reproduce CI's `docs/` byte for byte from Windows.
`make_images` does not — it rewrites four PNGs (`apple-touch-icon`,
`favicon-32`, `social`, `social-github`) through a different PNG
encoder. Committing those from here fails CI as "docs/ is stale", the
same symptom as the set-iteration and `cos(lat)` bugs. So: take `docs/`
from the CI rebuild artifact, run only the HTML chain locally, never
run `make_images` on this machine. Safe because `make_images` reads
only the district file, so the artifact's images survive the sector
crossing untouched.

## Cross-grain guard tightened 2026-08-25: 5% -> 0.5%

The publish-ordering rule has been broken twice, and after the second
time I wrote that nothing in CI compared the two grains and that the
guard was "not built". Both claims were wrong, and wrong in a way worth
recording, because the truth is less comfortable: the guard was there
the whole time and was too loose to fire.

`test_the_sector_model_nests_inside_the_district_model` reads both
published files and compares their exposure-weighted premiums. Its
bound was **5%**.

| window | grain drift | inside the 5% bound? |
|---|---|---|
| 2026-08-19 | 1.39% | yes — passed silently |
| 2026-08-25 | 4.1% | yes — passed silently |
| normal operation | 0.0087% | yes |

So the test watched both incidents go past and said nothing. A missing
test is a gap; a test tuned wider than its own failure mode is worse,
because it reads as coverage. This is the second time in two days that
a real defect hid behind something that looked like it was checking —
`sensitivity.py`'s comment claimed a basis it did not use, and this
assert claimed a comparison it could not fail.

**Now 0.5%**, which is ~57x the agreement the grains actually hold and
~8x under the drift that got through. Not tighter than that on purpose:
a genuine model change may widen the real geography gap, and the test
must fail on mixed pairs rather than on honest resolution differences.

**Verified by reconstructing the incident.** Scaling the sector file by
+4.1% and re-running produces `£169.66 vs £176.63` — against the
`£169.66 / £176.67` the live site actually served that day. The guard
fails on it; on the real pair it passes with 57x margin.

**One consequence, accepted deliberately.** `rebuild.yml`'s pre-flight
runs the full suite, so it now refuses to run while the two committed
files disagree. That is intended, and it is NOT the deadlock the
peril-set skip further up exists to avoid: recovery from a mixed pair is
crossing the sector file, which is a plain commit, not a rebuild. Both
sanctioned publish orders land the pair in one push, so a correct
publish never trips it. On `sector-model` the test skips outright — that
branch has no district build to compare against.

### Was the loose bound systemic? Measured: no

Having found one assert too wide to fail, the obvious worry is how many
others are. So every numeric tolerance in the suite was measured against
what it actually sees. The useful statistic is **margin** — bound divided
by realised value. A bound a test clears by 2x is doing work; one it
clears by 574x is decoration.

| assert | realised | bound | margin |
|---|---|---|---|
| `premium = el_total + capital` | 0.0985 | 0.15 | 1.5x |
| seed stability, median move | 6.4% | 12% | 1.9x |
| `inv_mixed_cdf` mean level | 2.64% | 5% | 1.9x |
| `inv_mixed_cdf` frequency | 0.00088 | 0.002 | 2.3x |
| `el_total5 = el_total + el_er` | 0.1000 | 0.25 | 2.5x |
| `premium_cc = el_total_cc + capital_cc` | 0.0500 | 0.15 | 3.0x |
| exposure conserved across grains | 0.0585% | 0.5% | 8.6x |
| **cross-grain premium level (before)** | **0.0087%** | **5%** | **574x** |

Everything else is calibrated. The Monte Carlo bounds sit ~2x out, which
is right for a seeded estimator; the reconciliation bounds are set by
1-dp publishing and sit 1.5–3x out; the seed-stability bound at 12% was
chosen to sit between the behaviour it rejects (20.6%, the pre-2026-08-19
realised allocation) and the behaviour it accepts (6.4%, conditional) —
that one is a good example of a bound picked from evidence.

One test came back with no `assert` at all —
`test_premises_join_failure_is_fatal_not_silent`. False alarm: it asserts
through `pytest.raises` and then re-runs the legitimate case to prove it
does *not* raise. It is one of the stronger tests in the file.

So the 5% bound was an outlier, not a symptom. Worth knowing rather than
assuming, in either direction.

## Draw-mean sweep 2026-08-25: the question made permanent

The user asked whether anything else compares against a draw mean. It
was worth asking: by then the 2026-08-18 analytic/draw fix had produced
**three** follow-on defects, each found by hand, one at a time, none by
CI. This is the sweep run properly and then wired into the suite so it
does not have to be run by hand a fourth time.

**The pair.** `el_total` is the sum of the analytic legs (`p * E[sev]`).
`el_year` is `year_loss.mean(axis=1)`, the mean of the simulated years.
They estimate the same quantity. The analytic one is the right basis for
capital because `calibrate_frequency` solves against the exposure-weighted
mean of the analytic `p` — no draw enters that loop, so `p * E[sev]` *is*
the calibration target. `el_year` only ever agrees with it up to Monte
Carlo error, which is exactly what makes the bug survivable: it never
looks wrong.

**What was swept.** Every `.py` under `scripts/` on `main`,
`exp/ct-severity`, `exp/buildings-contents` and `sector-model` — every
`.mean(axis=1)`, every `el_year` reference, every capital formula.

| site | verdict |
|---|---|
| `build_model.py` `tvar(...)` partition helper | correct — a tail mean over draws is *meant* to be a draw mean |
| `build_model.py` `res["tvar99_euler"]` | correct — same |
| `build_model.py` `capital` | correct — on `el_total` since 2026-08-18 |
| `build_model.py` `capital_cc` (climate) | correct — subtracts `sim_cc["el_total"]` |
| `seed_sweep.py` capital | correct — on `el_total` |
| `seed_sweep.py` `COLS` listing `el_year` | correct — `el_year` is a diagnostic *being* seed-tested there, not a basis |
| `backtest_coverage.py` `draws.mean(axis=1)` | correct — a 200k bootstrap of k-year windows, compared against an observed k-year window; draws are the point |
| **`sensitivity.py` premium** | **DEFECT — subtracted `el_year`** |

**The one defect.** `sensitivity.py` carried the pre-audit formula, under
a comment that read "same basis as build_model" — which by then it was
not. One file, but present identically on all four branches, because it
predates the branching rather than being four separate mistakes.

**Measured, not assumed.** A two-district synthetic frame made this look
like a 4–6% error. On the real baseline (912 districts, 1-in-3 sample,
the frame `sensitivity.py` actually builds) it is not:

```
                     stale (el_year)   fixed (el_total)    diff
capital                       5.7734             5.7575   +0.28%
premium                     169.5309           169.5150   +0.01%
el_total 163.7575    el_year 163.4926  (-0.16%)
rating-group churn between the two bases: 0 of 912
```

With 912 districts the draw mean is well estimated, and here it sits
0.16% *below* `el_total` — the opposite sign to the tiny frame, so the
stale basis ran capital slightly **high**, not low. No sensitivity
conclusion this repo has published turned on it. It was fixed for basis
consistency and because the comment asserted a basis it did not use, not
because it changed an answer. Saying otherwise would overstate it.

**The guard.**
`test_no_capital_formula_is_taken_against_a_draw_mean` reads the source
of every script, strips comments (prose may name `el_year`; executable
code may not), finds each `np.maximum(` whose first argument mentions
`tvar`, and fails if that argument names a draw mean. It scans source
rather than numbers deliberately: the two bases agree to fractions of a
percent, so **no value assertion would ever catch this**. Verified both
ways — passes on the fixed tree, and reverting the one line makes it
fail with `sensitivity.py:144` and nothing else.

The argument is extracted with a paren counter, not a regex. A non-greedy
`np\.maximum\(\s*(.*?),\s*0\.0\s*\)` looks right and is not: `marginal_params`
has an `np.maximum(..., 0)` with no `.0`, so the match runs on past it and
reports a defect hundreds of lines away. That was caught by the negative
control, which is the reason to always run one.

## Branch inventory, tidied 2026-08-27

Every branch that exists, why it exists, and what would retire it. Two
permanent branches remain, plus one live experiment. Both permanent
branches are synced to current main and pass their own suites (main 93,
`sector-model` 92 + 1 skip).

**`sector-model`'s one skip is deliberate.**
`test_the_sector_model_nests_inside_the_district_model` had been red on
that branch since it was written, and not because of a defect: the
branch's `build_model` writes the SECTOR grain to the generic output
path, so its `data/districts_risk.geojson` holds 10,398 sector rows and
there is no district build to nest against. It now detects that and
skips. The skip was **not** ported to main, where sector grain in
`districts_risk.geojson` would be the real thing — the 2026-08-25
publish-ordering mistake — and must keep failing loudly.

So the cross-grain test I said did not exist, when owning that
publish-order mistake, **does** exist and runs on main. What it does
not do is gate the *publish*: it checks two files already on disk, so
it catches a mismatched pair after a build, not an out-of-order deploy.
The gap I described is real; I described its location wrongly.

| branch | state | why it is kept |
|---|---|---|
| `main` | published | the product |
| `sector-model` | permanent, 33 ahead | the same model at postcode-SECTOR grain. **NEVER merges to main** — only `data/districts_risk.geojson` crosses, renamed `data/sectors_risk.geojson`. main merges INTO it, never the reverse. |
| `exp/subsidence-series` | LIVE, Gate 0 | the temperature-driven subsidence/freeze workstream. Data acquisition and evidence only so far — no model change, premium untouched. |

**Deleted 2026-08-27 (second tidy):** `exp/theta-ws-measure`, a
throwaway that existed to price one function and did so — GBP0.65, its
own section above, commit 1f0854e, CI 33129830672. It was never
mergeable by design: it set `theta_ws` to a constant to measure the
difference, not to propose it. Deleted locally and on origin the moment
the number was written down. If a measurement branch's output is a
NUMBER, the number belongs in this file and the branch belongs in the
bin — leaving it around invites someone to merge it.

**Deleted 2026-08-27:** `exp/ct-severity` and `exp/buildings-contents`,
both published that day and both sitting at exactly main's commit, so
every commit is reachable from main. Same disposal as `exp/eow-freeze`
and `exp/theft-level` after the 2026-08-25 publish.

**The roadmap is now complete.** Phase 1 (eight attritional perils),
Phase 2a (theft's residential denominator), Phase 2c (council-tax band
severity relativities) and Phase 3 (the buildings/contents cover split)
are all published at both grains. Two open questions ride along with
that and are NOT closed by having shipped: council tax tracks market
value while insurance pays reinstatement, and three perils worth 42.5%
of claim cost carry an unanchored split. Both are the user's accepted
decisions, recorded in their own sections above.

**Deleted 2026-08-25:** `exp/eow-freeze` and `exp/theft-level`, both
fully merged into main and published, commits reachable from main. Same
disposal as `exp/el-and-flood-fixes` after the 2026-08-19 publish.

**Keep experiment branches merged up to main.** `exp/buildings-contents`
was allowed to drift 48 commits, and that drift silently broke the cover
split: main's 2026-08-18 audit fix moved `el_total` onto analytic legs
while `el_buildings` went on summing draw means, and the identity test
only fired when the branch was finally merged. A branch that is behind
is not dormant, it is quietly diverging.

## exp/ct-severity (Phase 2c), re-priced 2026-08-25 — AWAITING THE USER'S DECISION

> **Re-run against the published baseline, 2026-08-25 (CI
> [32893304946](https://github.com/SMcode-source/uk-home-insurance-risk-map/actions/runs/32893304946)).**
> The figures below are now measured against £169.66, not the superseded
> £176.66. **The prediction made when this was flagged stale held
> exactly**: still level-neutral (EL −0.00%, premium −0.00%, capital
> −0.01%), and because theft is now a smaller share of the book the bite
> is slightly SMALLER — p95 +22.78% → **+22.09%**, p5 −14.32% →
> **−14.07%**. Everything else is unchanged in character: churn 1,928 of
> 2,736 (**70.5%**), **968** districts moving ≥2 groups, Spearman
> **0.8198**, dispersion 1.507 → **1.600**. Prime London still leads
> (SW1X +70.4%, W1K +67.0%, W1J +64.7%, SW1Y +62.1%, SW7 +58.0%, AB13
> +56.6%) and post-industrial cores still fall (L6 −20.9%, TS1 −20.8%,
> S14 −20.4%, L7 −20.2%, CF43 −19.4%). The percentages in the sections
> below are therefore still right to within a few tenths; the £ figures
> they sit beside are on the old baseline. **The open question in "Two
> checks run against it" is untouched** — it is about what council-tax
> bands mean, not about the level, and no rerun can settle it.

Branch `exp/ct-severity`, rebased onto published main (afcf0a5; the old
185485c evidence was measured against the pre-2a baseline and is
superseded). CI run
[32788080788](https://github.com/SMcode-source/uk-home-insurance-risk-map/actions/runs/32788080788),
`commit=false`. **Not merged. This is the user's call, and of the three
open experiments it is by far the largest change to the map.**

**What it does:** the four attritional severities (theft, EoW, fire, AD)
are flat national ABI anchors with no geography at all. This scales each
by the district's council-tax band mix — the only full-stock, small-area,
OGL property-value proxy in Great Britain — using each nation's statutory
charge ratios as band weights.

**The national level does not move**, by construction: the multiplier is
normalised to a CLAIM-weighted mean of exactly 1 per peril (households ×
that peril's rate), so each peril lands back on its ABI level.

| | published | branch | change |
|---|---|---|---|
| expected loss | 171.11 | 171.11 | **0.00%** |
| premium | 176.66 | 176.66 | **−0.00%** |
| capital | 5.54 | 5.54 | −0.01% |
| tvar99_euler | 263.49 | 263.49 | −0.00% |

**The mechanism was verified per district, not assumed.** On SW1X
(relativity 1.940) the four scaled perils came back at 1.950 / 1.938 /
1.979 / 1.944 and flood and subsidence at exactly 1.000; on CF43
(relativity 0.691) at 0.697 / 0.691 / 0.702 / 0.692, flood and
subsidence again 1.000. The small per-peril spread is the separate
claim-weight normaliser each peril gets, which is the intended design.

**But the map moves hard.** Churn **1,908 of 2,736 districts (69.7%)**,
69.6% of households, and **974 move by ≥2 rating groups**. Premium
Spearman **0.8219** — against 0.993 for both other open experiments.
Dispersion widens 1.544 → **1.624**. Median +1.33%, p5 −14.3%, p95
+22.8%; 1,516 rise, 1,216 fall.

**Risers** are prime London and one affluent Aberdeen suburb: SW1X
+72.4% (Belgravia), W1K +68.8% (Mayfair), W1J +66.1%, SW1Y +64.1%, SW7
+59.7% (South Kensington), AB13 +56.5% (Milltimber), W1C +55.5%, W1S
+55.3%, W8 +53.6% (Kensington), SW1E +52.3%.

**Fallers** are post-industrial urban cores: TS1 −21.3% (Middlesbrough),
L6 −21.3%, L7 −20.6%, L4 −19.8%, L5 −19.7% (Liverpool), S14 −20.8%, S5
−20.3%, S2 −20.1%, S4 −20.0% (Sheffield), SR1 −19.7% (Sunderland).

**This is the collision this file predicted:** 2a cut prime London on
theft's commercial denominator, 2c raises it on value. They are not
contradictory — one is claim frequency, the other claim size — but if
both ship, W1J's net move is the thing to check, not either in isolation.

### Two checks run against it, one of which it passed

**PASSED — the cross-nation schedule artefact does not exist.** England's
statutory ratios span 3.0× (6→18 over bands A→H) but Scotland's
post-2017 ratios span 3.68× (240→882), so normalising within nation pins
the level while potentially leaving Scottish districts a mechanically
wider *spread* — an artefact of local-government finance, not of housing.
Measured, it does not happen: relativity p95/p5 is **1.69 England, 1.65
Scotland, 1.56 Wales**. The schedules differ; the resulting dispersion
does not.

**OPEN — council-tax band tracks MARKET value; insurance pays
REINSTATEMENT.** Buildings cover excludes land, and land is most of what
separates Belgravia from Bootle. The saving grace is that the statutory
ratios compress enormously — band H is 2× band D in charge terms against
perhaps 10× in market value — so the district relativity spans only
1.68× p5–p95 (2.8× extremes) where raw market value across these
districts spans 15–25×. The direction is not in doubt: dear areas do
have dearer contents and costlier reinstatement. **What has no anchor is
the assumption that a 1991-valuation local-government charge schedule is
the correct compression for insurance severity.** Nothing published says
it is. This matters most for fire, which Phase 3 puts at 78% buildings,
and least for theft at 25%.

That is the decision in one line: the direction is well founded and the
mechanism is exact, but the *magnitude* rests on a schedule built for
council tax, and it re-rates 70% of the map.

## PUBLISHED 2026-08-25: two knobs at once, verified before it shipped

User decision: **"yes go ahead and publish"** on the recommendation to
take `exp/eow-freeze` and `exp/theft-level` and to HOLD
`exp/ct-severity`. Merges 930b99b and 0fa5aa4; both parameter comments
rewritten from experiment framing to shipped-model prose in 768a88f.

**Verified as a pair before publishing, not after.** Each branch had
only ever been priced against published main on its own, and rating
groups are quantiles, so combined churn is not the sum of the two. CI
[32789547647](https://github.com/SMcode-source/uk-home-insurance-risk-map/actions/runs/32789547647)
ran the merged main with `commit=false` first.

| | published | merged | change |
|---|---|---|---|
| expected loss | 171.11 | 164.12 | −4.09% |
| premium | 176.66 | 169.66 | **−3.96%** |
| capital | 5.54 | 5.54 | −0.03% |
| tvar99_euler | 263.49 | 256.47 | −2.66% |

**They compose with no interaction at all**, which is what the perils
predicted: theft-level alone was −4.09% EL and −3.96% premium, and the
pair returns exactly the same. National `el_th` moved −24.10%, which is
341.6/450 to the second decimal, and national `el_eow` moved −0.00%.
Both mechanisms are present and neither disturbed the other.

**The two effects remain separable in the output.** PH10's EoW EL rose
58.6 → 75.8 and TR22's fell 36.2 → 29.5 while the national EoW level did
not move, so the freeze redistribution survived the merge intact;
EC3V's theft EL fell 127.9 → 97.1 on the level cut.

**Net map effect:** 2,462 districts fall, 265 rise, 9 flat. Median
−3.32%, p5 −7.90%, p95 +1.22%. Spearman **0.9854** against published;
dispersion tightens 1.544 → 1.507. Biggest fallers are commercial cores
losing theft (EC3V −13.4%, EC4M −13.0%, WC2E −12.4%, W1C −12.3%, WC2H
−12.3%, W1F −12.1%, LS2 −11.7%); the risers are the frost-exposed
Highlands, where the EoW gain outweighs the theft cut.

**Both grains are live and agree.** District publish is bot commit
531da04 (rebuild run 40): premium **£169.6633**, EL £164.1213 over
2,736 districts. Sector output from `sector-model` run 13 (bot 80d1063,
`skip_fetch=true` — only two model parameters moved and no hazard input
changed) crossed to `data/sectors_risk.geojson` in d4723ea: premium
**£169.6780** over 10,398 sectors, **0.0087%** from the district grain
and in line with the 0.0085% the two have historically agreed to. The
sector-model branch is NOT merged and never is; only that one file
crosses. docs/ was rebuilt in the same commit as the crossing.

**Still held, deliberately:** `exp/ct-severity` (Phase 2c). Not a
rejection — the open question is recorded in its own section above.

### The publish order was wrong again, and the file already said so

**I repeated the 2026-08-19 mistake.** The rule two sections down —
written after that publish — says: when a model change touches both
grains, cross the sector output to main BEFORE merging the model change,
and if the sector run needs the merged `build_model.py`, merge into
`sector-model` first, run it, and hold the main merge until its output
crosses in the same push. I did neither. Districts were merged and
published first (531da04), the sector rebuild started afterwards, and
for the ~40 minutes in between the live site served **£169.66 at the
district grain and £176.67 at the sector grain**.

Nothing broke and no test can see it, exactly as predicted: each grain
is internally consistent and only the pair is wrong. The site's own
cross-grain check did notice — it published "exposure-weighted level
within **4.1%**" for that window, against 0.0% now.

**Why the rule is easy to break.** Both correct orderings require
holding a finished, verified, user-approved change unpublished while a
second ~40-minute job runs. The instinct after a green verification run
is to ship it. The rule exists precisely because that instinct is wrong
here.

**What would actually prevent it,** rather than another note asking the
next person to remember: nothing in CI compares the two grains. A test
that reads both `data/districts_risk.geojson` and
`data/sectors_risk.geojson` and fails when their exposure-weighted
premiums differ by more than ~0.05% would have caught this the moment
main was pushed, and would have caught the 2026-08-19 window too. The
0.0085% the grains historically agree to gives a comfortable threshold.
**Not built** — it is a real guard and worth having, but it would have
failed CI on a state I had deliberately created, so it needs the
publishing flow settled first.

> **The paragraph above is WRONG, and was corrected 2026-08-25.** The
> guard WAS built — `test_the_sector_model_nests_inside_the_district_model`
> compares exactly those two files and runs on every push to main. It
> said nothing because its threshold was **5%**, and the two windows it
> was meant to catch measured 1.39% and 4.1%. Both fit inside it. The
> problem was never a missing test; it was a test set 574x wider than the
> thing it guarded. **Now tightened to 0.5%** — see "Cross-grain guard
> tightened 2026-08-25" below. I wrote "nothing in CI compares the two
> grains" without checking whether something did.

### Two published headline figures were wrong, found while verifying

Both fixed in the same session (commit "Two published headline figures
were wrong, in two different ways").

**1. The map pages quoted a hardcoded premium, two publishes stale.**
`map/template.html` carried the literal text "~£170/policy/yr, around
77%". Nothing regenerated it. `docs/map.html` and `docs/sectors.html`
come out byte-identical on every rebuild, so they produce no diff, land
in no publish commit, and no stale-check fires — the two most-visited
pages on the site went on quoting a figure from before the 2026-08-19
publish while the data underneath them was current. Both numbers are now
injected by `build_map.py`, and `build_map`'s existing
unsubstituted-placeholder guard means they cannot silently rot again.
Each page reports **its own grain**, so a mixed district/sector pair is
now visible on the site instead of hidden behind one shared constant.

**2. `__MEAN_EL__` was an unweighted mean, next to a weighted one.**
`build_site.py` computed the headline as `np.mean` over districts while
the share beside it in the SAME SENTENCE (`__EL_CLAIMS_SHARE__`) was
exposure-weighted. "Come to £163 per policy per year — 75% of what all
home claims cost" mixed two bases: £163/£219 is 74%, and the 75% implies
£164. An unweighted mean over 2,736 districts is not a per-policy figure
at all — it over-weights small rural districts. Now weighted, which is
what `build_site.py`'s own comment eight lines above already said
"nationally" means everywhere in this model.

Published headline is now **£164/policy/yr, 75%** at both grains.

## PUBLISHED 2026-08-25: exp/eow-freeze, the EoW freeze share

Branch `exp/eow-freeze`, CI run
[32787462774](https://github.com/SMcode-source/uk-home-insurance-risk-map/actions/runs/32787462774),
`commit=false`. **MERGED to main 930b99b on the user's decision
("yes go ahead and publish", 2026-08-25) and published in the combined
run below.**

**One input changed:** `EOW_FREEZE_SHARE` 0.15 → **0.31** — the fraction
of escape-of-water claim cost that is freeze-driven (burst pipes) rather
than year-round plumbing failure. The shipped 0.15 had no published
anchor; the replacement has two, and they agree.

**The derivation** (committed to main separately, 45ba0b3, so the anchor
exists whether or not this branch merges): ABI puts burst-pipe cost at
**6.00% of total home paid in 2023 and 5.94% in 2025**. Escape of water
is 19.3% of the book. On a consistent basis that is a freeze share of
**0.311 and 0.307** — two independent release years landing within 0.004
of each other, against a shipped value less than half either.

**What CI actually produced**, against the published artifact:

| | published | branch | change |
|---|---|---|---|
| expected loss | 171.11 | 171.11 | **0.00%** |
| premium | 176.66 | 176.66 | **−0.00%** |
| capital | 5.54 | 5.54 | −0.03% |
| tvar99_euler | 263.49 | 263.47 | −0.01% |

**The national level does not move at all, by construction.** The frost
relativity is normalised to an exposure-weighted mean of exactly 1
before it reaches `eow_rate`, and `calibrate_frequency` re-pins the level
regardless, so this is a **pure redistribution**: it changes where EoW
claims fall, never how many there are. That is the cleanest kind of
model change — no re-levelling to defend, only geography.

**Where it moves, and it is the right places.** Risers are the Scottish
Highlands, the frostiest districts in the UK: PH10 +11.2% (group 4→7),
AB36 +10.7%, IV4 +10.3%, PH18 +10.2%, PH20 +9.5%, PH26 +9.3%, IV13
+8.9%, PH22 +8.8%, AB35 +8.7%. Fallers are the mildest, near-frost-free
coast: TR22 −5.5%, TR23 −5.2%, TR21 −5.0%, TR24 −4.9% (Isles of Scilly),
TR5 −4.6%, PL29 −4.5%, TR25 −4.4%, PL28 −4.3%, TR19 −4.3%, TR26 −4.3%
(west Cornwall). Raising the freeze-sensitive slice should shift burst
pipes from Penzance to Aviemore, and that is precisely what it did — the
sign test passes on both tails at once.

**Distribution:** median +0.14%, p5 −2.27%, p95 +3.03%; 1,444 rise, 1,224
fall, 68 flat. Rating-group churn 579 of 2,736 (21.2%), 17.1% of
households, **16 move by ≥2 groups**. Premium Spearman **0.9933**;
dispersion p90/p10 1.544 → 1.531, so the map barely widens or narrows.

**The case for taking it:** it replaces an unanchored knob with a
two-year-consistent published one, at zero cost to the national level,
and moves the geography in the direction the physics demands. It is the
least contentious of the three open experiments — nothing about the
headline premium changes, so there is no re-levelling to justify.

**The one caveat:** 0.31 is derived from burst-pipe cost as a share of
*total home paid*, divided by EoW's *share of the book*. Both numerators
come from ABI releases, but the 19.3% EoW share and the burst-pipe
percentage are not stated in the same table, so the ratio is assembled
rather than published. Two years agreeing to 0.004 is strong evidence
the assembly is sound; it is not the same as ABI printing 0.31.

## PUBLISHED 2026-08-25: exp/theft-level, theft's paid total

Branch `exp/theft-level`, CI run
[32607071195](https://github.com/SMcode-source/uk-home-insurance-risk-map/actions/runs/32607071195),
`commit=false`. **MERGED to main 0fa5aa4 on the user's decision
("yes go ahead and publish", 2026-08-25) and published in the combined
run below.**

**One input changed:** `theft_paid` 450e6 → **341.6e6**, severity held at
the current published ABI average of £3,800. The direction is the
defensible one — theft's *paid total* is the stale half (2018), its
*average* is current (2025) — and 0.58%/policy × 15.5m × £3,800 = £341.6m
is the bottom of the envelope DATA_SOURCES #25 already documents.

**The dose-response across theft's own documented envelope** (analytic;
EL is `paid ÷ policies` by construction, so this needs no simulation):

| theft level | £m | claims | % of 560k | book EL | premium | vs published |
|---|---|---|---|---|---|---|
| 2018 paid at 2018 avg (envelope top) | 571 | 150,350 | 26.85% | 179.00 | 184.55 | +4.5% |
| **as shipped** (2018 paid ÷ 2025 avg) | 450 | 118,421 | 21.15% | 171.11 | 176.66 | — |
| **this branch** — floor, claims fell with burglary | 342 | 89,900 | 16.05% | 164.06 | 169.61 | −4.0% |
| fits the count budget alone | 242 | 63,779 | 11.39% | 157.61 | 163.16 | −7.6% |

**What CI actually produced**, against the published artifact:

| | published | branch | change |
|---|---|---|---|
| expected loss | 171.11 | 164.12 | **−4.09%** |
| premium | 176.66 | 169.66 | **−3.96%** |
| capital | 5.54 | 5.54 | **−0.03%** |

**Capital does not move at all**, which confirms the mechanism rather
than assuming it: `W_THEFT = 0.0013` makes theft almost fully
diversifying, so its contribution to the worst 1% of years is its mean,
`tvar99_euler` falls exactly with EL, and the correction is a **pure
level change with no tail effect**. The analytic prediction was −4.0% and
CI returned −3.96%.

**Distribution of the move:** median −3.2%, p10 −6.3%, p90 −1.4%, range
−11.9% to +0.1%. 2,657 districts fall, 1 rises. Rating-group churn 731 of
2,736 (26.7%), 27.2% of households, but **only 3 move by ≥2 groups**.
Premium Spearman **0.993** — the ranking survives.

**Who loses most:** EC3V −11.9%, B40 −11.4%, EC4M −11.4%, LS2 −11.2%,
W1C −11.0%, WC2E −11.0%, WC2H −10.9%, LS1 −10.6%, SR1 −10.2%. Every one
is a commercial-core or city-centre district — the high-burglary end,
which is exactly where a theft level cut should land. All stay in
group 10.

**Dispersion barely changes:** EL p90/p10 1.549 → 1.524, premium 1.544 →
1.517. The map compresses slightly and tells the same story.

### Two things to weigh before deciding

**1. Even the floor does not fully fit the count budget.** 89,895 claims
clears the 99,955 the six pinned legs leave, with 10,060 spare — but
away-from-home accidental damage alone needs 36,176 of those, before any
liability or legal expenses. So this correction improves the book without
closing it, and theft is probably not the last word.

**2. The attribution rests on two shares that may not be the right
population.** Two of the six "pinned" counts — EoW 29.38% and AD 24.53% —
come from GoCompare's **quote-declared** claims table (40,962 claims
declared at quote, typically a five-year lookback). The model applies
those shares to the ABI's 560,000 *paid* claims in a single year. Those
are different populations. DATA_SOURCES is internally inconsistent about
it: #26 calls the EoW figure "GoCompare from ABI data" while #28 says it
is the quote-declared table and that EoW's share comes from the same
place. **If either share is overstated, theft's budget is larger and the
case for this cut is weaker.** GoCompare bot-blocks fetches, so this
could not be resolved here. It is the first thing to settle if the
decision is close.

## Coverage backtest 2026-08-23: the first test against real years

Until now nothing in this repo had ever checked the model's distribution
of years against a year that actually happened.
`scripts/backtest_coverage.py` does, for the one part of the book where
the ABI publishes an annual series. It compares the simulated national
**storm + flood** distribution against the published per-year totals.
Storm and flood are used because they map one-to-one onto `w_v` and `f_v`
and are published separately per year; the ABI's headline weather line
also contains burst pipes, which sits inside the EoW leg behind
`EOW_FREEZE_SHARE` and cannot be split back out of the year view.

```
.venv/Scripts/python.exe scripts/backtest_coverage.py          # cached, instant
.venv/Scripts/python.exe scripts/backtest_coverage.py --fresh  # re-simulates, ~40 min
```

The 20,000-year series is cached in `data/backtest_years.npz` (204 KB).
**Re-run with `--fresh` after ANY change to `build_model.py`** — the
cache has no way to know the model moved under it.

**The simulated distribution, GBP m national:**

| p1 | p5 | p25 | **p50** | p75 | p95 | p99 | mean | cv |
|---|---|---|---|---|---|---|---|---|
| 51 | 102 | 238 | **413** | 701 | 1,435 | 2,361 | 547 | 0.885 |

| year | storm | flood | total | model percentile |
|---|---|---|---|---|
| 2023 | 133 | 286 | 419 | 50.7% |
| 2024 | 185 | 226 | 411 | 49.7% |
| 2025 | 244 | 312 | 556 | 64.8% |

**On coverage the model passes.** 3 of 3 observed years land in its
middle half. Read the MEDIAN (413), not the mean (547) — the distribution
is strongly right-skewed, so most years sit well below the mean by
construction, and comparing a handful of years against the mean and
calling the gap bias is a mistake. That is the mistake I made earlier the
same day; see the retraction in the section below.

**The real test, a 200k bootstrap of 3-year windows:**

| statistic | observed | model median | P(model ≤ observed) |
|---|---|---|---|
| mean of the window | 462 | 490 | **0.450** |
| cv within the window | 0.176 | 0.608 | **0.048** |

- **Level: not contradicted.** The observed 3-year mean sits at the 45th
  percentile of what the model expects a 3-year window to average.
  Completely unremarkable.
- **Spread: the model's ordinary years are too volatile.** Only 4.8% of
  simulated 3-year windows are as steady as the observed one.

**Caveats on the spread result, which are serious.** n = 3, so the sample
cv is heavily biased and noisy; p = 0.048 on three points is weak
evidence. The window is 2022–2025 and contains **no catastrophic flood
year** — 2007 (~£3bn insured) or 2015–16 Desmond/Eva would widen the
observed spread a long way. Four quiet years cannot measure a tail. What
they can say is that the model's *ordinary* years are too volatile, which
is a narrower and more testable claim, and each new ABI year tests it.

**And then the proportionality check, which cuts it down to size.** Read
off the shipped artifact:

| | |
|---|---|
| expected loss | £171.11 |
| premium | £176.66 |
| **capital — the tail's entire contribution** | **£5.54 = 3.1% of premium** |
| capital as % of premium, across districts | 1.5% – 4.3% |
| EL p90/p10 | 1.55 |
| premium p90/p10 | 1.54 |

**Deleting the capital charge entirely would move the premium by 3.1%.**
A tail that is too wide by some fraction moves it by less. And the map's
spatial pattern is not the tail's at all — EL and premium have the same
dispersion, so what the map shows is expected loss, full stop.

**So the spread finding is real, worth recording, and is not where the
money is.** Expected loss is 97% of the premium and 100% of the map. The
theft level — one leg carrying 17% of EL (£29 of £171) and over its
claim-count budget on every reading — is worth roughly **2.5× the entire
capital charge**. That is the priority, and this backtest is what
established the ordering rather than guessing at it.

## The ABI releases, read properly, 2026-08-23

The user asked for annual ABI data, used granularly, at whatever grain we
actually have it. The primary releases are now transcribed one figure at
a time into **`data/abi_annual.csv`**, each row carrying its source URL, a
`published`/`derived` flag and the release it came from. Use that file.
Do not re-derive these numbers from a search summary — the summaries
disagree with the releases and with each other, which is how the error
below survived a day.

**What the £758m weather line actually is — and the correction to my own
flag of 2026-08-22.** The 2026-02 release's footnote 3 says the weather
figures cover *"damage caused by burst or frozen pipes, escape of water,
as well as damage as a result from storms and flooding"*. Read alone,
that says the whole EoW book is inside £758m, which contradicts the £657m
EoW anchor — and that is what I flagged. **It is not a contradiction.**
The 2024-04 release itemises the same line for 2023:

| 2023 weather line | £m |
|---|---|
| storm damage to homes | 133 |
| flooding | 286 |
| **burst pipes** | **153** |
| total (published 573) | 572 |

The water component is **burst pipes only**, a subset of the EoW book —
so 2025's residual, £758m − £244m − £312m = **£202m, is burst pipes**, and
the £657m anchor stands. The "£1,451m alternative headroom" in my
2026-08-22 note does not exist. What does survive: DATA_SOURCES:472 and
:518 still add the weather line and the EoW anchor as separate remainder
items, double-counting the **£202m** they overlap in — an overstatement of
£202m, not £657m.

**Also settled: the storm, flood and subsidence anchors are genuinely
2025.** All three are quoted directly in the 2026-02 release (£244m,
£312m, £307m), as are the £2,450 and £30,000 averages. Source 16's "2025"
label is correct and the per-peril weather totals were not withdrawn.
Storm's 17.78% claim share is therefore the ABI's own implication, not a
modelling artefact — which removes storm as the second suspect behind the
claim-count overshoot and leaves theft carrying it alone.

**Three new findings, none of them yet acted on.**

**1. The level is fitted to one year — but the data does NOT show it is
wrong.** I first wrote this section up as "a record year priced as the
expectation". That overstated it, and both halves of the evidence
dissolved on contact with the arithmetic. Recording the retraction
because the raw table is seductive:

| year | ABI storm | ABI flood | sum | model anchor | model as % |
|---|---|---|---|---|---|
| 2023 | 133 | 286 | 419 | 556 | 133% |
| 2024 | 185 | 226 | 411 | 556 | 135% |
| 2025 | 244 | 312 | 556 | 556 | 100% |
| **mean** | | | **462** | **556** | **120%** |

Storm and flood *are* anchored 20% above their own three-year average.
That is **not** evidence the level is too high. The anchor **is** the
model's mean by construction, and the simulated distribution is strongly
right-skewed — cv ≈ 0.9, median ≈ 25% below the mean — so most years
falling below the mean is what the distribution looks like, not a
finding. `backtest_coverage.py` runs the real test, a bootstrap of
three-year windows, and does not reject the level.

The book-level version dissolved even more completely. The model's
expected loss for seven perils (£2,631m) exceeds the ABI's actual
all-home total for 2022 (£2,330m) and 2023 (£2,550m), which looks
damning — until you notice those are 2022 and 2023 pounds against a
2025-anchored model, and that the ABI's average home claim rose **15% in
2025 alone**:

| claims inflation assumed | 2022→2025 | 2023→2025 | model as % of each |
|---|---|---|---|
| 0%/yr | 2,330 | 2,550 | 113% / 103% |
| 5%/yr | 2,697 | 2,811 | 98% / 94% |
| 10%/yr | 3,101 | 3,086 | 85% / 85% |
| 15%/yr | 3,544 | 3,372 | 74% / 78% |

From about 8%/yr upward the model sits below every observed year, which
is where a seven-peril subset of an eleven-category book belongs. **The
apparent overshoot was mostly a price-basis artefact.**

**What does stand, and needs no data to see:** `E[loss]` is fitted to a
SINGLE year. One year is one draw. The systemic loadings `W_*` get
multi-decade series while the level gets n=1 — which is backwards, since
every year gives you a total, making the mean the better-evidenced of the
two. That is a methodology defect whether or not the current value
happens to land close.

**And the blocker for fixing it: this repo has no claims-inflation index
and no stated "as at" date for the premium.** Until it has both, no
multi-year level can be built and the table above cannot be resolved.
That is the real finding here.

**2. `EOW_FREEZE_SHARE = 0.15` is below what the data implies.** Burst
pipes were £153m of a £657m EoW book in 2023 (0.23) and £202m in 2025
(0.31). Neither year supports 0.15. Raising it pushes EoW's geography
harder onto frost days and changes its systemic loading, so it is a model
change and needs an experiment branch.

**3. `TAIL_FREQ_RATIO = 2.0` was an undocumented knob that sets the tail
width of every published premium — now MEASURED and DOCUMENTED, value
unchanged.** It appeared in `build_model.py` and **nowhere else in the
repo**: no DATA_SOURCES entry, no README, no methodology page. Yet it is
the sole target `calibrate_spatial` solves against, which fixes
`SPATIAL_SCALE`, which drives the year view, `tvar99_euler`, capital and
premium. The house rule is that a parameter without a published anchor
does not ship; this one shipped.

`data/history.csv` had been sitting in the repo with 35 years of per-year
hazard drivers, used for nothing but a chart. `scripts/tail_ratio_from_history.py`
now measures the target against it. The target is a ratio of claim
*counts*, so the proxy has to drive how many homes claim, not how hard
each is hit — `storm_days` (gust ≥ 70 km/h), not `max_gust`:

| proxy | CV | obs max/mean | lognormal 1-in-100 | gamma |
|---|---|---|---|---|
| `storm_days` (primary) | 0.284 | 1.67 | **1.84** | 1.78 |
| `storm_days^1.5` | 0.419 | 2.09 | 2.35 | 2.22 |
| `rain5d` | 0.129 | 1.33 | 1.34 | 1.32 |
| `max_gust` (wrong shape) | 0.077 | 1.17 | 1.19 | 1.19 |

**2.0 sits inside the supported range of 1.78–2.35**, so the knob was
undocumented rather than wrong. It keeps its value and gains a
DATA_SOURCES entry under source 15. `storm_days` shows no significant
trend (−0.039 days/yr, p = 0.77), so fitting its raw spread is legitimate.
What this does *not* establish is that storm days convert to claim counts
one-for-one — and note the proxy choice moves the answer far more than
the fitted distribution does, since `max_gust` would have halved the
tail. A claims triangle would settle it.

**One thing to know before trusting any of this as a time series: the ABI
restates it, and its releases contradict each other.** The 2024-04
release puts 2023 at £573m and calls it the record. The 2025-02 release
puts 2024 at £585m, calls it *"£127 million (28%) higher than … 2023"*
(implying £458m) and names **2022** the previous record. Both cannot be
right. Footnote 3 of the 2024-04 release gives the mechanism — *"This
figure will include claims not yet fully settled"* — but not the
direction. `abi_annual.csv` carries both the 573 and the 458 rows,
flagged. **Pick one vintage of the series and stay inside it; never mix a
figure as-published with a later release's comparative.**

## Claim-count overshoot: attributed 2026-08-22

Reproduce all of this in a second, with no simulation:

```
.venv/Scripts/python.exe scripts/anchor_budget.py
```

**The count overshoot and the money undershoot are one fault, not two.**
103.3% of the ABI's claims on 77.4% of its money means only one thing:
the modelled book's average claim is £4,548 against the ABI's £6,071, a
quarter too cheap. And the sign is wrong. What the model leaves out —
legal expenses, personal possessions, liability, alternative
accommodation — is the *cheap* end of a home book, so stripping it out
should push the modelled subset's average **above** £6,071, not a
quarter below it. Whatever is wrong is a leg carrying too many claims
that are too small, and it will show up in the count budget.

**Six of the seven counts are pinned by something outside their own
leg. One is not.**

| leg | claims | % of 560k | by-product | what pins the count |
|---|---|---|---|---|
| storm | 99,592 | 17.78% | count | ABI 2025 paid AND ABI 2025 average, one release |
| flood | 10,400 | 1.86% | count | ABI 2025 paid AND ABI 2025 average, one release |
| subsidence | 17,228 | 3.08% | count | **WRONG as recorded — corrected 2026-08-27**: FY2025 paid, but a **Q1 2026** average, two releases apart (see DATA_SOURCES #33) |
| escape of water | 164,250 | 29.33% | severity | GoCompare 29.38% — VERIFIED, and closes the triangle |
| fire | 31,000 | 5.54% | paid | Home Office FIRE0201 attended dwelling fires 2024/25 |
| accidental damage | 137,576 | 24.57% | paid | GoCompare 24.53% — VERIFIED (at home + outside) |
| **theft** | **118,421** | **21.15%** | **count** | **nothing: 2018 paid ÷ 2025 average** |

The six leave **99,955 claims (17.85%)** for theft and for everything
unmodelled. Theft takes 118,421 — it **overruns the entire remaining
budget by 18,466 claims on its own**, which is the whole overshoot,
exactly.

**And the remainder is not empty.** Away-from-home accidental damage is
6.46% of the same GoCompare table; it is real, it is inside the ABI's
560,000, and `build_model.py:296` deliberately excludes it from the
model — so it is a charge against the remainder. That leaves **11.39%
(63,779 claims)** for theft, before a single pound of liability or legal
expenses. Theft does not fit on *any* reading of its own documented
vintage envelope:

| theft basis | %/policy | claims | % of 560k | fits? |
|---|---|---|---|---|
| as it ships (2018 paid ÷ 2025 average) | 0.76% | 118,421 | 21.15% | no |
| 2018 paid at the 2018 average, as published | 0.97% | 150,350 | 26.85% | no |
| floor: if claims fell with recorded burglary | 0.58% | 89,900 | 16.05% | no |

**So theft is the largest single cause and is over on every reading —
but it cannot be the only one.** Even the floor of its envelope is
4.66pp (26,121 claims) over, with nothing left for liability. The two
statements "theft ≤ 63,779" (from the budget) and "theft ≥ 89,900" (from
its own documented floor) do not overlap, so one of the other six is
also wrong.

**The next suspect is storm, and there is provenance evidence against
it.** Storm is the only other large count derived by dividing a paid
total by an average: 17.78% of all UK home claims. Its £244m and
flood's £312m are tabled in DATA_SOURCES as "UK domestic claims by
peril, **2025**" (line 26) — but DATA_SOURCES:402 records that the ABI's
2025 full-year release **stopped publishing per-peril weather totals**
and reports one £758m "weather-related damage to homes" line instead.
Both cannot be true of the same release. Source #16's narrative entry
gives no vintage at all, so the storm and flood anchors need their
release identified before storm's 17.78% can be defended or moved.

**The same £758m line is separately self-contradictory on the money
side.** DATA_SOURCES:402 says it covers storm, flood *and* escape of
water. Beside the anchors that cannot hold: £758m − £556m of storm and
flood leaves £202m for EoW, against an EoW anchor of £657m. Then
DATA_SOURCES:472 and :518 size the fire and AD triangles against a
remainder built by adding the £758m weather line and the £657m EoW
anchor as *separate* items — which on line 402's own reading
double-counts EoW. The headroom those two triangles were checked
against is either £794m as documented, or £1,451m — a 1.8× difference.
Settling it needs the ABI release itself.

**None of this is a publishing emergency, for the reason already
recorded:** each peril's EL is paid ÷ policies by construction, so the
premium follows the *money* anchors and is untouched by the count
budget. `el_total` is £171.11/policy and does not move. What a theft
correction would move is the tail. Holding theft's £450m and raising
its severity to fit the budget means fewer, larger claims: EL is
unchanged by construction and the tail should fatten, so `tvar99_euler`,
capital and premium should rise — *expected, not measured; that is what
the experiment branch is for*. Holding the £3,800 average and cutting
the count instead drops theft's paid to ~£242m, which takes 7.9% off EL
— that one is arithmetic, not a simulation result. **The two corrections
move the premium in opposite directions, which is exactly why this needs
an experiment branch with priced evidence and a decision from the user,
not a quiet edit to the `ABI` dict.**

Read this before any Phase 3 work. The buildings/contents split reasons
from frequency, and theft's frequency is the number this section says
is wrong.

## tvar99_vine seed sensitivity, measured 2026-08-22

Six seeds (42-47) through `simulate()` on the real scored frame, both
the published code and its pre-fix parent (1fdfbb5), same seeds, same
spatial calibration. Reproduce with `scripts/seed_sweep.py` — but see
the harness warning at the end, which cost a full wrong run.

**The three questions, answered.**

1. **Did the five fixes worsen it? No.** `tvar99_vine` relative SD
   across six seeds: **12.25% before, 12.40% after**. The 0.15pp is
   inside the noise of a six-seed estimate and is directionally what
   the fatter moment-matched flood severity would do. This closes the
   question the publish left open.

2. **They removed a far bigger one.** Pre-fix, `el_total` itself was
   seed-dependent — relative SD **7.31%**, range 166.52 to 199.80 —
   because the four vine perils took their EL from draws. Premium
   inherited it: **relative SD 6.69%, range 172.23 to 203.58, a 17.24%
   spread**. Post-fix `el_total` is bit-identical across all six seeds
   and premium spans **176.6576 to 176.7926, a 0.076% spread**. The
   premium seed lottery shrank by a factor of ~227. Put plainly: the
   premium published before 2026-08-19 was a draw from a ±17% seed
   distribution, and 174.2409 happened to be near its low end.

3. **The swing is 36%, not 14.7%, and the site does read it.** 14.7%
   was just the 42->43 pair. Across six seeds `tvar99_vine` runs
   **12,172 to 17,301** (household-weighted; thirty seeds later widened the
   unweighted mean to 10,157-17,515). And `build_site.py` injects it into
   `__MEAN_STANDALONE__` and `__DIVERSIFICATION__`, and ships it as a
   CSV column — so "nothing reads it" was wrong about the site even
   though it stays true of the premium path.

**Why it will not settle down.** Two independent causes, and the
second is the interesting one.

*It is a thin-sample estimator.* `tvar()` averages the worst
`k = N_SIM/100 = 200` of 20,000 years. With severity sigma up to 1.30
(fire) that mean is carried by a handful of draws.

*Nothing averages it away.* `base` is drawn ONCE in `simulate()` and
broadcast to every district, so year j is the same state of the world
everywhere and the per-district errors are near-perfectly correlated.
Measured directly: national relative SD divided by median per-district
relative SD is **0.964**. Independent errors across 2,736 districts
(effective N 1,812 on household weights) would give **0.023**. A
national portfolio buys essentially NO error reduction on this number.
Getting to 1% would need ~154x the years — about 3.1M per district.

**Why `tvar99_euler` is fine and premium is fine.** The year view mixes
each district's systemic factor with idiosyncratic noise at the
CALIBRATED spatial loadings, and those are tiny — `SPATIAL_SCALE`
solves to 0.025, giving w/f/s/g of 0.013/0.010/0.015/0.018. Districts
are therefore nearly independent in that view, the portfolio aggregate
does average down, and `tvar99_euler` lands at relative SD **0.33%**
(263.5 to 265.7). Capital and premium ride on that, not on the vine
tail. The two numbers behave differently for a real structural reason,
not by luck.

**What this means for the published page.** The premium map is sound.
The exposure is confined to two injected numbers:

| published | value | thirty-seed range | verdict |
| --- | --- | --- | --- |
| `__MEAN_STANDALONE__` | GBP11,956 | 10,157 - 17,515 (56.1%) | not a reliable point estimate; seed 42 ranks 9th of 30, in the lower third. RETIRED — replaced by `__STANDALONE_LO__`/`__STANDALONE_HI__` |
| `__DIVERSIFICATION__` | 98% | 97.42% - 98.48% | robust — the ratio is stable even though its numerator is not, and rounding to 0dp hides the rest |
| `premium` | 176.6581 | 176.58 - 176.92 (0.192%) | sound |

So the homepage tile survives on its merits; the methodology sentence
"a single policy's standalone TVaR99 is about GBP11,956" did not — the
same model at seed 44 says GBP17,118.

**FIXED and published 2026-08-22.** The sentence now quotes
GBP10,100-GBP17,600 across THIRTY seeds (42-71, run 2), with a footnote
giving the mechanism (shared draws, so the error does not average down)
and the contrast that keeps the rest of the page trustworthy: allocated
share 2.2%, diversification credit 97.42-98.48%, premium 0.19%. Bounds
round OUTWARDS to the nearest GBP100 so the quoted range never claims
to be tighter than what was measured. Nine placeholders are injected
from `data/seed_sensitivity.json`, written by `scripts/seed_sweep.py
--write-json` and regenerated by the manual `seed-sweep.yml` workflow —
NOT hand-written, because hand-written cells are exactly how defect 3
happened.

**Six seeds understated it, exactly as a min-max must.** The first
published range was 11,900-17,200 from seeds 42-47. Thirty seeds widen
it to 10,100-17,600 — the spread goes 36.8% -> 56.1% while the relative
SD barely moves, 12.60% -> 12.87%. That is the expected signature: the
SD is a property of the estimator and converges quickly, the min-max is
a property of the SAMPLE SIZE and keeps growing. Anyone re-running with
more seeds should expect the quoted range to widen again and should NOT
read that as the model degrading. If a stable interval is ever wanted,
quote a percentile band or mean +/- k*SD instead of min-max — the JSON
carries `per_seed` for all thirty, so no re-run is needed to switch.

The three options not taken, and why: drawing the standalone tail
independently per district would let the national mean average down but
would destroy the cross-district comparability shared draws buy;
computing it semi-analytically is real work for a column nothing prices
off; and more simulated years is the only route to a genuinely tight
point estimate — 20,000 -> 1% needs about 154x more, which is not worth
it for a diagnostic. Quoting the range costs nothing and is honest.

The premium survives the wider sweep: 0.192% across thirty seeds, so
the map is still sound and the standalone tail is still the only
exposed number.

**Harness warning, learned the hard way.** `main()` calls
`calibrate_frequency(gdf)` AND `calibrate_spatial(gdf)`. Any script
that drives `simulate()` directly must call BOTH. Omitting the second
leaves `SPATIAL_SCALE` at its module default of 1.0 — a 40x overstated
spatial loading — which silently inflates `tvar99_euler` by 9.7x while
leaving `tvar99_vine` and `el_total` bit-identical to the published
run. The pricing view does not use the loadings and the year view does,
so a harness can look perfectly validated on the columns you happen to
check and be wrong on the ones you care about. `analytic_el_check.py`
omits `calibrate_spatial` legitimately — it only needs marginals.
## Built AND PUBLISHED 2026-08-19: five defects fixed

**Live since 17be4b4** (rebuild run 34, tests run 32202273388 green on
both jobs, both grains verified on the live site). Built on branch
`exp/el-and-flood-fixes` (e025e46, 704866b — branch deleted after merge, commits reachable from main), merged to main at 37f6885
with a guard fix at 8ab6cbc, sector output crossed at 6805445.

The two defects the 2026-08-18 audit left OPEN are fixed, plus three
more found while fixing them. Every scope decision was taken by the
user before any code moved (an eleven-question grilling).

**What the live numbers moved to.** Exposure-weighted premium
174.2409 -> 176.6581 (+1.39%), driven mostly by groundwater's EL going
0.412 -> 1.3398 as it stopped being read off a starved draw. The
sector grain landed at 176.6731, 0.0085% from the district grain.
Analytic EL matches ABI to +0.00% for all seven anchored perils and
the portfolio reconciles at +0.0188% excluding groundwater.

**One caveat on the CI artifact.** CI's rebuild rewrote 276 of 2,736
districts in `data/districts_risk.geojson` versus the laptop build,
entirely in `capital`, `tvar99_euler`, `premium_cc`, `capital_cc` and
`cc_uplift_pct` — max relative change 4.6e-04, last-digit float drift
from a different BLAS in the TVaR Euler allocation. No `el_*` column
and no `premium` value moved. The CI artifact is the published one.

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
13,967). That is a per-district far tail out of 20,000 years and is
inherently noisy; premium uses `tvar99_euler`, not this. I have NOT
established whether these changes made it more seed-sensitive than it
was on main, only that it is sensitive.

> **Resolved 2026-08-22 — see "tvar99_vine seed sensitivity" below.**
> The answer is no: 12.25% -> 12.40% relative SD, immaterial. The same
> measurement found something much larger that these fixes REMOVED, and
> corrected two claims in the paragraph above: the swing is 36% across
> six seeds, not 14.7%, and the site does read this column.

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

**Determinism confirmed, and it caught a provenance slip.** Re-running
`build_model.py` after the defect-5 print change reproduced
`data/districts_risk.geojson` BYTE-IDENTICALLY - the build is
deterministic given RNG_SEED. It also showed `data/year_analysis.json`
changing, which was not nondeterminism but a mistake: the second-seed
script restored the geojson from its saved seed-42 copy after the
seed-43 run, and `build_model.py` writes year_analysis.json too, which
was not restored. Commit 2bfb36e therefore carried a seed-43 year
analysis beside seed-42 everything-else. Fixed in e5b623e;
`docs/years.html` was unaffected, so nothing downstream had consumed it.
**Lesson: build_model.py writes TWO artifacts. Any script that swaps
seeds must restore both.**

**Publishing is the user's call and has NOT been given.** Remaining, in
order: fix defect 5, sector rebuild in the worktree, copy output across,
merge to main, rebuild with commit=true, verify live.

## Phase 2 status: 2a PUBLISHED 2026-08-18, 2c built and NOT published

Both experiment branches were built, verified and priced. The user chose
**"2a only"**: 2a is live (see the section above), 2c stays on its branch.

- **2a - theft commercial denominator** - **PUBLISHED, now on main**
  (`exp/theft-commercial`, eebb5c2+c22aa06 — branch deleted after merge; evidence run 32033558205): rate = burglaries /
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
  first, so the churn numbers in the bullet above are measured against
  the pre-2a baseline. ~~2c's evidence run is now stale.~~ **REDONE
  2026-08-25:** `exp/ct-severity` rebased onto published main (afcf0a5)
  and re-priced by CI 32788080788 - see "exp/ct-severity (Phase 2c),
  re-priced 2026-08-25" above for the current numbers (churn 69.7%, 974
  by >=2 groups, Spearman 0.822, premium level unchanged). Still to do
  if it ships: the site copy pass for the severity prose, and the
  OUTWARD D seam for ct_bands.csv on sector-model - premises.csv already
  has it (fetch_premises.py, 9e777f8: 9,700 sectors, 100.0% placed).
- ~~Known stale: dependence_check.py and sensitivity.py never gained
  the attritional rate columns, so both fail at `_fields`.~~ **FIXED in
  c7a26db** ("Analysis scripts learn the attritional rate columns").
  Both now set th/eow/fire/ad rates plus er_frac and sw_sev. Re-checked
  2026-08-22: this bullet had been stale for some time.

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

- `scripts/seed_sweep.py` — seed sensitivity of every simulated column
  and of the premium, with the national/per-district noise ratio that
  shows whether an error averages down across districts. Established
  that `tvar99_vine` does not (ratio 0.964) while premium does.
  With `--write-json` it writes `data/seed_sensitivity.json`, which
  build_site injects so the methodology page can quote the standalone
  tail as a range. Run it via the `seed-sweep.yml` workflow, not on a
  laptop: a seed is ~3 min in CI (30 seeds = 95 min) and a sleeping laptop kills a long sweep.
  Calls BOTH calibrations — read its docstring before writing any other
  harness that drives `simulate()` directly.
- `scripts/anchor_budget.py` — do the seven per-peril level anchors fit
  inside the ABI's own 560,000 claims? No simulation, runs in a second,
  reads `build_model`'s own `ABI` dict so it cannot drift. Reports which
  of {paid, count, severity} is a by-product for each leg, and therefore
  which counts are pinned by an outside source and which are not. This
  is what attributed the claim-count overshoot to theft — see
  "Claim-count overshoot: attributed 2026-08-22".
- `scripts/tail_ratio_from_history.py` — measures `TAIL_FREQ_RATIO`
  against the 35-year ERA5 driver series instead of asserting it, under
  several proxies and three fitted distributions. Established that the
  shipped 2.0 is inside the supported range. Instant, no simulation.
  Writes `data/tail_ratio.json`.
- `scripts/backtest_coverage.py` — the first check that the model's
  distribution of years contains years that actually happened. Compares
  the simulated national storm+flood annual distribution against the
  ABI's published per-year totals in `data/abi_annual.csv`. Needs one
  full simulation (~40 min on the laptop). Writes
  `data/backtest_coverage.json`.
- `data/abi_annual.csv` — the ABI's annual releases transcribed one
  figure at a time, each row carrying its source URL and a
  published/derived flag. The releases restate and contradict each
  other; read the HANDOFF note before treating it as a clean series.
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

**Where the two resolutions live (moved 2026-08-23).** Both are worktrees
of this one repo, now under one roof:

```
C:/Users/sapta/Documents/Geospacial Map UK                          [main]
C:/Users/sapta/Documents/Geospacial Map UK/.worktrees/sector-model  [sector-model]
```

It used to sit at `C:/Users/sapta/Documents/GeoUK-sector-model`; that path
is gone. `.worktrees/` is gitignored — a worktree nested inside another
worktree of the same repo otherwise appears as ~20 MB of untracked
content and can reach main by accident. Verified after the move: main's
`git status` is clean, no script globs recurse from the repo root, and
all 86 tests pass. **The one-way rule is unchanged: merge main INTO
`sector-model`, never `sector-model` into main** — only its output
crosses, renamed `data/sectors_risk.geojson`.

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

**One open model question, attributed but not decided.** The theft
level anchor is over its share of the ABI's claim count on every
reading of its own vintage envelope, and the storm and flood anchors
need their ABI release identified before storm's 17.78% share can be
defended — see "Claim-count overshoot: attributed 2026-08-22" and run
`scripts/anchor_budget.py`. Both directions of a theft correction move
the published premium, in opposite directions, so this needs an
experiment branch with priced evidence and a decision from the user.
The published EL and premium are not wrong today: they follow the money
anchors, which the count budget does not touch.

Everything else that was ever on a pick-up list is done and live.

## No secrets in this repo

`gh` uses a keyring token; the CEDA token lives only in `~/.ceda_token`
(outside the repo, expired within days of use); nothing sensitive
appears in the code, data, workflows or this file.
