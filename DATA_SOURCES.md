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
      Scotland, not merely fill blanks. Northern Ireland (PSNI) is in
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
      line that also covers storm and flood). Cross-check that closes
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


32. **The ABI industry-data subscription, and how to read a withdrawn
    ABI file** (found 2026-08-18; numbers 30 and 31 are taken by the
    two unmerged branches, so this skips to 32 to merge cleanly).
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
