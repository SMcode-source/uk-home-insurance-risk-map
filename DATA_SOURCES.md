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
| 25 | Street-level crime archive, latest 36 months | police.uk (Home Office; OGL) | `scripts/fetch_burglary.py` | `data/burglary.csv` — 668,609 burglary points placed into the model's own polygons; the theft-peril frequency source |
| 26 | Annual count of air-frost days 1991–2020 (HadUK-Grid obs) | Met Office Climate Data Portal | `scripts/fetch_metoffice.py frost` | `data/metoffice/frost.csv` (63,296 cells, 0.7–208 days) — the freeze-exposure driver for escape of water |

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
    - **This series is also the anchor for `TAIL_FREQ_RATIO = 2.0`**
      (added 2026-08-23; the constant shipped before this with no source
      anywhere in the repo, which is what the no-undocumented-knobs rule
      exists to prevent). It is the sole target `calibrate_spatial` solves
      against, so it fixes `SPATIAL_SCALE` and through it the year view,
      `tvar99_euler`, capital and the published premium — the one number
      that sets how wide the tail is.
    - **What it has to be measured against.** `calibrate_spatial` reports
      it as *"1-in-100 year claims Nx the mean year"*, so it is a ratio of
      claim COUNTS. The proxy must drive how many homes claim, not how
      hard each is hit: **`storm_days`** (days with gust ≥ 70 km/h) is the
      right series and **`max_gust` is not**. One violent gust hurts a few
      homes badly; a year with many storm days puts many homes into claim.
    - **The measurement** (`scripts/tail_ratio_from_history.py`, 1990–2024,
      35 years; `storm_days` shows no significant trend, −0.039 days/yr,
      p = 0.77, so the raw spread is the right thing to fit):

      | proxy | CV | obs max/mean | lognormal 1-in-100 | gamma |
      |---|---|---|---|---|
      | `storm_days` (primary) | 0.284 | 1.67 | **1.84** | 1.78 |
      | `storm_days^1.5` | 0.419 | 2.09 | 2.35 | 2.22 |
      | `rain5d` (flood count driver) | 0.129 | 1.33 | 1.34 | 1.32 |
      | `max_gust` (wrong shape, shown to make that visible) | 0.077 | 1.17 | 1.19 | 1.19 |

      **2.0 sits inside the 1.78–2.35 range** the primary proxy supports
      once mild convexity is allowed. The knob was undocumented, not
      wrong, so it keeps its value and gains this entry.
    - **What this does not establish.** That storm days convert to claim
      counts one-for-one. The proxy choice moves the answer far more than
      the fitted distribution does — `max_gust` would have halved the tail
      — so the assumption is argued rather than assumed. A claims triangle
      would settle it; see HANDOFF, "What remains, honestly".
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

25. **police.uk street-level crime — the theft-peril frequency source**
    (fetched 2026-08-16). `https://data.police.uk/data/archive/latest.zip`
    302s to `policeuk-data.s3.amazonaws.com/archive/<YYYY-MM>.zip`
    (1.7 GB; the S3 URL is resumable with `curl -C -`, the vanity URL is
    not). One zip holds **36 months** of per-force monthly CSVs
    (`<month>/<month>-<force>-street.csv`); `scripts/fetch_burglary.py`
    filters `Crime type == "Burglary"` and spatially joins the snap-point
    coordinates to the model's own district polygons →
    `data/burglary.csv` (668,609 incidents placed, 2023-07..2026-06).
    Quirks that matter:
    - **Coordinates are anonymised snap points** (nearest of ~750k street
      anchors, each covering ≥8 addresses) — a few hundred metres of
      displacement, noise at district scale. Joined on coordinates, NOT
      the row's LSOA code: the LSOA vintage drifts across census
      editions; the polygons don't.
    - **"Burglary" includes commercial premises.** Districts with tiny
      residential counts show absurd per-household rates (EC3V: 116
      burglaries over 72 households = 54%/yr — those are offices). The
      reader must winsorise, not trust raw rates.
    - **Scotland is NOT covered** (Police Scotland publishes no
      incident-level data) — but 9 Scottish districts still show 1–2
      incidents via **British Transport Police**, which does cover
      Scottish railways. The country-mask fallback must OVERRIDE
      Scotland, not merely fill blanks. The override's comparator was
      measured on 2026-09-01 and **kept**: see #36 and LIMITATIONS §5. Northern Ireland (PSNI) is in
      the archive but outside the GB polygons; its rows land in the
      "outside every polygon" bucket (8,633 with BTP/coastal strays).
    - **Calibration anchor (the LEVEL):** the ABI stopped publishing an
      annual theft-paid total; the last public figure is **~£450m
      (2018)**, formerly on the ABI theft page (now only in search-engine
      caches of it). Averages are still published: **£3,800 per theft
      claim (2025), £4,350 (Q1 2026)**. CSEW "Nature of crime: burglary"
      tables carry **no insurance-claim propensity** (checked the
      year-ending-March-2025 edition sheet by sheet). None of this
      blocks the model: `calibrate_frequency` pins the exposure-weighted
      national frequency to paid/severity/policies, so the
      burglary→claim propensity **cancels** — police data supplies
      relativities only, and the implied envelope (2018 paid at 2025
      severity = 0.76%/policy, vs 0.97% then and ~0.58% now if claims
      fell with recorded burglary) is the documented uncertainty on the
      theft LEVEL, not on the geography.

