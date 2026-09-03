# Limitations, methodology and data provenance

**Written 2026-08-29.** Companion to `DATA_SOURCES.md` (what the sources
are) and `HANDOFF.md` (what happened when). This file answers a different
question: *for every decision in the model, why was it made that way, and
what does it cost?*

It is deliberately unflattering. Anything here that reads as a weakness is
a weakness, and the ones that would change a published number are marked
**MATERIAL**.

---

## 1. Is there any synthetic or fake data in the model?

**No.** Audited 2026-08-29 across the whole scoring path. Specifically:

| check | result |
|---|---|
| `np.random` / RNG anywhere in **scoring** | **None.** The only two RNG calls (`build_model.py:1049`, `1243`) are inside the Monte Carlo simulation and are seeded (`RNG_SEED = 42`). Every district score is deterministic from real inputs. |
| Synthetic datasets in the repo | **One**, and it never touches the model: `gusts_from_midas.py:278` builds a fake MIDAS directory tree to self-test the parser. Test scaffolding only. |
| Hardcoded per-district values | **None.** No district is given a value by hand anywhere. |
| Placeholder constants presented as anchors | **None now.** One shipped once — see §6 — and the guard that stops it recurring is `SPLIT_ANCHORED`. |

What *does* exist, and must not be confused with fake data, is three
different things:

1. **Imputations** — a real, documented rule filling a real, documented
   gap in coverage (§5). Every one prints its own count at build time.
2. **Calibration scalings** — raw hazard scores rescaled to published ABI
   totals (§3). Large, deliberate, and the point of the design.
3. **Unanchored assumptions** — three numbers with no published source,
   fenced from publication in code (§6).

All three are disclosed. None is invented data dressed as observation.

---

## 2. The one architectural decision everything else follows from

The model **separates LEVEL from GEOGRAPHY**, because the available data
forces it to:

- **Level** comes from ABI national published totals. There is no public
  register of UK home insurance claims by postcode or district —
  insurers hold claims history commercially, and the ABI publishes
  national aggregates only. I checked the most recent subsidence release
  (Q2 2026): no regional split of any kind.
- **Geography** comes from granular *physical hazard* data — geology,
  flood extents, wind, burglary points, fire incidents.

So `calibrate_frequency` pins each peril's exposure-weighted national
frequency to its ABI figure, and the hazard scores decide only the
*relative* ordering of districts. This has a consequence worth stating
plainly: **the model's district ordering has never been validated against
actual claims, because no such data is published.** It is validated
against physics and against the national level, and that is all.

The scalings applied to reach the ABI level are large:

| peril | raw score frequency | ABI target | scaling |
|---|---|---|---|
| weather | 3.252% | 0.643% | **×0.198** |
| flood | 0.311% | 0.069% | ×0.221 |
| subsidence | 0.958% | 0.115% | **×0.120** |
| theft | 0.772% | 0.580% | ×0.751 |
| escape of water, fire, accidental damage | — | — | ×1.000 |

A ×0.12 scaling on subsidence means the raw geological susceptibility
score over-predicts claim frequency eightfold. That is expected — not
every clay-founded house on shrinkable ground claims — but it does mean
the *shape* of the hazard curve is doing all the work and any error in
that shape is not corrected by the calibration.

**Groundwater is not calibrated at all.** It is pegged at 10% of flood
(`GW_SHARE_OF_FLOOD = 0.10`) because the ABI does not report it
separately — it sits inside flood. This is a modelling choice with no
anchor, and groundwater is 0.8% of expected loss, so it is disclosed
rather than fixed.

---

## 3. Per-peril provenance, and what each driver actually is

EL per policy and share of the **£164.09 priced** total. Note which line
is outside it:

