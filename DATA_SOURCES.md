# Data sources register

Every external dataset used by the model: what it is, where it comes from, how
it is fetched, its licence, and any access quirks discovered along the way. All
sources are **open data** (Open Government Licence v3 unless noted). Access
dates: 2026-07-29/30.

| # | Dataset | Publisher | Fetched by | Local file(s) |
|---|---------|-----------|------------|---------------|
| 1 | UK postcode district polygons | missinglink/uk-postcode-polygons (OS/Wikipedia-derived) | `git clone` | `data/uk-postcode-polygons/` (120 GeoJSONs, 2,736 districts) |
| 2 | BGS Geology 625k bedrock | British Geological Survey | `scripts/fetch_bgs.py` | `data/bgs_625k_bedrock.geojson` (~32 MB, 11,244 formations) |
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
| 14 | Daily 10 m wind-gust maxima 1990–2024 (ERA5 reanalysis) | ECMWF via Open-Meteo archive API (CC-BY 4.0; **not** Met Office) | `scripts/fetch_gusts.py` | `data/gusts.csv` (90 grid points, p98 + Gumbel-fitted 1-in-50 gust: 124–196 km/h) |
| 15 | Daily gusts, precipitation and max temperature 1990–2024 (ERA5) | ECMWF via Open-Meteo (CC-BY 4.0) | `scripts/fetch_history.py` | `data/history.csv` (12 points → per-year storm days, peak gust, wettest 5-day, JJA deficit) — the backtest |
| 16 | UK domestic claims by peril, 2025 | Association of British Insurers (published statistics) | manual (figures embedded in `build_model.py`) | Calibration anchors: storm £244m @ £2,450 avg; flood £312m @ £30,000; subsidence £307m @ £17,820; ~15.5m policies; £3.4bn / 560,000 all-perils home claims for context |

## Endpoints

1. **Boundaries** — `https://github.com/missinglink/uk-postcode-polygons`
   (clone; GB only, no BT/Northern Ireland).
2. **BGS bedrock** — OGC API Features:
   `https://ogcapi.bgs.ac.uk/collections/bgsgeology625kbedrock/items`
   (paged via `next` links, 500/page). BGS's old
   `/arcgis/rest`-style endpoints are dead.
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

## Not used / dead ends (so you don't repeat them)

- `environment.data.gov.uk/arcgis/rest/...` — EA's old ArcGIS root: gone.
- Legacy `risk-of-flooding-from-surface-water-extent-*` spatialdata slugs: 404
  (superseded by NaFRA2).
- CEDA HadUK-Grid NetCDF downloads: directory listing is anonymous but files
  are login-walled (the "downloads" are 8 KB HTML login pages).
- SEPA surface water via FeatureServer: 8–10 M features — infeasible; use the
  raster route.
- BGS GeoSure / GeoClimate, OS AddressBase: licensed, not open.