26. **Air-frost days + ABI escape-of-water anchors — the EoW peril's
    sources** (assembled 2026-08-16). The hazard grid is
    `Annual_Count_of_Airfrost_Days_1991_2020` on the same anonymous
    ArcGIS portal as the other four Met Office layers
    (`fetch_metoffice.py frost`, field `airfrostDays`, centroid query;
    63,296 cells, GB range 0.7 days on Scilly to 208 on Cairngorm
    summits, median 47). Anchors and why each was chosen:
    - **Level: ~£657m/yr** — the ABI's standing "insurers pay out
      around **£1.8 million every day** for escape of water" (quoted
      across their material since ~2017; like theft, the ABI stopped
      publishing an annual per-peril total, and the 2025 full-year
      release folds EoW into a £758m "weather-related damage to homes"
      line that also covers storm and flood). **RESOLVED 2026-08-23
      against the primary releases — and the resolution corrects both
      this note and the flag raised here on 2026-08-22.** The releases
      are now transcribed with per-figure provenance in
      `data/abi_annual.csv`; read that, not this paragraph, for the
      numbers. What they say:
      - The 2025 weather line's scope, footnote 3 of the 2026-02
        release verbatim: *"These weather-related figures cover damage
        caused by burst or frozen pipes, escape of water, as well as
        damage as a result from storms and flooding."*
      - The 2024-04 release **itemises the same line for 2023**:
        storm £133m + flood £286m + **burst pipes £153m** = £572m
        against a £573m total. So the water component of the weather
        line is **burst pipes only, not the whole EoW book** — and by
        the same subtraction the 2025 residual is
        £758m − £244m − £312m = **£202m of burst pipes**.
      - Therefore there is **no contradiction with the £657m EoW
        anchor**: burst pipes are a SUBSET of it. The 2026-08-22 flag
        claiming £758m "leaves £202m for EoW, not £657m" was wrong on
        that point, and the £1,451m alternative headroom it offered
        does not exist.
      - What survives the correction: #27 and #28 below still add
        "weather £758m" and "EoW £657m" as separate remainder items,
        which double-counts the **£202m** they overlap in. The
        headroom those two triangles were sized against is overstated
        by £202m, not by £657m.
      - Also settled: storm £244m, flood £312m and subsidence £307m
        **are** 2025 full-year figures, quoted directly in the 2026-02
        release, so source 16's "2025" label is correct. The
        per-peril weather totals were not withdrawn — they sit beside
        the aggregate line.
      **Two things this opens, both unresolved:**
      - **`EOW_FREEZE_SHARE = 0.15` looks low.** Burst pipes were
        £153m of a £657m EoW book in 2023 (0.23) and £202m in 2025
        (0.31). Neither year supports 0.15. Changing it is a model
        change: it moves EoW's geography onto frost days harder and
        alters its systemic loading, so it needs an experiment branch.
      - **The ABI restates this series and its releases disagree.**
        The 2024-04 release puts 2023 at £573m and calls it the record;
        the 2025-02 release puts 2024 at £585m, describes it as
        *"£127 million (28%) higher than ... 2023"* (implying £458m for
        2023) and calls **2022** the previous record. Both cannot be
        right. The 2024-04 release's own footnote 3 gives the
        mechanism — *"This figure will include claims not yet fully
        settled"* — but not the direction. Pick ONE vintage of the
        series and stay in it; never mix a figure as-published with a
        later comparative.
      `scripts/anchor_budget.py` and `scripts/backtest_coverage.py`
      print the consequences; see HANDOFF "Claim-count overshoot:
      attributed 2026-08-22" and "Coverage backtest 2026-08-23". Cross-check that closes
      the triangle: EoW was **29.3% of 2025's 560,000 home claims**
      (GoCompare from ABI data) ≈ **164,000 claims/yr**, and
      £657m / 164k = **£4,005 average** — self-consistent, so
      frequency ≈ **1.06%/policy** over 15.5m. Aviva's 2025 book
      average of £8,595 shows how wide insurer-level severity runs
      (their book, post-repair-inflation); the documented envelope on
      the EoW LEVEL is the vintage mixing, exactly as for theft.
    - **Year-to-year variation (pins W_EOW, the systemic loading):**
      winter 2010 freeze, 24 Nov–31 Dec: **103,000 burst-pipe claims,
      £680m** (ABI via Insurance Times) — a normal year's EoW paid in
      SIX WEEKS, so the worst year in the record cost ≈ **2× mean**;
      Q1 2018 (Beast from the East): **£193m** freeze-attributed
      domestic EoW in the quarter ≈ +30% on that year. Unlike theft
      (±10-15%), EoW has genuine systemic freeze years — its loading
      must come out an order of magnitude above theft's, and the
      derivation in build_model targets 1-in-100 ≈ 2× cost.
    - **Freeze-attributable share (sizes the frost-sensitive slice):**
      Aviva 2026 — **25% of EoW claims occur July–September**; the peak
      is January, freeze-driven. Most EoW is year-round plumbing and
      appliance failure with NO open spatial predictor until Phase 2
      (EPC dwelling age / VOA), so the frequency is a FLAT base plus a
      freeze-sensitive slice (~15%) scaled by each district's
      frost-day relativity. The map should NOT light up dramatically
      for EoW; the open data does not support dramatic spatial claims.
    - **Rejected:** water-hardness maps (no per-district open product,
      and limescale→failure is a weaker mechanism than freeze);
      CSEW (no EoW analogue); per-insurer claim-rate maps (marketing
      material, no methodology).

27. **Home Office dwelling-fire incidents + ABI fire anchors — the
    fire peril's sources** (assembled 2026-08-17). Unlike EoW, fire
    has a REAL open spatial driver at sub-district resolution:
    - **Spatial driver (England): the incident-level "Low level
      geography dataset"** under
      `gov.uk/government/statistics/fire-statistics-incident-level-datasets`
      (MHCLG since Apr 2025, previously Home Office) — one row per
      incident with `LSOA_CODE` and `INCIDENT_TYPE`; filter
      `Primary fire - dwelling` (dwellings are NOT split by motive at
      incident level; use all — deliberate dwelling fires are insured
      and spatially informative). Two ODS files cover 2017/18→present
      (9.6 MB + 29 MB); the current file's 2025/26 sheet has
      `Not known` LSOAs — **use complete financial years only**
      (8 available: 2017/18–2024/25). **Quirk: pandas' odf engine
      takes >10 min on the 9.6 MB file even for nrows=5** — parse
      `content.xml` from the zip directly, and mind
      `table:number-columns-repeated` compression when counting.
      LSOA→district weighting via ONSPD, as for households.
    - **Devolved:** Wales — StatsWales "Fires ... by area and
      financial year" cubes (OData/JSON, dwelling fires by FRA/LA);
      Scotland — statistics.gov.scot "Fire - Type of Incident"
      (accidental dwelling fires down to datazone). Better than
      theft's flat-Scotland override: both nations have real
      sub-national counts.
    - **Level anchor (triangle, no direct figure exists):** the ABI
      publishes NO current domestic fire split — the 2025 full-year
      release (£3.4bn/560k home claims) and Q1 2026 release were both
      checked; the latter only says "lower fire and explosion payouts
      were the main driver of the decline", never a number.
      Frequency leg: **FIRE0201** (one xlsx, all three GB nations):
      2024/25 attended dwelling fires **31,001** (England 25,465,
      Scotland 4,104, Wales 1,432) → **0.20%/policy** on the tracker's
      15.5m, treating attended count as claim-count proxy (unattended
      small claims vs uninsured/below-excess attended fires roughly
      offset — documented judgment). Severity leg: the ABI-attributed
      **"average payout for fire damage £10,200–£11,000"** (undated,
      ~2019 vintage, still cited 2023–25 by AA/GoCompare/Tempest);
      indexed ~+27% for claims inflation → **sev_fire ≈ £14,000**.
      Implied level ≈ **£434m/yr ≈ 12.8%** of 2025 home paid — inside
      the remainder envelope after EoW £657m, weather £758m,
      subsidence £307m, theft ~£450m and AD.
    - **Year-to-year variation (pins W_FIRE):** FIRE0201's national
      series runs 1981/82–2025/26. Raw CV 0.246 is ALL secular decline
      (58k→25k); detrended year-on-year residuals are **±2–3%** with
      no spike years (even the 2022 heatwave summer barely registers
      at annual grain) — so fire's systemic loading comes out near
      ZERO, below theft's. That is a finding, not a shortcut: fire is
      the closest thing in the book to a purely idiosyncratic peril.
    - **Rejected:** aggregator per-peril percentages (mutually
      inconsistent — "fire is 17% of claims" contradicts every
      severity figure); Statista per-peril paid series (paywalled);
      guessed FIRE0102 asset URL (dead — always take URLs from the
      statistical-data-sets page). **Quirk:** abi.org.uk moved to
      `/media-hub/` — the old `/news/news-articles/...` URLs 404 for
      WebFetch and render an empty Next.js shell in a real browser;
      re-find articles under the new path instead.