| peril | EL | share | driver | resolution | coverage |
|---|---|---|---|---|---|
| Escape of water | £42.39 | **25.83%** | air-frost days | 1991–2020 **climatology** | UK — **no year-to-year variation** |
| Fire | £28.00 | 17.06% | MHCLG dwelling-fire incidents | fire-authority area | GB |
| Theft | £22.04 | 13.43% | police.uk burglary points | **street level** | E&W; Scotland at council resolution |
| Flood | £20.13 | 12.27% | EA NaFRA2 / NRW FRAW / SEPA zones | polygon fractions | UK; depth England only |
| Subsidence | £19.81 | 12.07% | BGS clay shrink–swell | 1:625,000 | GB |
| Storm | £15.74 | 9.59% | wind, WDR, rain days, 191 gust stations | 5–12 km | UK |
| Accidental damage | £14.65 | 8.93% | census child-share | LSOA | GB |
| Groundwater | £1.34 | 0.82% | EA alert areas | postcode flag | **England only** |
| *Coastal erosion* | *£2.85* | *—* | *EA NCERM frontages; NatureScot Dynamic Coast* | *frontage / eroded-area polygons* | ***England + Scotland on two bases (`er_basis`); no Wales; UNPRICED*** |

**Coastal erosion is deliberately outside `el_total`** — "no policy pays
it" (`build_model.py:1438`). Standard UK home insurance does not cover
coastal erosion, so it is carried as information (`el_total5`) and never
reaches the premium. Any share quoted against a nine-peril total is wrong;
the denominator is the eight priced perils.

### Cleaning and adjustment decisions, with reasoning

**Subsidence — superficial deposits at half weight (`SUP_WEIGHT = 0.5`).**
BGS 625k publishes no deposit *thickness*, so a 0.5 m gravel skin and a
20 m clay sequence are indistinguishable in the data. Full weight would
assert a confidence the source does not support; half weight says "drift
matters where present" without pretending to know how much.

**Subsidence — two superficial classes excluded.** *Peat* subsides badly
but by consolidation and oxidation, not shrink–swell; pricing it inside
this peril would conflate two mechanisms under one calibration (15,728
km², 11.9% of cover). *"Drift geology not mapped"* is excluded because it
is an absence of survey, not a deposit — scoring it would invent data.

**Theft — commercial premises stripped.** police.uk "Burglary" includes
commercial break-ins, so districts with almost no residents show rates no
household experiences. Capped at the household-weighted p99.9 (3.399%/yr);
14 commercial-core districts clipped.

**Fire — same treatment**, cap 0.3453%/yr at p99.9, 4 districts clipped.

**Flood severity — blended, then re-derived.** Fluvial/tidal (£35,000) and
surface water (£18,000) blend to £29,322 against the ABI's £30,000
headline; the target is re-derived from the blend so flood still
reproduces its paid anchor exactly.

**Coverage decided by boundary, not by data.** Several EA products stop at
the English border. Inferring coverage from the data kept failing in ways
that looked plausible — a Welsh district with no depth mapped reads as
"nothing over 0.2 m", and Dundee's missing climate-change extent read as a
70-point *fall* in flood risk. Coverage now comes from ONS country
boundaries, and a district must be ≥95% inside England
(`ENGLAND_MIN_SHARE = 0.95`) to take English data; the ~20 genuine
straddlers (Portishead, Chester, Berwick, Welshpool) take the neutral
fallback rather than a reading built from whichever half happens to be
mapped.

---

## 4. Can escape of water be broken into types?

**It already is, once — and that split is anchored.** `EOW_FREEZE_SHARE
= 0.31`: 31% of EoW is freeze-attributable and varies spatially with
frost days; the remaining 69% is flat. That 0.31 is a measurement, not a
guess — the ABI's weather line itemises burst pipes at £153m (2023) and
£202m (2025), which against EoW's 19.3% share of the home book imply
0.311 and 0.307, two independent years agreeing to within 0.004.

