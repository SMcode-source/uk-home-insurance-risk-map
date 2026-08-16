# Handoff — UK Home Insurance Risk Map

**Written:** 2026-08-12, audited and refreshed 2026-08-16 · lives in the
repo (supersedes the old `%TEMP%\uk-risk-map-handoff.md`, which is now
just a pointer here)
**Repo:** https://github.com/SMcode-source/uk-home-insurance-risk-map ·
**Live:** https://smcode-source.github.io/uk-home-insurance-risk-map/

## Status: complete, deployed, TWO resolutions published (2026-08-12)

The site now publishes the model at **two grains side by side**:
`/map.html` over 2,736 postcode districts and `/sectors.html` over
10,398 derived postcode sectors. One template builds both pages, so
they cannot drift; the layout suite runs every map invariant against
both. **72 tests**, CI green, Pages live. The methodology page also
draws the Hull comparison (districts vs sectors on the climate layer)
as an inline SVG generated from the published GeoJSON at build time —
a screenshot would go stale at the next rebuild; this cannot.

## In flight 2026-08-16: theft peril on `exp/theft-peril` (Phase 1)

The model prices £55.68 of the ABI's £219 average premium because it
stops at four catastrophe perils; the roadmap (agreed 2026-08-16) adds
the attritional lines, theft first. State right now:

- **Data on main** (7bb3fdc): `data/burglary.csv` — 668,609 burglaries
  from the police.uk 36-month archive (2023-07..2026-06), spatially
  joined to the model's own district polygons by
  `scripts/fetch_burglary.py`. Traps and anchors in DATA_SOURCES.md #25
  (snap points, commercial contamination, BTP's Scottish leak, the
  2018-vintage ABI theft-paid figure and why propensity cancels).
- **Model on the branch** (32a9d0c): independent compound leg OUTSIDE
  the vine (burglary has no weather root), drawn LAST in the seeded
  stream so the four weather perils simulate bit-identically — the
  rebuild diff is the theft addition and nothing else. Level pinned to
  ABI theft paid/average/policies (£29.03/policy); geography is each
  district's own burglary rate, capped at the household-weighted p99.9
  (office cores are burgled as shops, not homes), Scotland overridden
  with the national housebreaking rate. 74 tests green.
- **Evidence is IN (run 31970674869, the third — see below): premium
  £59.07 → £88.11 (+£29.04), of which el_th £29.03 and capital +£0.01.**
  The theft level lands on the ABI calibration to the penny, theft earns
  full diversification credit under portfolio-TVaR capital, and every
  weather-peril output is bit-identical to published (verified column by
  column). Churn is large and REAL: 77.9% of districts change rating
  group, 1,281 by ≥2 — theft geography is nearly orthogonal to cat
  geography (corr 0.04), so pricing it re-ranks the book. City cores go
  to group 10 (B2 £25→£240); el_th median £22, p95 £71, max £215 at the
  p99.9 winsorisation cap. Dilutions to disclose in site copy if
  accepted: uplift_pct 11.0%→8.2% weighted, climate uplift 8.6%→5.6%
  (same £ of repricing on a bigger base). The USER decides.
- **The first two evidence runs were themselves the evidence process
  working.** Run 1 (31969240862) failed the published-geojson identity
  test — el_total no longer equalled the four-peril sum, the diff being
  el_th to the penny; the identity now includes theft with a
  missing-column-reads-as-zero fallback that cannot mask a partial
  regression. Run 2 (31969920992) priced a MIS-SPECIFIED model and the
  numbers said so: premium +79.9%, +£13/policy of phantom capital and
  el_th +17% over calibration. Two lessons that apply to EVERY
  attritional peril still to come (EoW, fire, AD):
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
     the tail columns. Both now guarded by tests.
- **Not done, deliberate**: sectors get theft only if the user accepts
  it for districts (needs sector-resolution burglary aggregation on the
  sector-model branch); EoW/fire/AD are next in Phase 1; the VOA
  non-domestic premises count is the proper fix for the commercial
  contamination (Phase 2).

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