28. **Accidental damage anchors — the AD peril's sources** (assembled
    2026-08-17). Like fire, no public AD paid total exists (the ABI
    never published one, even historically); unlike fire there is NO
    open spatial driver at all — AD is behavioural, and every
    frequency/severity anchor is insurer- or aggregator-attributed:
    - **Claim-share (frequency leg):** GoCompare's 2025 quote-declared
      claims table (`gocompare.com/home-insurance/common-home-insurance-claims/`
      — bot-blocks plain fetches, use a real browser; 40,962 declared
      claims): **accidental loss/damage AT home 23.35%**, away from
      home 6.46%, outside home 1.18% — total 30.99%. Same source and
      vintage as EoW's verified 29.38%, so the two shares are
      internally consistent by construction. Cross-check from a
      second, independent book: **Aviva (02 Apr 2026 release, claims
      Jan 2022–Mar 2026): AD = 32% of all home claims, their most
      common claim** — two books agree within a point. Applied to the
      ABI's 560k 2025 home claims: at-home+outside ≈ 137k → ~0.89%/
      policy on 15.5m; including away-from-home ≈ 174k → ~1.12%.
      (Away-from-home is a separate optional personal-possessions
      extension — decide the scope explicitly before wiring.)
    - **Severity leg:** Aviva (same release): average AD claim
      **£1,148 (2022) → £1,869 (2026)**, +63% in four years — the
      2025 point interpolates to ~**£1,650**. Paymentshield
      (Aug 2024–Jul 2025 book): **£1,159** average, AD = 25% of their
      claims. AD is the smallest-severity peril in the book by far
      (broken TVs — 18% of Aviva's AD claims — spilled drinks,
      cracked sinks; children cause 8%).
    - **Implied level:** ~137k × ~£1,650 ≈ **£225m/yr** (at-home
      basis) to ~£290m (all-AD) ≈ 7–9% of 2025's £3.4bn home paid —
      comfortably inside the ~£790m remainder after weather £758m,
      EoW £657m, theft £450m, fire £434m, subsidence £307m.
    - **Year-to-year variation (pins W_AD):** the 2020–21 lockdowns
      were the largest stay-at-home behavioural shock on record, and
      AD claim declarations rose only **~6% vs 2019** (GoCompare
      press release, 26 Oct 2021, Jan–Aug 2021 quote data). Aviva's
      category-level spikes (hot tubs +188%, exercise equipment
      +200% in 2020) are tiny categories inside a stable aggregate.
      So the worst systemic AD year ≈ 1.06× mean — between fire
      (residual CV ~2%) and theft (±10–15%); W_AD lands ~5e-4 by the
      CV(count) ≈ sqrt(w)·φ(z_p)/p derivation.
    - **AD is optional add-on cover** (Aviva's own explainer:
      "isn't always included as standard... an optional add-on to
      buildings insurance, contents insurance, or both") — the
      modelled premium prices the peril as if covered, same policy
      basis as theft/EoW/fire; say so in the site copy.
    - **Spatial driver: none exists in open data.** Candidates
      examined and rejected as drivers rather than sources: fire's
      incident data (different peril), police.uk (crime, not
      accidents), EPC (dwelling age says nothing about toddlers with
      juice). The honest options are a FLAT rate or a mild census
      relativity (households with dependent children, tenure) —
      decision recorded with the wiring, not assumed here.
    - **Rejected:** pcla.co.uk's £615 average (undated, no
      methodology); "25% of claims" aggregator repeats without a
      book behind them; Admiral's "+39% AD claims after lockdown
      eased" (that figure is MOTOR, not home — a trap when searching
      this topic).

29. **VOA non-domestic premises counts — theft's commercial
    denominator** (fetched 2026-08-17, `fetch_premises.py` →
    `data/premises.csv`). The Phase 2a fix promised in #25: police.uk
    "Burglary" includes commercial break-ins, so the theft rate now
    divides by households PLUS non-domestic premises instead of
    leaning on the p99.9 cap to hide commercial cores (the cap stays
    as a tiny-denominator backstop).
    - **Source:** "Non-domestic rating: stock of properties 2025"
      (VOA, OGL v3, snapshot 31 Mar 2025, published summer 2025) —
      `ndr_stock_oa_2025.zip` (7.1 MB) from
      assets.publishing.service.gov.uk, member
      `SOP_OA_counts_all.csv`, rows filtered to `geography == "LSOA"`,
      the `2025` year column. 35,672 LSOAs (**LSOA2021 codes** — the
      count matches the 2021 census geography exactly, and the ONS
      lookup's `lsoa21cd` covers 100.0% of premises; the fetcher
      matches both vintages and asserts ≥97% coverage so a future
      boundary revision fails loudly), 2,136,290 premises. Counts are
      rounded to 10; 3,873 suppressed small cells ("[c]") treated as
      0. Apportioned to districts by live-postcode share through the
      same ONS lookup the household counts use — 100.0% of premises
      placed, 2,415 of 2,736 districts have any. Most commercial:
      SE1 7,696 / E1 6,620 / E14 6,397.
    - **Scotland deliberately absent:** VOA covers E&W only, and
      theft's Scotland is a flat national override (#25), so a
      commercial correction there would adjust nothing.
    - **Effect (local check against the published rates):** cap falls
      6.22% → 3.40% and binds 14 districts instead of doing crude
      duty for every commercial core; W1J 6.22% → 1.85% real rate,
      EC3V 6.22% → 3.40% (still capped); correlation with the old
      geography 0.89; the −8% E&W mean shift is re-pinned to the ABI
      level by FREQ_SCALE at calibration.
    - **Dead ends:** the VOA **rating-list bulk** downloads
      (voaratinglists.blob.core.windows.net) are free but under
      restricted terms, not OGL — unusable in this public repo when
      the statistical LSOA release exists; the data.gov.uk "VOA
      non-domestic rating" catalogue entry is a dead 2016 record with
      no links; **EPC bulk** (epc.opendatacommunities.org) needs
      registration, carries Royal Mail copyright on address fields,
      and covers only certificate-holding stock — CTSOP4.1 gives
      build period for the FULL stock at LSOA under plain OGL if
      Phase 2b/2c ever need it.