**The frost map is aimed at 1991–2020, and that was tested rather than
assumed.** UK frost days are falling fast — −0.326 days/year, p = 0.0002,
about −7.5% of the mean per decade, 49.0 days across 1961–1990 against
38.9 across 1991–2020 — so the obvious objection is that the climatology
is out of date. `measure_frost_era.py` re-derived the map on four
candidate windows and read each against *within-era controls* that hold
the climate fixed and vary only the sample, because a shorter, more
recent window is a noisier estimate as well as a more current one. The
two windows worth considering move the relativity far less than the
noise does: 1996–2025 by |Δrel| p95 = 0.045 and 2006–2025 by 0.091,
against 0.158 for two 15-year halves of the published window itself.
Even the 1961–1990 map differs from today's by no more than two
arbitrary decades inside the current window differ from each other. Both
resolutions agree to the third decimal. **Re-aiming would buy a noisier
estimate of the same map, so the window stays.**

**What that leaves is a real limitation, and it is structural.** Frost
enters as each district's days *divided by the national
household-weighted mean*, so a decline that is roughly proportional
across the country cancels exactly — the model cannot feel a warming
winter at all, however far frost falls. Only `EOW_FREEZE_SHARE` could
carry that signal, and no UK publication attributes escape-of-water
claims to freeze *by era*, so there is nothing to calibrate a declining
share against. The share is priced as a dose-response rather than
adjusted on judgement (see the temperature page), and is carried at its
anchored 0.31.

**Further splitting the flat 69% is currently blocked, and not for want
of trying.** Gate 3 searched for a burst-pipe breakout with geography and
found none: three ABI series exist, two disagree by a third, the 2025
figure is not burst pipes at all, and no geographic split is published.
The natural sub-types — appliance failure, plumbing/joint failure,
heating-system leaks, overflow — have no published UK cost split and,
more importantly, **no spatial driver in the model**, so splitting them
would change nothing. A split only earns its place if each part has a
different geography or severity.

**What would unblock it: dwelling age and plumbing vintage.** Old pipework
fails more. Two open sources carry it (§8).

---

## 5. Imputations — the complete list

Every one of these prints its own count at build time.

