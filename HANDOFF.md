# Handoff — UK Home Insurance Risk Map

**Written:** 2026-08-10 · lives in the repo from now on (supersedes the
old `%TEMP%\uk-risk-map-handoff.md`, which is now just a pointer here)
**Repo:** https://github.com/SMcode-source/uk-home-insurance-risk-map ·
**Live:** https://smcode-source.github.io/uk-home-insurance-risk-map/

## Status: complete, deployed, and the model CHANGED on 2026-08-10

CI green (both jobs), Pages live, **61 tests** passing, tree clean.
Nothing is half-finished and nothing is waiting on anyone.

The headline since the last handoff: **the gust component now runs on
Met Office MIDAS station observations**, not ERA5 reanalysis — the first
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
ABI 2025 payouts, exposure-weighted by census households, capital
Euler-allocated from the portfolio, premiums on TVaR₉₉. Coastal erosion
is in the vine but deliberately outside the premium. A climate scenario
reprices on the EA's future flood extents: +10% exposure-weighted over
2,087 English districts.

## The experiment-branch pattern (how model decisions get made here)

Twice used, twice decisive — reuse it for any future model input change:

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

## Evidence tooling now in the repo

- `scripts/compare_rebuild.py` — experiment artifact vs published model
  (premium level, churn, movers). Both model decisions above used it.
- `scripts/compare_gust_surfaces.py` — two gust point sets IDW'd to
  district level through the model's own code path.
- `tests/test_layout.py` — the browser-level invariants (Playwright;
  skips without it). `tests/test_midas.py` — the BADC-CSV selftest.

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

- **Sector-level modelling** is a decision, not a task: the geometry
  exists (`derive_sectors.py` → 10,398 sectors, partition asserted
  exact), but wiring it in means ~4× the raster work across every
  hazard fetch, exposure re-apportionment, and a longer simulate. First
  probe if green-lit: validate the derived Scottish sectors against
  Scotland's official polygons to measure the method's error.
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