30. **Council-tax band mix — the attritional severity relativity**
    (`scripts/fetch_ct_bands.py` → `data/ct_bands.csv`, Phase 2c).
    Bands are the only full-stock, small-area, OGL property-value
    proxy in Great Britain; the district band mix scales the four
    flat attritional severities (theft, EoW, fire, AD).
    - **England & Wales:** CTSOP1.1, VOA "Council Tax: stock of
      properties 2025", snapshot 31 Mar 2025 — direct zip (732 KB)
      `https://assets.publishing.service.gov.uk/media/6a0ad444c75cc34a8ff8f397/CTSOP1.1.zip`,
      member `CTSOP1.1/CTSOP1_1_2025_03_31.csv`, filter
      `geography=="LSOA"`. Counts rounded to 10; `-` = suppressed
      (<5, treated as 0); `..` = not applicable (band_i outside
      Wales). 35,672 LSOAs / 27.29m dwellings.
    - **Scotland:** "Dwellings by Council Tax Band Detailed",
      NRS via statistics.gov.scot (10.6 MB zip,
      `https://statistics.gov.scot/downloads/file?id=c0c89950-ae25-48c1-b806-c6a759a211c5%2FDwellings+by+Council+Tax+Band+Detailed.zip`).
      **Use the 2023 CSV only**: 2005–2023 are on 2011 data zones,
      the 2024 file silently switches to 2022 data zones, which no
      postcode product joins yet. 6,973 DZs / 2.73m dwellings.
    - **Band weights are each nation's statutory charge ratios**
      (England/Wales LGFA 1992 s.5: 6:7:8:9:11:13:15:18(:21)/9;
      Scotland post-2017: 240:280:320:360:473:585:705:882/360) —
      published, stable, and the only anchor that exists for all
      three regimes. The regimes are INCOMPATIBLE (1991 England vs
      2003 Wales vs 1991-with-own-ratios Scotland), so weights are
      normalised within nation to a dwelling-weighted mean of 1.0
      before any district — several straddle the English-Welsh
      border — averages over its small areas.
    - **Geography join trap:** the cached ONS lookup's `lsoa21cd`
      column holds E&W 2021 LSOAs AND Scottish 2011 data zones
      (Scotland had no 2021 census); there is no lsoa11cd member.
      Coverage asserted ≥97% per nation (both hit 100.0%).
    - **Effect:** 30.02m dwellings placed across 2,866 districts;
      relativity runs 0.69 (CF43, Rhondda) to 1.94 (SW1X,
      Belgravia). Normalisation to CLAIM weights (households × that
      peril's rate) happens in build_model.main(), so each peril's
      ABI severity level is pinned by construction.
31. **Buildings/contents split anchors — searched 2026-08-17/18, and the
    search FAILED for half the book.** (Numbers 29 and 30 are published, with
    Phase 2a and Phase 2c respectively; this one follows 30 in order.) Phase 3 needs, for each peril, the share of claims *cost*
    falling on the buildings section rather than contents. **No published
    UK source gives a peril × cover-type matrix.** Not the ABI, not the
    FCA, not any regulator. What does exist, per peril:
    - **Theft — anchored.** ONS Crime Survey for England and Wales,
      *Nature of crime: burglary* tables. Damage (a buildings-section
      cost: forced doors, windows, frames) is **24.2%** of burglary
      cost pooled over nine survey years; the rest is stolen goods,
      which is contents. → **~25% buildings**. The one peril where the
      split falls straight out of an official statistic.
    - **Fire — anchored.** Home Office, *Economic and social cost of
      fire*. Property damage in dwelling fires is dominated by
      structure; the published dwelling uprate puts contents at
      **~22%** → **~78% buildings**.
    - **Subsidence — anchored at ~100% buildings, on loss-cost grounds
      only.** Subsidence damages foundations and walls; contents are
      almost never the loss. **Correction worth keeping:** do NOT cite
      policy wording as the proof — contents sections *do* insure
      subsidence in all four wordings checked. The anchor is where the
      money goes, not what the policy covers.
    - **Flood — three published conventions that CONTRADICT each other.**
      Flood Re's statutory buildings/contents premium caps imply
      **66/34**; the Multi-Coloured Manual depth-damage curves imply
      **48/52**; the EA's own appraisal convention implies **25/75**.
      These are not refinements of one number, they are three different
      answers. Fortunately it barely matters here — flood is 9.8% of
      this model's claim cost, so all three land within 4pp at portfolio
      level (63.2%–67.2% buildings).
    - **Storm, groundwater, escape of water, accidental damage — NO
      ANCHOR EXISTS.** Nothing published, at any grain, from any body.
      Together these are **43.2% of the model's claim cost**, and escape
      of water alone is **25.1%** — the single largest peril in the
      book. This is what stops Phase 3 (see the verdict below).
    - **Rejected — the all-perils shortcuts.** FCA General Insurance
      Value Measures give an all-perils **~77/23**, but it compares
      *standalone* buildings and contents products and so carries the
      same renter-selection bias that already disqualified the premium
      ratio: contents-only buyers are disproportionately renters with
      lower sums insured. A bottom-up recombination of the four real
      anchors suggests **~70/30**, which is a coherence check, not a
      source. Also dead: every `abi.org.uk/globalassets/...` PDF URL
      found via search (all 404 — the media-hub move again, see #27),
      and the marketing "typical split" statistics that insurer and
      aggregator blogs quote without a book behind them.
    - **Second search pass, 2026-08-18 — three more routes closed.**
      Each was checked directly rather than assumed:
      - **IFoA research working parties: no such party exists.** The
        current register runs Actuarial applications of vine copulas,
        AI/ML for pricing, UK asbestos, Black swan, Capital research,
        Claims inflation, Climate change, Cyber, Electric vehicles,
        Fairness and inclusion, **Flood**, Liability exposure
        management, ML in reserving, Managing the cycle, UK motor,
        Pricing research, Reserving research, Risk drivers, Delegated
        underwriting, Solvency UK, Third party, Optimal reserving.
        Nothing on household, water damage, or claims-by-peril. The
        Flood party is the only property-peril one, and flood is the
        peril already anchored three times over.
      - **FCA General Insurance Value Measures is product-level, not
        peril-level.** It reports claims frequency, acceptance rate and
        average payout per *product* (buildings, contents, combined) —
        there is no peril dimension in the return, so it cannot yield a
        peril x cover matrix at any level of effort. Confirms the
        earlier rejection for a second reason beyond renter selection.
      - **ABI property-claims releases give combined figures only.**
        The quarterly and annual releases split weather vs non-weather
        and quote per-peril totals and averages, but never buildings vs
        contents within a peril. (The 2026 annual release URL also
        404s to WebFetch — the media-hub move again, see #27.)
    - **Third pass 2026-08-18 — the last two live routes, both closed.**
      - **FCA GIVM re-checked against the 2025 release** (calendar 2025,
        the fourth full year) in case the return had gained a peril
        dimension. It has not: the five metrics are claims frequency,
        acceptance rate, average payout, complaints rate, and claims
        cost as a proportion of premium, for buildings / contents /
        combined. Worth stating why the product split is not even an
        *aggregate* cross-constraint on contents propensity: the three
        lines are bought by different populations — contents-only is
        overwhelmingly renters, buildings-only is landlords and
        mortgage-driven owner cover — so their frequency ratio measures
        who buys which product, not how a peril's cost divides between
        covers. That is selection, not a split. (For scale: home claims
        cost 48% of premium in 2025; acceptance 62% buildings, 71%
        combined, contents down to 74%. Context, not an anchor.)
      - **Restoration-industry escape-of-water cost composition.** The
        trade and loss-assessing literature states the split
        *qualitatively* — structure, floors, ceilings and fixed fittings
        under buildings; furniture, carpets and belongings under
        contents — and quotes whole-claim restoration ranges (~£1,500 to
        £6,000 including drying and alternative accommodation). None
        publishes the **proportion**. "Both are affected" cannot become
        a number.
      **The search is now exhausted**: four anchors, four perils with
      none, three contradictory flood conventions. Do not re-run it
      without new data.
    - **One incidental find worth keeping, unrelated to Phase 3.** Flood
      Re reports spending more repairing Council Tax Band G/H homes than
      Band A/B homes in three of the past four years — independent
      support for the Phase 2c severity relativity (`exp/ct-severity`,
      #30), from a source that had no part in building it.
    - **The one route left, and it needs the user:** the IFoA's
      withdrawn general-insurance research papers, requestable from
      `webarchive@actuaries.org.uk`. **Not contacted** — sending mail on
      the user's behalf needs their say-so, and this is theirs to send.
      Otherwise a claims triangle (top item on the blocked list below)
      remains the only thing that would settle it.

32. **The ABI industry-data subscription, and how to read a withdrawn
    ABI file** (found 2026-08-18; number 30 is still held by
    `exp/ct-severity`, so this skips past it to merge cleanly).
    Two separate things, both worth keeping.

    **(a) The web-archive technique, which WORKS.** Entries #27 and #31
    record ABI PDF and XLSX URLs that 404 after the media-hub move, and
    treat them as dead. They are not dead — they are archived. The
    Wayback CDX API enumerates them without an API key:

        curl "http://web.archive.org/cdx/search/cdx?url=abi.org.uk*\
        &output=text&fl=original,statuscode\
        &filter=original:.*\.(xlsx|xls|csv)$&collapse=urlkey&limit=8000"

    108 ABI spreadsheets survive at status 200. Fetch a specific one
    with the `id_` modifier, which returns the raw bytes rather than
    the archive's HTML wrapper:
    `https://web.archive.org/web/<timestamp>id_/<original-url>`.
    (`WebFetch` cannot reach web.archive.org from this project — use
    curl. Old `.xls` needs `xlrd`, not `openpyxl`.) **Before recording
    any abi.org.uk URL as dead, check the archive.**

    What was actually recovered this way:
    - `general-insurance-overview-statistics-2018.xlsx` — Property
      sheet is Domestic vs Commercial premium/claims/outgo only. No
      peril, no cover split. Dead end, but confirmed rather than
      assumed.
    - `industrydata/samples/1-full-statistics-bundle.xls` → the sample
      of **"General insurance - property (2b)"**, the paid product.
      This is the find.

    **(b) The ABI's paid property dataset is exactly the missing
    reconciliation source — and its schema is now documented.** The
    sample is schema-only (every value cell stripped, which is what a
    sales sample does), but the table structure is complete:
    - **Table 5 — Summary, Gross Incurred Claims AND Number of Claims,
      annual 1988–2012 plus quarterly from 1991Q1.** Columns: FIRE,
      THEFT, BUSINESS INTERRUPTION, WEATHER, ESCAPE OF WATER, DOMESTIC
      SUBSIDENCE, ACCIDENTAL DAMAGE, **OTHER DOMESTIC CLAIMS**, TOTAL.
    - **Table 8 — Breakdown of quarterly DOMESTIC property claims and
      number of claims.** Same peril columns, domestic only.
    - **Table 9 — Weather Damage split into Commercial, Domestic
      Pipes, Domestic Storm, Domestic Flood.**
    - Table 13 — domestic subsidence back to 1987.

    Read that peril list against this model's: fire, theft, weather,
    escape of water, subsidence, accidental damage — **identical, plus
    the residual bucket the model is missing.** This is the dataset
    that settles the claim-count defect in HANDOFF's "Model audit
    2026-08-18": the model implies 578,466 claims against ABI's
    560,000 (103.3%), forcing a negative remainder, and Table 5's
    per-peril *counts* plus OTHER DOMESTIC CLAIMS would resolve it
    directly instead of by moving the AD anchor on judgement. Table 9's
    Domestic **Pipes** column would also replace `EOW_FREEZE_SHARE =
    0.15`, currently a reasoned figure rather than a measured one.
    **It is a paid subscription** (ABI industry data; contact via the
    data-and-analytics team) and the user's call — cost unpriced here.
    It carries **no buildings/contents dimension**, so it does not
    unblock Phase 3.

    **(b2) All 108 were harvested and indexed — nothing else is in
    there.** Do not repeat this sweep. Every archived abi.org.uk
    `.xls`/`.xlsx`/`.csv` at status 200 was downloaded via the `id_`
    modifier (13 MB; the CDX `length` field is the COMPRESSED size, so
    3.3 MB in the index became 13 MB on disk) and every sheet indexed:
    **102 readable files, 441 sheets**, the remaining six being
    login-wall HTML. Result:
    - **No per-peril domestic claim counts anywhere.** Every
      industry-data subscription sample is value-stripped, not just the
      property one — confirmed by opening all of them.
    - **No Domestic Pipes values**, so `EOW_FREEZE_SHARE` stays
      reasoned rather than measured.
    - **No buildings-vs-contents claims split**, at any grain, in any
      file.
    - The three login-walled entries expose real asset paths in their
      `ReturnUrl=` query
      (`annual-general-insurance-overview-statistics---2015.xlsx`,
      `annual-long-term-insurance-overview-statistcs-2013.xls`,
      `household-spending-on-insurance-tables.xlsx`). **All three were
      retried against the archive directly and none has a snapshot** —
      the wall was archived, the asset behind it never was.
    - Two files look relevant by keyword and are not: `Motor.xls`'s
      "Accidental Damage" is a motor claim category, and
      `Home_Contents_Insurance_Table.xls` is a blank room-by-room
      worksheet for a householder to total their own possessions.

    **(b3) One real find in the harvest, and it is evidence for a
    rejection rather than an anchor.**
    `household-spending-on-insurance-tables.xlsx` (ABI, from the ONS
    Living Costs and Food Survey) Table 6 analyses household insurance
    expenditure **by tenure**, giving both average spend and the
    percentage of households holding each cover:

    | tenure | Structure | Contents |
    |---|---|---|
    | Local Authority rented | suppressed | £142.39, **40.7%** |
    | Housing Association | suppressed | £135.43, **41.1%** |
    | Rented furnished | suppressed | £177.12, **24.1%** |
    | Owner occupied, being purchased | £218.87, **93.5%** | £178.03, 93.5% |
    | Owner occupied, owned outright | £201.79, **93.5%** | £164.30, 94.7% |

    Structure cover among renters is so rare the ONS **suppresses the
    cell**, while 93.5% of owner-occupiers hold both. That measures the
    renter-selection confound this file has twice asserted (against the
    FCA GIVM product split, and against the ABI premium ratio) instead
    of merely claiming it: a buildings-only versus contents-only
    comparison sets a ~93%-penetration owner population against a
    24–41% renter one. **Cite this table, not the assertion.**

    **(c) Proxies for the missing Phase 3 split — two tested, both
    refuted.** Recorded so nobody proposes them again:
    - *One universal split for every peril* (from the sum-insured
      ratio, or any scalar). Refuted with no fitting required: the four
      anchors are 25%, 78%, 100% and 48–66% buildings. A 75-point
      spread is not one number.
    - *Buildings share rises with average claim severity.* Fits the
      three clean anchors at R² 0.979 — meaningless on three points and
      two parameters — then fails out of sample. It predicts flood at
      **118.9%**, missing every published convention by 53 to 94
      points, and extrapolates accidental damage to **−14.2%** and
      groundwater to **100.3%**. It also calls escape of water a 26%
      buildings peril, when EoW's cost is drying, plaster, ceilings,
      floors and fixtures: the proxy is measuring "theft steals
      things", not damage physics. **42.9% of claim cost would have
      rested on that extrapolation.**
    The surviving lead is the MCM depth-damage file behind #31's
    48/52 flood convention: it carries explicit
    `Building_Fabric_Damage`, `Household_Inventory_Damage` and
    `Domestic_CleanUp` columns per property type (FHRC licence; a
    cut-down example ships free with Flood Modeller). Its value is not
    flood — flood is already anchored three ways and is only 9.8% of
    claim cost — but **escape of water**, which is 25.1%, has no anchor
    at all, and is the same physical process: water in a dwelling,
    damaging fabric, services and fixtures on one side and inventory on
    the other. That transfer needs stating as an assumption (clean
    water from above, no depth, no contamination) but it is a
    documented one, which is more than the other three unanchored
    perils have.

33. **ABI domestic subsidence, by quarter — and the two bases it is
    published on** (acquired 2026-08-27, `data/abi_subsidence.csv`,
    validated by `scripts/check_abi_subsidence.py`).
    Gate 0 of the temperature-driven subsidence work. 26 rows, 2018Q2 to
    2026Q2, every figure carrying its verbatim quote and its source URL.

    **There is no ABI dataset.** The Property Insurance Tracker exists
    only as one press release per quarter, each quoting one or two
    numbers plus a year-on-year delta. Several URLs 404 after the
    media-hub move — recovered via the #32 web-archive technique, which
    worked again exactly as documented. Archive timestamps are recorded
    in each row's note so any figure can be re-read.

    **Re-checked 2026-08-31, because the site was publishing five dead
    citation links.** The years page renders `ABI.sources` as clickable
    links, so a 404 in the CSV is a 404 a reader clicks. Three of the
    five turned out to be live again under renamed media-hub slugs, and
    each was verified by reading the article and matching the figures
    this repository quotes from it — not by trusting a status code:

    | was | now | verified against |
    |---|---|---|
    | `2023/3/sinking-uk--last-summers-…` | `media-hub/news-post/surge-in-subsidence-payouts` | £219m, 23,000, 18,000, £9,600 — all four verbatim, and it still carries the old "Sinking UK" headline as its first line |
    | `2026/1/abi-shares-cold-weather-advice-…` | `media-hub/news-post/the-abi-issues-advice-for-homeowners-and-drivers-ahead-of-upcoming-cold-weather` | "roughly 8,000 claims … £250 million … average claim cost almost £33,000" |
    | `2026/2/adverse-weatherpushesproperty-…` | `media-hub/news-post/adverse-weather-pushes-property-insurance-payouts-to-61-billion-in-2025` | already present as a second row; the old URL was a dead duplicate of a live one, so the page showed "ABI 2026-02 · ABI 2026-02" with one broken |

    **Two are withdrawn from abi.org.uk and are archive-only**, confirmed
    absent from ABI's own `sitemap.xml` (352 live news posts): the 2018
    "subsidence claims quadruple" release and the 2025-08 "insurance
    support tops £150 million" release. The second is not a small loss —
    it is where `sev_subsidence = £17,264` comes from, the Gate 1
    severity anchor that is live in the model. Both rows already carry
    their archive timestamps, which remain the citation of record.

    **Do not "fix" those two by guessing a media-hub slug.** ABI's site
    is a single-page app that returns HTTP 200 for *any* slug under
    `/media-hub/news-post/`, including deliberate nonsense, and echoes
    the slug into the HTML — so both a status check and a keyword grep
    will tell you a page exists when it does not. The only reliable
    tests are ABI's `sitemap.xml`, and rendering the URL in a real
    browser: a missing article renders the literal text **"No news
    articles found."** Verified against a control on both sides before
    any of the three remappings above was accepted.

    **(a) The ABI publishes subsidence on TWO bases and never says so.**

    | basis | what it is | which releases |
    |---|---|---|
    | `incurred_notified` / `incurred_ultimate` | value of claims **made** in the period, an estimate that moves as monitoring finishes | the 2018 and 2022 surge releases |
    | `paid_in_period` | cash paid **during** the quarter, whenever notified | the quarterly Tracker |

    They are not interchangeable and dividing one by the other is
    meaningless. Each is internally sound: 2022's £219m ÷ 23,000 claims
    = £9,522 against a published £9,600 average incurred, closing to
    0.8%.

    **(b) The paid series cannot carry a weather signal.** Subsidence
    runs a monitoring period — often a full seasonal cycle — before
    repair, so paid lags notification by quarters to years. It shows up
    directly in the data: **2025 paid splits 49.8% H1 / 50.2% H2**,
    dead flat, while **2022 notified is 78% H2**. Paying smears the
    summer into a straight line. Any curve against a temperature index
    must be fitted to NOTIFIED COUNTS.

    **(c) `sev_subsidence = 17_820` is on the wrong period.** It is the
    average claim for **Q1 2026** (ABI 2026-05: "rising 9% from £16,295
    in 2025 to £17,820 in the first quarter of 2026"), paired in
    `build_model.py` with `subsidence_paid = 307e6`, which is **FY2025**
    (ABI 2026-02). `HANDOFF.md` recorded this as "ABI 2025 paid AND ABI
    2025 average, one release" — wrong on both counts, corrected there.
    Every period-consistent alternative raises the implied count:
    £16,295 → 18,840 (+1,612), £17,264 (H1 2025) → 17,783 (+555),
    against the published 17,228. All of them worsen the claim-count
    budget in `anchor_budget.py`. **Not yet changed** — that is Gate 1
    and it prices on its own.

    **(d) The surge signature, for whatever curve gets fitted.** 2018
    Q2→Q3 notified count went **2,500 → 10,000 (×4.0 in one quarter)**,
    which the ABI called the largest quarter-on-quarter jump "since
    records began more than 25 years ago" — so a quarterly series
    exists internally back to at least 1993, none of it published.
    2022: 23,000 claims, 18,000 of them in H2.

    **(e) One restatement and one open gap.** Q2 2024 was published at
    £60m ("the highest quarterly figure on record") and restated to
    £59m a quarter later; both rows are kept, as with the 2023 weather
    figure in `abi_annual.csv`. **UNRECONCILED:** Q1–Q3 2024 paid sums
    to £178m against a derived FY2024 of £280m, implying a Q4 of £102m,
    1.55× the largest published quarter. Q1 and Q2 are both confirmed
    from primary text, so the suspect is FY2024 = 307 − 27 — and the
    2025-02 FY2024 release carries no subsidence line at all.

34. **Drought climatology — the subsidence frequency relativity (the
    Gate 2 SMD curve, published 2026-08-31).** `data/smd_climatology.csv`
    holds each polygon's 1991–2020 mean of `cwd_yr_max_mm`: the annual
    peak of the running water deficit max(cumsum(PET − rain), 0), reset
    every 1 January, computed from **HadUK-Grid v1.3.2.ceda 1 km DAILY**
    tasmin/tasmax/rainfall (Met Office via CEDA, OGL; account needed —
    the same wall as #24). The 174 GB of daily grids never touched a
    disk whole: `scripts/haduk_1km_stream.py` fetched, reduced and
    deleted year by year on CI (`haduk-1km.yml`, run 33319459184 for
    the full 66-year table; `haduk-1km-sectors.yml` for the sector
    grain), and `scripts/make_smd_climatology.py` reduces the annual
    table to the committed climatology. `scores_real.drought_from_haduk`
    loads it with EXACT coverage required — a missing name means the
    file is at the wrong grain (the ct_bands lesson, #30).

    At the sector grain, the 13 sectors whose polygon is empty (no
    geometry, so no centroid, no Hargreaves Ra, no PET) take their
    parent district's climatology
    (`make_smd_climatology.py --fill-empty-from`), printed sector by
    sector at build time — the children.csv posture, not a silent
    patch. Coherence between the grains: Spearman +0.9964 between
    per-district sector means and the district table, median relative
    difference 0.000.

    **Why this index:** aggregated nationally it recovers 5 of the 6
    canonical UK subsidence years (1976, 1995, 2003, 2018, 2022;
    misses 2006); the capped 150 mm bucket saturates (94–96% of
    districts peg) and the uncapped multi-year run is a trend, not a
    year index. Full derivation in HANDOFF's Gate 2 sections.

    **The share (SUB_DROUGHT_SHARE = 0.565)** is the ABI's own
    arithmetic by two agreeing routes: the 2018-12 release frames
    2,500 claims/quarter as the pre-surge baseline (⇒ 10,000/yr), and
    the 2022 release attributes 13,000 of 23,000 claims to the drought
    ⇒ 13/23 = 0.565 (2022's H1 of 5,000 = base/2 cross-checks the same
    base — all from the releases in #33). Zurich's "An in-depth look
    at subsidence" brackets it: ~60% of upheld claims are root-induced
    clay shrinkage in an average year, ~85% in a surge year.

    **The measured caveat:** the PET is Hargreaves–Samani (FAO-56
    eq. 21 Ra), which runs ~a third high in a maritime climate, and a
    uniform bias does not cancel out of the deficit. Measured
    (`scripts/check_pet_sensitivity.py`, at 1 km on CI run 33404395072
    and at 5 km locally): PET × 0.85/0.70 moves the LEVEL
    (240 → 121 mm) and not the MAP — Spearman ≥ +0.9983 — and the
    level is exactly what the ABI calibration re-pins, so only the map
    is used. If the level itself is ever needed, the citable fix is
    **Hydro-PE** (Penman–Monteith on the same HadUK-Grid met, 1 km
    daily 1969–2021, CC-BY,
    doi:10.5285/9275ab7e-6e93-42bc-8e72-59c98d409deb).

35. **The temperature page's two national series (published
    2026-08-31).** `data/temperature_series.json` — the household-weighted
    national annual series of the peak within-year soil water deficit and
    of air-frost days, 1960–2025, plus their least-squares trends, era
    means and the drought backtest. Same source and same extraction as
    #34 (HadUK-Grid 1 km daily, Met Office via CEDA, OGL), reduced by
    `scripts/make_temperature_series.py`; the 12 MB per-district annual
    table stays gitignored and the ~4 KB reduction is committed, the
    make_smd_climatology.py rule.

    Both series are the model's OWN instruments rather than a tidier
    public index, so the page cannot illustrate a different model from
    the one it links to. Weighted by census households, so the national
    figure is what an average policy experienced rather than an average
    square kilometre. Measured: drought **+3.6%/decade** (p = 0.036),
    frost **−7.5%/decade** (p = 0.000204, −20.5% between the 1961–1990
    and 1991–2020 normals).

    **Every figure on the page is injected at build time — none is typed
    into the template.** That sentence stood here while it was false: at
    first publication the page carried thirteen hand-typed numbers (the
    ten of the bad-year decomposition, the premium, and the two peril
    shares), all measured pre-Gate-2 and all drifted by the time it went
    live. They were converted to placeholders on 2026-08-31; HANDOFF's
    temperature-tab entry records what each one said and why typing them
    is the defect this repository keeps rediscovering.

    The same page publishes the freeze dose-response from
    `data/freeze_share_pricing.json` (CI run 33431160741, six full
    simulations) and the published curve's own churn from
    `data/smd_curve_pricing.json` (CI run 33410640013, seven full
    simulations), both committed for the reason `seed_sensitivity.json`
    is: a measured range quoted from memory is a measured range that
    drifts. The SMD artifact was the last priced gate without one — its
    churn figures had been quoted from a run ID for a day. `build_site`
    looks its row up by the SHIPPED index and share (`cwd_yr`,
    `SUB_DROUGHT_SHARE`) rather than by variant key, and raises if that
    does not match exactly one priced variant, so re-tuning the share
    cannot silently leave the page describing a variant the model no
    longer runs.
    Companion measurement, not a data source:
    `scripts/measure_frost_era.py`, which tested re-aiming the frost
    climatology and rejected it against within-era controls.

36. **The two countries' burglary taxonomies — how the Scottish theft
    override was checked (measured 2026-09-01).** Not an input to the
    model: neither table is read at build time, and nothing changed as a
    result. Both are cited here because the check turned on them.

    - **Recorded Crime in Scotland 2024-25, Table A6** (gov.scot, OGL
      v3.0), the source of `SCOTLAND_HOUSEBREAKING_2024_25`. Downloaded
      to `data/cache/` (gitignored, refetchable). Theft by Housebreaking,
      2024-25: Dwelling **3,661**, Non-dwelling **1,531**, Domestic
      **5,192**, Other **2,189**, Total **7,381**. The model uses the
      Total.
    - **Crime in England and Wales: Appendix tables, year ending March
      2026 edition, Table A5a** (ONS / Home Office police recorded
      crime, OGL v3.0),
      `https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/crimeandjustice/datasets/crimeinenglandandwalesappendixtables/yearendingmarch2026/appendixtablesyemar2026.xlsx`.
      Splits E&W burglary exactly the way Scotland splits housebreaking.
      Summed over Apr 2023 – Mar 2026, which brackets the police.uk
      window in #25: Residential **503,171**, of which home **375,677**;
      total **734,529**. Residential share **68.5%** (68.7 / 67.9 / 68.9
      by year — stable, so the window choice does no work).

    The taxonomies line up: E&W residential 68.5% against Scottish
    domestic 70.3%, E&W home-only 51.1% against Scottish dwelling 49.6%.
    That is what makes the comparison fair, and it is why the naive
    reading fails — see LIMITATIONS §5 and `price_scotland_theft.py`.
    Note the file naming: the year-ending-March-**2025** edition is NOT
    at the analogous URL (404); the 2026 edition carries the full time
    series and is the one to fetch.

## Budget: zero, decided 2026-08-31

**The user has decided this project will not spend money.** That is a
standing constraint, not a current cashflow position, so the licensed
datasets below are **out of scope permanently** rather than "not yet
afforded" — nobody should re-cost PAF/AddressBase or BGS superficial
thickness hoping the answer changed. Anything that needs a paid licence,
a paid API tier, or a commercial agreement is closed.

What this does NOT close, and the distinction is the whole point of
keeping the list: **free-but-gated** sources stay open. MIDAS Open was
never money-blocked, only one registration away, and it is now live and
carrying the model's gust component. CEDA HadUK-Grid was the same story.
So the test for anything below is "does it cost money", not "is it
inconvenient" — a registration, an email, or an OGL attribution is a
cost the project can pay.

Bearing on the model as it stands: the assumed θ(s) copula forms and the
ABI-calibrated compound Bernoulli×LogNormal are **permanent**, because
the claims triangle that would replace them cannot be bought at any
price anyway (see below) and is not merely expensive. `SUP_WEIGHT` stays
a bounded 0.5 prior. Census households smeared over each district stays
the exposure basis. These are now documented limits rather than
outstanding work, and LIMITATIONS records them as such.

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

- **EoW dwelling-age slice (Phase 2b) — dropped for want of an anchor
  (2026-08-17).** CTSOP4.1 gives build period per LSOA for the full
  E&W stock (OGL, trivial to fetch), but no UK publication quantifies
  the dwelling-age → escape-of-water frequency relationship: every
  hit is qualitative "older pipes corrode" marketing copy (Alan
  Boswell, Oakleafe, MA Group's rooms-affected trend), and the US
  figures that do exist (ISO/III ~1.6%/yr water-damage claim rate)
  are a different market and peril mix. Without a citable number the
  slice size would be an undocumented knob, so EoW's geography stays
  freeze-only. Revisit only if an insurer publishes age-banded claim
  rates.
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
  `data/sectors_gb.gpkg` (25 MB, gitignored; ~5 min to rebuild).
  **No longer just geometry (2026-08-12): the model was rebuilt on them and
  is PUBLISHED alongside the district one** — `/sectors.html`, output
  `data/sectors_risk.geojson`. Every hazard was re-aggregated over the
  10,398 sectors (three of the four raster fetches ran on GitHub runners;
  the EA 403'd them for rivers/sea after ~3.5 h, so that one was fetched
  locally). Validated against Scotland's official sectors by
  `scripts/validate_sectors_scotland.py`: sector IoU **0.706** vs
  district IoU **0.689**, i.e. the Voronoi step adds no error beyond the
  district outlines it inherits. The climate-change editions were
  re-rasterised over the sectors too (2026-08-12): surface water and
  depth on runners, rivers/sea from a laptop - the EA 403s runner IPs
  for that WMS after ~3.5 h, the same block BGS applies. 8,730 of
  10,398 sectors fall inside EA climate coverage.