| where | rule | scale | why |
|---|---|---|---|
| Groundwater | non-England districts get `GW_BACKGROUND = 0.02` | **623 of 2,736 districts** | EA alert areas are England-only. NRW/SEPA publish no equivalent. |
| Theft, Scotland | housebreaking at **council** resolution (32 areas, three-year mean 7,794/yr → 0.039–0.632%/yr), apportioned by household share | **442 districts, 32 distinct values** | Police Scotland publishes no incident-level data; the cube stops at council area. |
| Surface-water depth | districts with no mapped depth fall back to multiplier 1.0 | **651 of 2,736** | NRW and SEPA publish no depth product — checked directly against both services 2026-09-03, not assumed (DATA_SOURCES #38). |
| Coastal erosion | districts no projection reaches score **zero** | **2,205 of 2,736** | NCERM is England-only; Dynamic Coast closed Scotland's 442 on 2026-09-03 (179 of them are coastal). Wales and NI have no published projection at all. |
| Gridded CSV layers | missing districts take the **national median** | varies, printed per layer | A missing grid reading is not a zero reading. |
| Geology slivers | districts with no polygon intersection take the nearest polygon | small | Boundary artefacts. |

**These are wrong numbers, not merely uncertain ones.** Welsh eroding
coastlines still score *zero*, which reads on the published map as no
Welsh erosion rather than no Welsh data. Scotland read the same way until
2026-09-03; it now carries Dynamic Coast's projections on a clearly
marked different basis. Groundwater still has the old shape at 83.3%
England.

Their materiality differs sharply, though, and the distinction matters:

- **Coastal erosion is NOT material to the premium.** It is outside
  `el_total` entirely (§3), so the gap degrades the *information* the map
  presents, not any priced number. That is exactly why Scotland was worth
  closing on 2026-09-03 and why it could be: an unpriced layer can take a
  second source on a different basis, provided the basis is published
  alongside it — which `er_basis` does, per district. Wales is what is
  left, and it is now captioned rather than silently zero.
- **Groundwater IS priced** (0.82% of EL), so its England-only basis and
  flat 0.02 background do reach the premium — but at that weight the
  effect is small.
- **Surface-water depth was the materially damaging one left**: it sits
  inside flood (12.27%). Scottish theft sat beside it inside theft
  (13.43%) until 2026-09-01, when the flat national rate was replaced by
  council geography (§7); what remains there is a 32-value step
  function, not a single value.

**Scottish theft's *basis* has now been measured, and it is smaller than
it looks** (run 33449273312, `scripts/price_scotland_theft.py`, artifact
`data/scotland_theft_pricing.json`). The override uses 7,381 — *Total*
Housebreaking, all premises — while Phase 2a gave England and Wales a
residential-share denominator and never revisited the comparator. The
obvious reading is that Scotland is inflated by 7381/5192 = 1.42×. It is
not:

| | share of burglary that is residential | inflation carried |
|---|---|---|
| E&W, as the model computes it | 91.2% retained by `hh/(hh+prem)` | — |
| E&W, ONS Table A5a (Apr 2023–Mar 2026) | 68.5% | **1.33×** |
| Scotland, Table A6 (2024-25) | 70.3% domestic | **1.42×** |

Two errors in the same direction that nearly cancel: like-for-like,
Scotland is over-stated by **1.07×**. Priced, that is **−£0.53 to −£0.96
on the mean Scottish premium** (£172.09 published), 48–82 districts
moving one rating group, none moving two, and the UK headline unchanged
at £169.65. Correcting Scotland *alone* — the naive fix — would move it
−£2.47 to −£4.23, four to five times too far. The two taxonomies line up
closely enough for the comparison to be fair: E&W residential 68.5%
against Scottish domestic 70.3%, E&W home-only 51.1% against Scottish
dwelling 49.6%.

**Period IS a confound, and it points the other way — this corrects
what was written here on 2026-09-01.** The original note said period was
not a confound: Scottish housebreaking fell 18% between 2023-24 and
2024-25, so a backward multi-year mean would sit above 7,381, but the
police.uk archive runs 2023-07 to 2026-06, is centred on December 2024,
and the 2024-25 constant straddles that centre. That reasoning was sound
and the premise was wrong. It assumed 2024-25 was the newest published
Scottish year, because the Recorded Crime in Scotland workbook is where
the constant came from. **statistics.gov.scot carries 2025-26** — 6,968
housebreakings, a complete year (315,357 All Crimes against 299,111 the
year before). So 33 of the archive's 36 months are published, not 21:

| overlap with 2023-07…2026-06 | housebreaking |
|---|---|
| 2023-24, Jul–Mar (9 months) | 9,033 × 9/12 = 6,775 |
| 2024-25 (12 months) | 7,381 |
| 2025-26 (12 months) | 6,968 |
| 2026-27, Apr–Jun (3 months) | not yet published |

Month-weighted over the 33 published months, the archive-matched figure
is **7,681/yr — 4.1% ABOVE the constant in use**. Scotland is
*under*-stated on period by roughly as much as the basis work found it
*over*-stated on definition, and in the opposite direction. Netted, the
like-for-like over-statement is nearer 1.03× than the 1.07× above.

**The definition correction was not applied; the period one effectively
has been.** 7,381 over 5,192 stands: the two definitional errors nearly
cancel, and correcting Scotland alone would move it four to five times
too far. But shipping council geography on 2026-09-01 (§7) also moved
the *window*. The model now reads the three published years 2023-24 to
2025-26, whose mean is **7,794/yr** — 5.6% above the old constant, and
within 1.5% of the 7,681 the archive overlap implies. The *geography*
gap this section used to rank as the materially damaging half is closed
to council resolution.

---

## 6. Unanchored assumptions

Three numbers in `SPLIT_BUILDINGS` have no published source and cover
**42.5% of claim cost**:

```
"wx":  0.85     "eow": 0.75     "ad":  0.45
```

They are kept so the buildings/contents mechanism runs and its sensitivity
can be computed. The code fences them: only the five anchored perils
(`SPLIT_ANCHORED = {sub, th, fire, fl, gw}`) are split on the site, and
**the portfolio buildings share is published as a 31.8%–79.5% BOUND, never
as an estimate.**

This guard exists because the mistake already happened: before 2026-08-25
the four anchored perils sat at placeholder values (0.20/0.70/0.65/0.80)
against real anchors of 0.242/0.78/0.48/0.48, and shipping in that state
would have published placeholders and called them anchors.

Also unanchored, and worth naming:

- **`SEV_SIGMA`** — lognormal severity dispersions (sub 0.90, wx 1.10,
  fl 0.90, gw 0.80, er 0.35…). These have no published source, but Gate 3
  proved analytically and by measurement that **every σ cancels out of
  both EL and capital**, so they cannot move the premium. Guarded by
  `test_severity_sigma_cannot_move_capital`.
- **`GW_SHARE_OF_FLOOD = 0.10`** — see §2.
- **`SMD_CAP = 150 mm`** in the new climate work — not a model parameter;
  nothing reads it yet.

---

## 7. Limitations ranked by what they would actually change

**MATERIAL — would change published numbers**

1. **The largest peril has the weakest driver.** Escape of water is 25.8%
   of expected loss and its only geography is a 1991–2020 frost
   *climatology* with no year-to-year variation, on 31% of the peril. The
   other 69% is spatially flat. Nothing in the model distinguishes a
   Victorian terrace's plumbing from a 2015 new build's. The frost map
   itself is sound — re-aiming its window was tested and rejected on
   measurement (§4) — but the model is blind to the *level* of frost by
   construction, so a warming winter cannot reach the premium. **The
   dwelling-age fix is blocked for free (checked 2026-09-03):** EPC gives
   the age *stock* at postcode grain, but no published UK source gives EoW
   claim *frequency* by age to anchor it to, and the ABI's granular claims
   data is subscription-only. See §8 row 1.
2. **Surface-water depth is England-only** — 651 districts fall back to a
   flat severity multiplier inside flood, which is 12.3% of EL. With
   Scottish theft closed to council resolution below, this is now the
   largest *priced* coverage gap. **It is also the one there is no free
   route to closing (verified 2026-09-03):** SEPA's open REST publishes
   surface-water hazard as `METRIC='Extent'` and nothing else, and NRW's
   GeoServer has exactly one layer with "depth" in its name and it is peat
   depth. So the largest priced gap and the largest unclosable gap are now
   the same item. See §8 and DATA_SOURCES #38.
3. **Theft's Scottish geography stops at council area.** It was one flat
   rate across all 442 districts until 2026-09-01, when the 32 councils'
   housebreaking counts replaced it (§5), apportioned onto districts by
   household share — a 16× spread where there had been none, worth
   **+£0.46** on the mean Scottish premium, **nothing** at the headline,
   and 126 Scottish districts moving one rating group. What remains is a
   32-value step function: districts inside one council are still
   indistinguishable from each other, against street-level points in
   England and Wales. The residual gap is bounded by whatever
   within-council variation the council totals hide, and no free source
   resolves it further.
4. **Accidental damage is driven by census child-share.** That is a
   demographic proxy for "households with children have more accidents",
   not a hazard measurement. 8.9% of EL rests on it.
5. **Fire resolves only to fire-authority area** — far coarser than the
   district grid it feeds.

**METHODOLOGICAL — affect confidence, not the current numbers**

6. **No claims-based validation of geography is possible** (§2).
7. **Subsidence geology is 1:625,000** — regional scale, not property
   scale, against a peril that varies house by house with foundation
   depth and tree proximity.
8. **Hargreaves-Samani PET overestimates UK evapotranspiration** by about
   a third (668–697 mm modelled against a true 450–550). A known weakness
   of the method in humid maritime climates. The bias does **not** cancel
   in the drought index because the deficit subtracts rainfall.
   *Measured 2026-08-31 (`scripts/check_pet_sensitivity.py`, 1 km and
   5 km): the bias moves the index's LEVEL, which the ABI calibration
   re-pins, and not its MAP (rank correlation ≥ +0.998 at PET × 0.85
   and × 0.70) — so the published relativity survives it. The deficit's
   millimetre values are still not soil-physics quantities and are never
   published as such; Hydro-PE (doi:10.5285/9275ab7e-6e93-42bc-8e72-
   59c98d409deb) is the citable Penman–Monteith replacement if a level
   is ever needed.*
9. **HadUK-Grid 1 km is interpolated from a station network**, so 1 km
   spacing is not 1 km of independent information. It buys district
   *separation*, not necessarily district *accuracy*.
10. **EPC-style stock data is absent entirely** — no dwelling age, type,
    or construction material anywhere in the model.

---

## 8. How each limitation could be fixed, and with what

Candidate sources, with the merge that would be needed. **None of these
has been implemented; several need verification before they can be
trusted.**

| # | limitation | candidate source | merge | confidence |
|---|---|---|---|---|
| 1 | EoW flat 69%, no dwelling age | **EPC Open Data** (England & Wales) — ~30m certificates with `CONSTRUCTION_AGE_BAND` (12 bands, pre-1900 → 2012+) and postcode, free and programmatic | postcode → district, share by age band | **BLOCKED on the ANCHOR, not the data (checked 2026-09-03).** EPC itself is open and granular as described. What does not exist for free is any published UK figure for EoW claim FREQUENCY by dwelling age: the ABI publishes national aggregates and puts granular claims behind its subscription industry-data service (zero budget → permanently out of scope), and the English Housing Survey publishes damp/leak *stock condition* by age, which is not claims. Deriving a relativity from stock condition would be an invented correction factor — the rule below, and `SPLIT_ANCHORED`, forbid it. This is the wall Gate 3 hit for burst pipes, hit again from the other side. |
| 1 | same, unbiased | **VOA Council Tax stock of properties** — build-period counts, complete stock | LSOA/LA → district | Medium — complete but coarser geography |
| 1 | Scotland | **Scottish EPC Register** (separate from E&W) | same | Medium — needs checking |
| 2 | Coastal erosion, **Scotland** | **Dynamic Coast** phase 2 (NatureScot, OGL) | eroded-area polygon → district, area-weighted | **DONE 2026-09-03** (DATA_SOURCES #39): 179 of 442 Scottish districts, 79.7 km² by 2100, worst AB23 at 1.891%. The basis gap that looked expensive was measured and is not: only **1.88%** of the projected loss sits at a defended frontage, against England's 0.377 SMP/NFI ratio, so Dynamic Coast's management case and NCERM's SMP agree to within 2% *for Scotland*. What survives is the climate rung — RCP8.5-95th against England's 70th — and it is disclosed, not corrected. Original assessment, which held up: **High (verified 2026-09-03).** Eleven open feature services plus `DC2_Main_results` and `DC2_LES_results`. Scotland has a **climate ladder** — RCP8.5-95th and RCP2.6, each at 2050 and 2100 — which maps onto NCERM's `_hi`/`_lo` allowance columns; ErodedArea totals are 79.7 / 32.5 km² at 2100 and 17.9 / 12.9 km² at 2050. **The real mismatch is the management axis, not the climate one:** NCERM publishes SMP (defences maintained) against NFI (defences lapse), while Dynamic Coast publishes **one** management case — "do nothing", meaning no new intervention but existing defences physically present, capping retreat at **25 m** where they exist. That is nearer SMP than NFI, but it is one point on an axis England resolves into two, and there is no Scottish central (70th-percentile) case at all. DATA_SOURCES #38. |
| 2 | Coastal erosion, **Wales** | — | — | **The whole of what is left of this row, and still blocked (verified 2026-09-03).** NRW's GeoServer publishes SMP *policies* (`nrw_shoreline_management_plan_policies`) but no projected-shoreline geometry, so a Welsh erosion extent cannot be built the way NCERM's is. With Scotland closed the layer is England + Scotland, and Wales is captioned on the map and in the methodology rather than left as a silent zero. |
| 2 | **Surface-water depth outside England** | — | — | **No free route (verified 2026-09-03).** SEPA publishes surface-water hazard at `MAP_TYPE='Hazard'`, `METRIC='Extent'` only, and its `Secure`/`Utilities` REST folders list no services at all; NRW's 4,374 published WMS layers contain one "depth" layer and it is `geonode:nrw_ph2_lowland_peatland_peat_depth`. The England-only claim in §3 and §5 is now checked rather than asserted. |
| — | *(adjacent, not a fix)* | **NRW `NRW_NATIONAL_FLOOD_RISK_SURFACE_WATER_ECON/PEOPLE/ENVIRO`**; **SEPA `NFRA_Flood_Risk_Grid_Latest`** (26,614 cells, `aad_score_res` banded 1–7) | — | These are *consequence*/annual-average-damage products. They cannot serve as severity multipliers — AAD already contains frequency, so multiplying it into a calibrated frequency double-counts. They are, however, a candidate **external validation of flood ordering** outside England, which §2 records the model has never had. |
| 2 | Groundwater outside England | **BGS susceptibility to groundwater flooding**; SEPA/NRW flood maps | polygon fractions per district | Medium — BGS product is GB-wide, but is *susceptibility*, not EA's alert-area basis, so the two do not merge cleanly |
| 3 | Theft, Scotland | **Recorded Crime in Scotland** by local authority | LA → district apportionment by households | **DONE 2026-09-01.** Shipped from the statistics.gov.scot cube (DATA_SOURCES #37), not the workbook — the cube carries all 32 councils and a fresher year. LA is still far coarser than street level, so this improved on one flat rate without matching E&W, exactly as forecast here. |
| 4 | Accidental damage proxy | EPC/VOA stock type + census tenure | district | Low — no anchor for what AD actually correlates with |
| 5 | Fire resolution | **Home Office incident-level fire statistics** if published below authority level | district | Low — needs checking |
| 8 | PET bias | **Hydro-PE** (CEH, doi:10.5285/9275ab7e-6e93-42bc-8e72-59c98d409deb), the citable Penman–Monteith replacement; or Met Office MORECS/MOSES | replace the PET term | Optional. This row read "**Required before the SMD index ships**" until 2026-08-31, when the index shipped without it: the bias was measured to move the LEVEL, which the calibration re-pins, and not the MAP (rank correlation ≥ +0.998), so it stopped being a blocker and became a level-only improvement. See §7.8. |

**Every source in this table is free.** The project's budget is zero
(decided 2026-08-31, see DATA_SOURCES), and that decision costs this
table nothing — EPC Open Data, VOA, NRW, Dynamic Coast, BGS's open
products, Recorded Crime in Scotland, Home Office fire statistics and
Hydro-PE are all open, some behind a free registration. What the budget
does close is elsewhere: the licensed PAF/AddressBase and BGS
superficial-thickness routes, which would have improved exposure and
`SUP_WEIGHT`. Those are now permanent limits rather than future work.
The claims triangle in §7 was never a money question — it is not
purchasable at any price.

**Rule that governs all of the above:** a source only ships if it carries a
published, citable anchor. No correction factor may be invented to make a
number look right — that rule is what killed the Phase 2b age slice, and it
is why §7.8 is recorded as blocking rather than quietly patched.

Merging two sources onto one peril also needs care about **basis**: EA
alert areas and BGS susceptibility measure different things, as do
police.uk "Burglary" and Recorded Crime in Scotland's "housebreaking". The
Gate 3 failure was exactly a basis mismatch — three ABI series, two
disagreeing by a third — and it cost a full gate.

---

## 9. Rules that must continue to hold

- No model parameter ships without a published anchor.
- Placeholders never ship as anchors (`SPLIT_ANCHORED` is the guard).
- The portfolio buildings share is a bound, never a headline estimate.
- Coverage is decided by boundary, not inferred from the data.
- Both grains (districts and sectors) publish in one push.
- Model changes require priced evidence from an experiment branch, and
  publishing is the owner's decision.
