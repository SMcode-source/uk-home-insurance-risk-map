# Data sources register

Every external dataset used by the model: what it is, where it comes from, how
it is fetched, its licence, and any access quirks discovered along the way. All
sources are **open data** (Open Government Licence v3 unless noted). Access
dates: 2026-07-29/30; 2026-08-01 for sources 20–21; 2026-08-08/09 for 23–24.

| # | Dataset | Publisher | Fetched by | Local file(s) |
|---|---------|-----------|------------|---------------|
| 1 | UK postcode district polygons | missinglink/uk-postcode-polygons (OS/Wikipedia-derived) | `git clone` | `data/uk-postcode-polygons/` (120 GeoJSONs, 2,736 districts) |
| 2 | BGS Geology 625k bedrock | British Geological Survey | `scripts/fetch_bgs.py` | `data/bgs_625k_bedrock.geojson` (~34 MB, 11,244 formations) |
| 2b | BGS Geology 625k superficial | British Geological Survey | `scripts/fetch_bgs.py --superficial` | `data/bgs_625k_superficial.geojson` (~24 MB, 10,651 deposits) |
| 3 | Winter mean wind speed 5 km (UKCP18 baseline) | Met Office Climate Data Portal | `scripts/fetch_metoffice.py` | `data/metoffice/wind.csv` |
| 4 | Annual wind-driven rain index, SW walls, 5 km (UKCP18 baseline) | Met Office Climate Data Portal | `scripts/fetch_metoffice.py` | `data/metoffice/wdr.csv` |
| 5 | Annual count of ≥10 mm rain days 1991–2020 (HadUK-Grid obs) | Met Office Climate Data Portal | `scripts/fetch_metoffice.py` | `data/metoffice/rain10.csv` |
| 6 | Annual precipitation 1991–2020, 12 km (HadUK-Grid obs) | Met Office Climate Data Portal | `scripts/fetch_metoffice.py` | `data/metoffice/precip.csv` |
| 7 | Rivers & sea defended flood extents, present day (NaFRA2) | Environment Agency | `scripts/fetch_flood.py` | `data/flood_fractions.csv` (derived) |
| 8 | Flood Map for Planning / FRAW rivers+seas merged zones | Natural Resources Wales | `scripts/fetch_flood.py` | ↳ same |
| 9 | River & coastal flood maps (medium/low likelihood) | SEPA | `scripts/fetch_flood.py` | ↳ same |
| 10 | Risk of Flooding from Surface Water (NaFRA2 RoFSW) | Environment Agency | `scripts/fetch_surface_water.py` | `data/sw_fractions.csv` (derived) |
| 11 | FRAW surface water & small watercourses | Natural Resources Wales | `scripts/fetch_surface_water.py` | ↳ same (+ `data/sw_wales20.csv` via `merge_sw_wales.py`) |
| 12 | Surface water flood maps (medium/low likelihood) | SEPA | `scripts/fetch_surface_water.py` | ↳ same |
| 13 | Flood risk: postcode search tool data (incl. GWTR_RISK groundwater flag) | Environment Agency | manual download (URL below) | `data/ea_postcode_risk.csv` (36 MB) → `data/gw_fractions.csv` via `scripts/fetch_groundwater.py` |
| 14 | Daily 10 m wind-gust maxima 1990–2024 (ERA5 reanalysis) | ECMWF via Open-Meteo archive API (CC-BY 4.0; **not** Met Office) | `scripts/fetch_gusts.py` | **fallback only since 2026-08-10** — regenerates an ERA5 `data/gusts.csv` without a CEDA account (90 grid points, rp50 124–196 km/h) |
| 15 | Daily gusts, precipitation and max temperature 1990–2024 (ERA5) | ECMWF via Open-Meteo (CC-BY 4.0) | `scripts/fetch_history.py` | `data/history.csv` (12 points → per-year storm days, peak gust, wettest 5-day, JJA deficit) — the backtest |
| 16 | UK domestic claims by peril, 2025 | Association of British Insurers (published statistics) | manual (figures embedded in `build_model.py`) | Calibration anchors: storm £244m @ £2,450 avg; flood £312m @ £30,000; subsidence £307m @ £17,820; ~15.5m policies; £3.4bn / 560,000 all-perils home claims for context |
| 17 | Postcode → OA / LSOA / MSOA / LAD best-fit lookup (Aug 2023) | ONS Open Geography Portal | `scripts/fetch_households.py` | 2.6m postcodes → census small areas (22 MB zip, cached) |
| 18 | Census 2021 TS041 "Number of households" by LSOA | ONS via NOMIS | `scripts/fetch_households.py` | England & Wales household counts (35,672 LSOAs, 24.78m households) |
| 19 | Scotland's Census 2022 household total | National Records of Scotland | manual (constant in `fetch_households.py`) | 2,509,300 households, apportioned across Scottish postcodes |
| 20 | Surface-water flood **depth** bands (NaFRA2 RoFSW, >0.2/0.3/0.6/0.9/1.2 m) | Environment Agency | `scripts/fetch_sw_depth.py` | `data/sw_depth.csv` (derived; England only) |
| 21 | National Coastal Erosion Risk Mapping (NCERM) National 2024 | Environment Agency | `scripts/fetch_erosion.py` | `data/erosion.csv` (derived; England only) |
| 22 | Countries (December 2025) UK BGC boundaries | ONS Open Geography Portal | `scripts/fetch_countries.py` | `data/country.csv` — the coverage mask for every England-only dataset |
| 23 | Code-Point Open (GB unit-postcode centroids) | Ordnance Survey (OS OpenData) | `scripts/fetch_codepoint.py` | `data/cache/codepoint_open.zip` → `data/sectors_gb.gpkg` via `derive_sectors.py` (derived sector polygons; **not a model input**) |
| 24 | MIDAS Open uk-mean-wind-obs (station wind/gust observations 1970–2025) | Met Office via CEDA (OGL; account needed to download) | `scripts/fetch_midas.py` + `gusts_from_midas.py` | `data/gusts_midas.csv` → **`data/gusts.csv` (the model's gust source since 2026-08-10)**: 191 stations ≥20 y coverage, ≤300 m altitude, rp50 105–211 km/h |

Together 17–19 produce `data/households.csv` — **27.3m households across 2,995
districts**, used as the exposure weight throughout.

## Endpoints

1. **Boundaries** — `https://github.com/missinglink/uk-postcode-polygons`
   (clone; GB only, no BT/Northern Ireland).
2. **BGS bedrock** — OGC API Features:
   `https://ogcapi.bgs.ac.uk/collections/bgsgeology625kbedrock/items`
   (explicit `offset` paging, 2000/page). BGS's old
   `/arcgis/rest`-style endpoints are dead.
   - **The endpoint blocks GitHub Actions.** From a residential connection
     the full fetch completes every time; from runner IPs it first
     throttled (~20 requests per window, at any pacing — nine runs, every
     one dying around offset 10000) and then escalated to dropping packets
     on the *first* request while the same call answered in 0.3 s locally.
     CI therefore fetches **neither layer from BGS**: both are mirrored as
     release assets on this repo (`data-bgs-625k-v1`, OGL v3 with
     attribution, sha256-pinned in the workflow). Refresh the mirror from
     a laptop: `fetch_bgs.py` (+ `--superficial`), `--verify`, then
     `gh release upload data-bgs-625k-v1 --clobber` and update the pinned
     hashes in `rebuild.yml` if the layers changed.
   - **The superficial sibling `bgsgeology625ksuperficial` is fetched too**
     (`--superficial`, 10,651 deposits) and feeds the subsidence score as a
     bounded modifier — see README's methodology section. It carries `lex_d`
     / `rock_d` in the vocabulary the classifier keys off, but `max_system`
     instead of `max_period` (QUATERNARY throughout, so `OLD_AGE_FACTOR`
     correctly never applies). Its 14-deposit vocabulary is enumerated
     exhaustively in `SUP_SUSCEP`/`SUP_EXCLUDED`; an unrecognised deposit
     raises rather than defaulting. **Peat and unmapped drift are excluded**
     (consolidation/oxidation is not shrink-swell; unmapped is an absence of
     survey), and the blend is capped at half weight because 625k publishes
     no **thickness** — a thin gravel over London Clay would otherwise score
     like a thick one. An earlier note here called this layer unused, and
     README once implied it was licence-blocked behind GeoSure; both were
     corrected when it went into the model on 2026-08-03.
3–6. **Met Office** — anonymous ArcGIS feature services under
   `https://services.arcgis.com/Lq3V5RFuTBC9I7kv/arcgis/rest/services/`:
   `Seasonal_Average_Wind_Speed_Projections_5km/FeatureServer/0`,
   `Annual_Index_of_Wind_Driven_Rain_Projections_5km/FeatureServer/2`
   (filter `Wall_orientation=225`),
   `Annual_Count_of_10mm_Rain_Days_1991_2020/FeatureServer/0`,
   `Annual_Precipitation_Observations_1991_2020/FeatureServer/0`.
   **Quirk:** layers with `x_coord`/`y_coord` fields are in EPSG:27700, but
   `returnCentroid=true` responses come back as WGS84 lon/lat regardless of
   `outSR` — `scores_real._load_grid` auto-detects and reprojects.
   **Note:** HadUK-Grid NetCDFs on CEDA (`dap.ceda.ac.uk`) need a CEDA login;
   the Climate Data Portal serves the same HadUK-derived layers anonymously.
7. **EA rivers/sea** — WMS
   `https://environment.data.gov.uk/spatialdata/rivers-and-sea-defended-and-undefended-flood-risk-extents-present-day/wms`,
   layers `Rivers_1in100_Sea_1in200_defended_extents` and
   `Rivers_1in1000_Sea_1in1000_defended_extents`, rasterised at 100 m in
   EPSG:27700 tiles.
8. **NRW rivers/sea** — GeoServer WMS `https://datamap.gov.wales/geoserver/ows`,
   layer `inspire-nrw:NRW_FLOODZONE_RIVERS_SEAS_MERGED` with
   `cql_filter=risk='Flood Zone 3'` for the high band.
   **Quirk:** several NRW layers carry scale-dependent styling.
9. **SEPA rivers/coastal** — FeatureServer **vector** queries (their MapServers
   have a 1:85,000 minScale, so image export at coarse scales renders nothing):
   `https://map.sepa.org.uk/server/rest/services/Open/<service>/FeatureServer/<id>/query`
   with `maxAllowableOffset=100`. Sublayer ids: River medium=1, Coastal
   medium=7, River low=2, Coastal low=8.
10. **EA surface water** — WMS
    `.../spatialdata/nafra2-risk-of-flooding-from-surface-water/wms`, layer
    `rofsw`. **Quirk:** `MaxScaleDenominator=50000` — renders only at
    ≤ ~14 m/px, so tiles are fetched at 13 m/px (2048 px) and the three legend
    colours are decoded per pixel: High(1in30)=(85,91,157),
    Medium(1in100)=(154,159,222), Low(1in1000)=(195,224,255),
    nearest-anchor with alpha>16.
11. **NRW surface water** — same GeoServer, layer
    `inspire-nrw:NRW_FLOOD_RISK_FROM_SURFACE_WATER_SMALL_WATERCOURSES`,
    `cql_filter=risk IN ('High','Medium')` for the high band, rendered at
    20 m/px (100 m under-renders the small polygons — hence the Wales
    re-render + `merge_sw_wales.py` max-merge). FRAW SW is notably more
    conservative than EA RoFSW (e.g. Cardiff ~2% envelope vs London ~48%) —
    a data-source difference, not an error.
12. **SEPA surface water** — MapServer export at 20 m/px. **Quirk:** the
    sublayers are default-hidden, so exports must pass `layers=show:<id>`
    (medium=4, low=5); without it every export is a blank transparent PNG.
13. **EA postcode flood risk** — direct CSV:
    `https://environment.data.gov.uk/api/file/download?fileDataSetId=fb921496-1788-4fc2-b469-7b51e2a45553&fileName=Postcodes_Risk_Assessment_All.csv`
    (UTF-8 **with BOM**). Columns HIGH/MED/LOW_CNT are the **combined max** of
    RoFRS and RoFSW per address — *not* per-source — so the model only uses
    `GWTR_RISK` (groundwater alert-area flag, England only). Product
    description PDF is on dataset page `53cba123-71f8-417a-8441-4c7ba111e8e1`.
    - **This is the one England-only layer whose coverage is taken from the
      data rather than the boundary**, and that is safe here — checked, not
      assumed. `groundwater_from_ea` gives any district missing from
      `gw_fractions.csv` a nominal 0.02 background, so unlike the depth and
      climate layers an absent district reads as "background", never as
      "no risk". The table is also England-complete: of 2,087 districts at
      ≥95% English share, **0** are missing from it, so the background never
      lands on an English district. The 26 rows that are in the table but
      below the 95% threshold are the known straddlers (Portishead, Chester,
      Knighton, Presteigne, Chepstow, the Dumfriesshire border…) and get a
      partial reading, the same residual limitation noted in #22.

14. **ERA5 gusts** — `https://archive-api.open-meteo.com/v1/archive` with
    `daily=wind_gusts_10m_max`, multi-location batches. **Quirk:** the free
    tier rate-limits by data volume — 35-year daily pulls need small batches
    (2 locations), ~45 s pauses and 150 s backoff on HTTP 429, and the daily
    quota still cuts a full national sweep short. The fetcher is therefore
    resumable — it appends to the CSV, skips points already fetched, and thins
    the remaining grid on resume — so the published 90-point grid was built
    over two days. Gust climatology is smooth at this scale, so the thinned
    grid interpolates fine; `scores_real.py` only folds gusts into the weather
    score once at least 60 points exist, and cleanly falls back to the
    4-component blend below that.

15. **ERA5 history** — same archive endpoint as #14 but requesting
    `wind_gusts_10m_max,precipitation_sum,temperature_2m_max` for twelve
    named locations spanning the Atlantic west, exposed north, dry south-east
    and the flood-prone north-west. Reduced to per-year national indices; the
    JJA rainfall deficit is measured against each point's own 1991–2020
    June–August normal.
16. **ABI aggregates** — published in ABI press releases and property-claims
    statistics; quoted (not scraped) in `build_model.py`'s `ABI` dict so the
    calibration is auditable in one place. Update the dict when newer figures
    are published. Two traps worth recording:
    - **Use the per-peril figures, not the all-claims total.** The headline
      "560,000 home claims / 3.6% frequency" covers escape of water, theft,
      fire and accidental damage, which this model does not cover. Calibrating
      four catastrophe perils to that frequency while applying catastrophe
      severities overstated the loss cost by ~77%.
    - **Denominator:** the ABI premium tracker covers ~15.5m policies, which
      is what every per-policy figure here divides by.

17–19. **Households per district.** Postcode districts are not an ONS
    geography, so households are built from census small areas: the outward
    half of each postcode *is* the district, so the ONS lookup alone gives the
    mapping with no spatial join, and each small area's households are shared
    equally between the postcodes inside it. Traps found:
    - **NOMIS silently truncates at 25,000 records.** The first run returned
      exactly 25,000 LSOAs and looked fine; England & Wales actually has
      35,672. `fetch_households.py` pages with `RecordOffset`.
    - **The UK-wide 2011 table (QS406UK) also contains English and Welsh
      areas.** Summing it onto the 2021 figures double-counts — filter to
      `S` codes, and prefer the 2021 numbers for E&W.
    - **Scottish data zones do not join.** The ONS lookup carries the 2011
      vintage (S01006506–S01013481) while NOMIS only offers 2001
      (S01000001–S01006505) for that table, so the overlap is empty. Scotland
      therefore uses its national Census 2022 total spread across Scottish
      postcodes — within Scotland this makes households proportional to
      postcode count.
    - The lookup CSV is **Latin-1**, not UTF-8 (Welsh and Gaelic place names).

20. **EA surface-water depth bands** — the *same* WMS as #10,
    `.../nafra2-risk-of-flooding-from-surface-water/wms`, which carries five
    extra layers alongside `rofsw`:

        rofsw_0_2m_depth  rofsw_0_3m_depth  rofsw_0_6m_depth
        rofsw_0_9m_depth  rofsw_1_2m_depth

    Each is the part of the surface-water envelope deeper than that
    threshold, painted with the same three likelihood colours, so the same
    decode as #10 works unchanged. Notes:
    - **They carry no `Abstract` and all five share one `Style` name**
      (`Risk_of_Flooding_from_Surface_Water_Depth_0mm`), so the layer name is
      the only statement of what each contains. Verified empirically instead
      of trusted: over a Humber test tile the painted area falls
      100% → 48% → 29% → 10% → 4.9% → 2.3%, and each mask nests inside the
      previous one to within the antialiasing error at 13 m/px.
    - Same `MaxScaleDenominator` 50000 as #10, so **13 m/px or finer or they
      render empty**.
    - The deeper layers are sparse and therefore fast (0.7–2.6 s/tile vs
      6.9 s for the base), so all five together cost only ~10% more than one
      base pass.
    - `sw_low` from #10 is the depth>0 denominator — same layer, same grid,
      no need to refetch it.
    - England only. NRW and SEPA publish no equivalent depth product, so
      Wales and Scotland keep a flat surface-water severity.
    - **`sw_depth.csv` has a row for every district, zero-filled outside
      England** — so "row exists" is not "has data". A Welsh district has
      real surface water (`sw_low > 0`, from NRW) but all-zero depth
      fractions; read naively that says *none of its flooding exceeds
      0.2 m*, i.e. the shallowest possible severity, quietly under-pricing
      Wales and Scotland.
    - And it is not clean either way: **~17 border districts** (Annan,
      Jedburgh, Wrexham, Caldicot, Newtown…) clip far enough into England
      to pick up a *sliver* of EA depth, while `sw_low` covers the whole
      district. That drags the ratio towards zero and makes them look
      uniformly shallow — they were the entire bottom of the severity
      ranking before this was caught.
    - Coverage is therefore judged by whether the depth mapping explains a
      plausible share of the envelope: `d02_low / sw_low ≥ 0.10`.
      Nationally that share is ~0.44 (median), 1st percentile 0.16, so a
      tenth is unambiguously missing coverage rather than shallow water.
      This drops 2,118 districts to 2,101 and leaves only genuine
      straddlers (Berwick, Knighton, Presteigne, Chepstow) with a partial
      reading — a residual limitation, and the reason a hand-maintained
      country list was not used: `SY` and `CH` really do span the border.
      Both traps have tests.

21. **EA NCERM coastal erosion** —
    `https://environment.data.gov.uk/spatialdata/ncern-national-2024/`
    with `/wfs`, `/wms` and `/ogc/features/v1`. Traps:
    - **The slug is misspelled `ncern`, not `ncerm`.** The correctly spelled
      URL 404s. This cost a round of dead guesses.
    - **The OGC API Features `items` endpoint returns HTTP 500.** Use WFS
      `GetFeature` with `outputFormat=application/json`, paged via
      `count`/`startIndex` (1,000 per page).
    - Licence is **OGL**, but `license_id`/`license_title` on CKAN are both
      `null` — it is recorded only in an `extras` entry keyed `licence`.
    - 14 collections: `NCERM_{SMP,NFI}_{2055,2105}_{0,70,95}CC` plus
      `NCERM_Ground_Instability_{Zone,Recession}`. SMP = the adopted
      Shoreline Management Plan (defences maintained as planned); NFI = no
      further intervention (defences lapse). We use the 70th-percentile
      climate-change allowance.
    - **`Ground_Instability_Zone` and `_Recession` are not duplicates**, and
      the second is not a subset of the first. Both carry 80 features with
      byte-identical attributes, which makes them look redundant. The
      geometry says otherwise: the two unions overlap by 0.01% of the
      recession area (700 m² of 5.39 km²) while all 80 recession polygons
      *touch* their zone at distance 0.00 m. `_Zone` (27.18 km²) is the
      cliff that is unstable **today**; `_Recession` (5.39 km²) is the strip
      the rear scarp is projected to retreat into, lying immediately
      landward. They are adjacent and **additive**, not nested. Consistent
      with that, polygon area ÷ `rearscarpr` recovers the frontage length to
      within 3% (median ratio 0.971 against half the perimeter), so unlike
      the SMP/NFI frontages this layer's area *is* trustworthy — it really
      is a strip of width `rearscarpr` ∈ {0, 10, 50, 100} m.
      Only `_Zone` is fetched (`er_gi`); `_Recession` is left unfetched
      deliberately, because `er_gi` is a published descriptive column that
      does not feed `er_score` (only `er_smp105` does), so a second such
      column would cost a full rebuild to change nothing that is priced.
    - **The polygon area is not a reliable measure of land lost.** For most
      of the ~7,500 frontages the polygon is the recession strip and its
      area ≈ `shape_leng × recession`, but 2–10% of records — concentrated
      in estuaries — are broad zones instead. Frontage 101342 covers 10 km²
      of the Dee while declaring a **3 m** recession over a **110 km**
      "frontage"; taken literally it made two Wirral districts (CH60, CH64)
      the most erosion-exposed in England, ahead of the Holderness coast,
      and barely moved between 2055 and 2105 — the tell that it is not
      erosion. `fetch_erosion.py` therefore takes the land lost from
      `shape_leng × recession` and uses the polygon only to decide *where*
      it falls. This also restores the scenario contrast the broad zones
      were flattening: on raw polygon area SMP-2055 → NFI-2105 spans just
      1.6×, on length × recession it spans 6.4× (67 → 435 km²).

22. **Country boundaries — the coverage mask.** Three separate EA products
    stop at the English border (#20 depth, #21 erosion, and the
    climate-change extents), and every attempt to infer that from the data
    produced a plausible-looking error:
    - a Welsh district has real surface water from NRW but zero EA depth,
      which reads as *"none of its flooding exceeds 0.2 m"* — the
      shallowest possible severity, applied to all of Wales and Scotland;
    - Dundee's present-day flood fraction is 70% and its EA climate-change
      fraction is 0%, which reads as a **70-point fall** in flood risk
      under climate change;
    - border districts that clip a few hundred metres into England pick up
      a sliver of English data and look like genuine observations.

    Postcode areas cannot settle it — `SY` and `CH` genuinely straddle —
    so `fetch_countries.py` takes the actual ONS boundary and assigns each
    district the country holding most of its area, keeping the share.
    Coverage requires **England and ≥95% share**, so the ~20 real
    straddlers (Portishead 50%, Chester 54%, Hereford 57%, Berwick 64%,
    Welshpool 66%) take the neutral fallback instead of a reading built
    from whichever half happens to be mapped. Result: England 2,099,
    Scotland 442, Wales 195.

    Two traps in fetching it:
    - Use the **BGC** (generalised) edition. The **BFC** full-resolution
      one is **133 MB**, its single England feature exceeds GDAL's default
      GeoJSON object-size limit (`OGR_GEOJSON_MAX_OBJ_SIZE`), and
      intersecting that coastline against 2,700 districts takes tens of
      minutes for a question answered at kilometre scale.
    - Service names on the portal are inconsistent
      (`Countries_Dec_2021_GB_BFC_2022` vs
      `Countries_December_2025_Boundaries_UK_BGC`); list the services
      rather than guessing the pattern.

23. **OS Code-Point Open — unit-postcode centroids** (for the derived
    postcode-sector polygons, not a model input yet):
    `https://api.os.uk/downloads/v1/products/CodePointOpen/downloads?area=GB&format=CSV&redirect`
    — keyless, ~1.7 M current GB postcodes with 1 m-resolution BNG
    centroids. OS OpenData licence (OGL-compatible; attribution
    "Contains OS data © Crown copyright and database right", plus Royal
    Mail/ONS for the postcode data). Fetched by
    `scripts/fetch_codepoint.py`. **Quirks:** the CSVs have *no header
    row* (column names live in `Doc/Code-Point_Open_Column_Headers.csv`
    inside the zip); postcodes come space-padded to 7 characters
    (`"YO1 1AA"`, `"YO25 6QP"` both occur) — normalise by stripping
    spaces, inward code is always the last 3 characters; `quality=90`
    rows have **no coordinates** (0,0) and must be dropped.

24. **Met Office MIDAS Open — station wind/gust observations** (the
    intended upgrade for the gust component): catalogue
    `https://catalogue.ceda.ac.uk/uuid/91cb9985a6c2453d99084bde4ff5f314`
    (`uk-mean-wind-obs`), OGL, **but downloads need a CEDA account** —
    free, human registration at
    `https://services.ceda.ac.uk/cedasite/register/info/`; directory
    listings are anonymous but every file GET 302s to "Unauthenticated"
    (same wall as the HadUK NetCDFs above). **Fetch route:** the account
    holder creates an access token at
    `https://services.ceda.ac.uk/account/token/` (~72 h validity) and
    saves it as the only line of `~/.ceda_token`;
    `scripts/fetch_midas.py` then mirrors the latest dataset-version
    (qcv-1, ≥1970) into `data/midas/`, validating every body starts
    `Conventions,G,BADC-CSV` — an expired token otherwise saves
    thousands of login pages under `.csv` names, discovered only at
    parse time. **This is the model's gust source since 2026-08-10**
    (mirror fetched 2026-08-09: 10,983 files, 8.4 GB). The processor
    excludes stations above 300 m — the first run kept Cairngorm summit
    (1,237 m) and its rp50 of 283 km/h smeared across valley districts;
    summit anemometers measure a climate nobody lives in. Once a mirror
    is on disk,
    `scripts/gusts_from_midas.py <download-root>` reduces it to the
    exact `data/gusts.csv` contract (per-station daily-gust p98 +
    Gumbel 1-in-50, knots→km/h) and refuses to emit fewer than 50
    stations. Use **qcv-1** files only; the processor ignores qcv-0.

## Blocked on non-open data — what each would unblock

Kept here so nobody re-derives the shopping list. None of these have an
open substitute; every open path was checked (see dead ends below).

- **A claims triangle** (insurer bordereaux or ABI member-level data;
  not published at any price — it needs a data-sharing agreement with an
  insurer). Unblocks: fitting the pair-copulas from data
  (`pyvinecopulib` replaces the assumed θ(s) forms), and real
  frequency/severity distributions instead of ABI-calibrated compound
  Bernoulli×LogNormal. This is the single highest-value dataset the
  model lacks.
- **PAF / AddressBase** (Royal Mail licence via a reseller, or OS
  AddressBase Premium — both licensed, hundreds to thousands of £/yr
  depending on tier). Unblocks: real dwelling counts below district
  level, sum insured proxies (property type/age), construction type —
  i.e. exposure that is currently census households uniformly smeared
  over each district.
- **BGS superficial thickness** (licensed BGS product; the open 625k
  layer publishes extent only). Unblocks: making `SUP_WEIGHT` physical
  instead of a bounded 0.5 prior — see the dose-response runs in the
  project notes.
- ~~MIDAS Open~~ **unblocked and LIVE since 2026-08-10** (#24): the user
  registered, the mirror was fetched and the model's gust component now
  runs on station extremes. Kept here so the pattern is remembered: it
  was never money-blocked, only one registration away.

## Not used / dead ends (so you don't repeat them)

- `environment.data.gov.uk/arcgis/rest/...` — EA's old ArcGIS root: gone.
- Legacy `risk-of-flooding-from-surface-water-extent-*` spatialdata slugs: 404
  (superseded by NaFRA2).
- CEDA HadUK-Grid NetCDF downloads: directory listing is anonymous but files
  are login-walled (the "downloads" are 8 KB HTML login pages).
- SEPA surface water via FeatureServer: 8–10 M features — infeasible; use the
  raster route.
- BGS GeoSure / GeoClimate, OS AddressBase: licensed, not open.
- `spatialdata/ncerm-national-2024/...` (correctly spelled): 404. The EA
  published it as **`ncern`**.
- NCERM via `/ogc/features/v1/collections/<id>/items`: HTTP 500. WFS works.
- `nafra2-risk-of-flooding-from-surface-water-depth` as its own dataset slug:
  404. The depth layers live inside the existing surface-water WMS.
- **A second climate epoch or allowance for either flood product**: does not
  exist. `GetCapabilities` on both climate services returns one future layer
  each — `Rivers_1in{100,1000}_Sea_1in{200,1000}_{defended,undefended}_extents_CCP1`
  and `rofsw_cc01` with its five depth bands — with no `CCP2`/`cc02` sibling
  and no percentile variants. (The duplicate `..._28_11_2025` names on both
  the present-day and climate services are edition stamps of the same
  layers, not epochs.) A climate *ladder* is therefore unavailable from the
  EA flood extents, though NCERM does publish one for erosion.
- **Postcode-sector boundaries for England & Wales**: not published. Only
  Scotland has official sector polygons; E&W publish postcode→sector
  *lookups* only. **Derived instead (2026-08-08)**: sectors nest inside
  districts by definition, so `derive_sectors.py` Voronoi-partitions each
  modelled district's own Code-Point Open centroids (#23) and dissolves by
  inward digit — 10,398 sectors over all 2,736 districts, each district's
  partition exact by construction (asserted, not assumed). Output
  `data/sectors_gb.gpkg` (25 MB, gitignored; ~5 min to rebuild). Not a
  model input: that would mean re-rasterising every hazard over ~10k
  geometries (~4× the raster work) and re-validating exposure — a decision,
  not a step. Validation against Scotland's official sectors is the obvious
  next probe if sector-level modelling is ever green-lit.
