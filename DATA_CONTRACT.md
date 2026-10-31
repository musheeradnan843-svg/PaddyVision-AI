# PaddyVision AI — Data Contract and Provenance

**Status:** initial integration contract, 2026-10-19  
**Study area:** user-supplied Sekinchan polygon, approximately 66.878 ha (about 67 ha)  
**Purpose:** define how each dataset may enter the connected Digital Twin without confusing local observations, external model-training data, references, and simulations.

## 1. Non-negotiable data rules

1. Every value shown in the product must retain its source, timestamp or period, spatial support, processing status, and evidence class.
2. Only measurements collected in the Sekinchan study area may be called local ground truth. A template, estimate, reference record, synthetic row, or external training image is not ground truth.
3. An external model may be demonstrated as an external model, but its output must not be presented as a Sekinchan prediction until it has been evaluated on suitable local labels.
4. Never convert a missing value into zero unless zero is the documented meaning. Preserve nodata, quality flags, fill source, and confidence.
5. The 66.878 ha GeoJSON polygon is the area-of-interest geometry. Clip/ mask map displays to this polygon. Do not infer field area from a raster bounding box or count coarse soil cells as 10 m field pixels.
6. Keep raw inputs immutable. Store derived products separately with reproducible processing metadata.

## 2. Evidence classes

| Class | Meaning | Product wording | Permitted use |
|---|---|---|---|
| `LOCAL_OBSERVED` | Measurement or observation actually collected in the Sekinchan study area, with date, location, method, and provenance | “Observed” / “Measured” | Local monitoring and, after QA, validation |
| `LOCAL_REMOTE_SENSING` | Satellite-derived value whose pixel intersects the study area | “Satellite estimate” | Spatial/time-series monitoring with source and quality flags |
| `MODELLED_EXTERNAL` | Model output or training data from another place or domain | “External model/demo” | Method prototype; no local-performance claim |
| `REFERENCE` | Calendar, literature, soil-grid estimate, or other contextual source | “Reference” / “Context” | Context only, with source and limitations |
| `SYNTHETIC` | Simulated data created for software testing | “Synthetic demo” | UI, schema, and pipeline testing only |
| `TEMPLATE` | Empty schema or form awaiting real records | “Awaiting field data” | Data collection workflow only |

## 3. Dataset register

### A. Sekinchan satellite and spatial data

- **Location provided:** `C:\Paddyvision_AI_Dataset\01_Satellite_Imagery_Spatial_Data\`
- **Files:** `paddyvision_v3_stack_2023_2025.tif`, `paddyvision_v3_pixels_panel_2023_2025.csv`, `paddyvision_v3_window_summary_2023_2025.csv`, `README_paddyvision_v3_merged.md`
- **Class:** `LOCAL_REMOTE_SENSING`
- **Coverage:** Sentinel-1/2-derived time series for the study-area grid, 2023–2025. Verified TIFF metadata: EPSG:32647, 10 m, 157 × 124, 558 bands. The panel has 6,681 unique coordinate pairs and 706,394 rows.
- **Meaning:** Sentinel-2 bands/indices, Sentinel-1 VV/VH, source/fill indicators, elevation, and the static `gsw_occurrence` / `gsw_seasonality` water-history layers. The panel README identifies elevation in metres from an approximately 30 m source model. The supplied CSV/TIFF metadata does not document units, native resolution, or time period for the GSW layers; show their stored values without assigning an unverified physical unit.
- **Required handling:** respect `s2_source`, `s2_fill_confidence`, `bright_flag`, `s1_outlier_flag`, nodata, and each layer’s native temporal/spatial resolution. `v2_monthly_fill` is a monthly value reused in a ten-day slot; do not treat it as a real ten-day observation. Keep real 10-day-only and filled views distinguishable.
- **Audit notes:** the window summary contains 111 windows; the panel has 109 distinct window IDs, with no panel rows for `2023-021` and `2025-321`. Separately, `usable_s2_or_s1=0` for eight summary windows; six of those have panel rows and nonzero S2 counts (for example, `2025-311` has 4,426 `n_s2_v3` values and 66.2% post-fill S2 coverage). The supplied merged README does not define this usability flag well enough to reconcile those cases. Preserve the flag as supplied and show the discrepancy rather than treating it as synonymous with “no values.” The pixel-panel QA flags are stored as `0.0`, `1.0`, or blank; blank is missing/not applicable, not a zero/clear flag. The panel has 319 rows at three repeated coordinate locations that fall outside the supplied polygon under point-in-polygon checking; clip these edge rows from polygon-only statistics. The README also says about 242 edge pixels occur only in the TIFF grid. Do not silently equate the panel and full raster masks.
- **Spatial identity:** use `sekinchan_study_area_polygon.geojson` as the display and analysis AOI. Satellite raster footprint and polygon align closely, but polygon clipping still applies.

### B. Sekinchan boundary

- **Location provided:** `C:\Paddyvision_AI_Dataset\04_Soil_and_Ground_Truth\02_Boundary\sekinchan_study_area_polygon.geojson`
- **Class:** `LOCAL_REMOTE_SENSING` (AOI geometry; not a field measurement)
- **Area:** the package QA reports 66.878 ha; feature property rounds to 66.8 ha. Treat 66.878 ha as the reported GIS area and cite the geometry/CRS in derived outputs.
- **Coordinate reference:** GeoJSON EPSG:4326, lon/lat order. Reproject for metric operations; do not label the polygon as an administrative boundary for all of Sekinchan.

### C. Historical weather

- **Location provided:** `C:\Paddyvision_AI_Dataset\02_Historical_Weather_Data\`
- **Files:** daily and hourly Sekinchan weather CSVs, 2021–2025, plus README and validation script.
- **Class:** `REFERENCE` / regional weather context (`Open-Meteo`), not a field sensor.
- **Use:** date-aligned weather context, charts, and exploratory joins with satellite windows/calendar.
- **Limits:** one representative grid location; weather does not confirm crop condition, disease, irrigation, or yield. Show provider/location and time aggregation.

### D. Paddy crop calendar

- **Location provided:** `C:\Paddyvision_AI_Dataset\03_Paddy_Crop_Calendar\sekinchan_paddy_crop_calendar_reference.csv`
- **Class:** `REFERENCE`
- **Use:** expected season and crop-stage context.
- **Limits:** recurring reference calendar, not verified actual sowing/transplanting/harvest dates for each year or field. A stage displayed from this file must be named “calendar-estimated stage” until actual dates are collected.

### E. Soil and ground truth

- **Location provided:** `C:\Paddyvision_AI_Dataset\04_Soil_and_Ground_Truth\`
- **Files:** final study polygon, 14 SoilGrids-derived layers and stack, `polygon_coverage_fraction.tif`, `soil_summary.csv`, blank soil/yield templates, validation script, README, QA report.
- **Soil class:** `REFERENCE` (`SoilGrids` model estimates). **Templates:** `TEMPLATE`.
- **Resolution/limits:** native cells are roughly 252 × 264 m; the 66.878 ha AOI contains only about ten pixel centres. These data cannot show within-field soil variation at 10 m. SOC and nitrogen are explicitly low confidence and must not be used for recommendations or model features without local lab validation. Other layers remain gridded estimates, not field samples.
- **Ground truth status:** no completed local soil-lab or yield measurements were present in the supplied package. Empty templates are not observations.

### F. Pest and disease references and Paddy Doctor images

- **Location provided:** `C:\Paddyvision_AI_Dataset\05_Pest_and_Disease_Data\`
- **Reference files:** pest/disease reference, risk context, source list, and blank observation template.
- **Reference class:** `REFERENCE`; template class: `TEMPLATE`.
- **Paddy Doctor image set:** external labelled training classes under `Paddy_Doctor\train_images\<class>\`; test images were supplied in a separate unlabelled-looking `test_images` folder. Class names in training directories are dataset labels, not Sekinchan outbreak records. Verify test-set label availability and dataset licence before evaluation or redistribution.
- **Permitted use:** build/compare an image classifier as `MODELLED_EXTERNAL`, with a clear external-data label. Do not connect predictions to the Sekinchan map as confirmed disease, and do not use weather or satellite indices alone as a disease label.
- **Local data status:** no confirmed local pest/disease observations or Sekinchan-labelled images were supplied.

### G. Synthetic yield examples and outlook

- **File:** `data/demo/sekinchan_yield_synthetic.csv`
- **Class:** `SYNTHETIC`; rows for 2023–2025 are generated examples and are not local harvest observations.
- **Identity:** `SEKINCHAN-AOI-66.878HA` / `AOI-AGGREGATE-NOT-SUBPLOT` denotes the full AOI aggregate only; it does not define a real sub-plot. The 66.878 ha value is the reported GIS AOI area, not measured harvested area.
- **Yield/weight:** synthetic tonnes per hectare and generated harvest tonnes are linked arithmetically using the AOI reference area. They must not be described as measured harvests.
- **2026–2027:** season-specific ordinary least-squares trend scenarios are calculated solely from the synthetic 2023–2025 examples. They are demonstration outputs, not an ML model, forecast validated against field harvests, or operational prediction. No local yield ground truth is available.
- **Product wording:** use “Synthetic example” for 2023–2025 and “Synthetic trend scenario” for 2026–2027. Keep the caveat visible in dashboard/API/export. Do not report accuracy or use these values for agronomic decisions. Replace the synthetic source with measured, plot-linked harvest records before training or validating any Sekinchan yield model.
- **Connected context:** the yield panel may show calendar-reference dates, AOI-clipped Sentinel-2 direct-window mean NDVI, monthly-fill window counts, and regional historical weather summaries for the selected 2023–2025 season. These are displayed as context only and do not feed the synthetic yield values or trend scenarios. The calendar dates are not verified field dates; weather is a regional archive point, not an in-field sensor. For 2026–2027, satellite and weather fields must remain unavailable because the supplied archives end in 2025.

### H. Water and irrigation

- **Location provided:** `C:\Paddyvision_AI_Dataset\06_Water_and_Irrigation_Data\`
- **Files:** synthetic event/observation/rainfall CSVs, generator and README.
- **Class:** `SYNTHETIC`.
- **Use:** demonstrate water timelines, event schemas, dashboard states, and pipeline joins when visibly marked “Synthetic demo.”
- **Limits:** records are generated (seed 42), use `SIM-F01`–`SIM-F12`, are not linked to the 67 ha AOI, and are not actual Sekinchan measurements or local irrigation schedules. Never use them for local validation, water-use claims, or a Sekinchan-trained model.
- **Local data status:** actual field water-depth observations, irrigation events, canal schedules, and gauge rainfall were not supplied.

### I. Legacy project model datasets (keep separate from Sekinchan data)

| Existing component | Source/domain | Class | Contract decision |
|---|---|---|---|
| U-Net segmentation | WeedyRice UAV RGB and masks, An Giang, Vietnam | `MODELLED_EXTERNAL` | Preserve as external research/prototype. Confirm mask semantics and license. Do not call mask pixels weeds/disease until label definition confirms it. Do not map the illustrative mask projection as georeferenced Sekinchan area. |
| CNN yield model | RiceUAS five-band multispectral UAV, Arkansas, USA | `MODELLED_EXTERNAL` | Retire from active Digital Twin decisions because the notebook reported test R² near −0.004. Keep artifacts/notebook for reproducibility until deliberate archival. Never display as Sekinchan yield. |
| UAV index lab | Five aligned RiceUAS TIFF bands: blue, green, red, red edge, and NIR | `MODELLED_EXTERNAL` | Calculate deterministic NDVI/NDRE/GNDVI previews and summaries only. Verify same-plot selection; reflectance scale/calibration is unverified. Do not georeference into Sekinchan or present values as calibrated agronomic thresholds. |
| Weather/yield Random Forest | `Weather_Factors_And_Yield_Dataset.csv`, external station/year records (Bangladesh Aman per prior project notes) | `MODELLED_EXTERNAL` | Keep separate; target is a normalized Aman yield score, not t/ha unless target mapping is verified. No local yield prediction claim. |
| RiceUAS weather archive | RiceUAS historical context | `REFERENCE` | Do not mix with Sekinchan Open-Meteo weather or treat it as model input unless a documented model contract requires it. |

## 4. Join and storage keys

- **Spatial key:** study-area AOI ID plus raster CRS/grid identity. Use pixel coordinates/row-column derived from a documented grid transform, not rounded lat/lon alone, for raster joins.
- **Temporal key:** retain source date/window start/end and calendar year. A ten-day satellite window, daily weather record, hourly weather record, crop-calendar interval, and synthetic event are different temporal resolutions; aggregate explicitly before joining.
- **Field key:** no actual subfield/block polygons were supplied. Synthetic `SIM-Fxx`, Paddy Doctor IDs, and external UAV plot IDs must never be joined to the real AOI or to each other as if they identify the same field.
- **Model key:** each prediction must record model/version, training dataset/domain, input time and area, preprocessing, confidence/quality status, and whether local validation exists.

## 5. Product-facing status labels

Use these labels consistently in maps, charts, tooltips, API responses, and exports:

- `Satellite observation` — include acquisition/composite window and source/fill badge.
- `Weather context` — include provider, location, and aggregation.
- `Soil reference estimate` — include SoilGrids source, coarse resolution, and confidence.
- `Calendar-estimated crop stage` — reference schedule only.
- `Synthetic water demo` — persistent visible badge; no local map linkage.
- `External model demo` — name the training domain; no Sekinchan accuracy claim.
- `Field observation` — only for a completed, evidence-backed local record.
- `Awaiting local validation` — for outputs needing local ground truth.

## 6. Current readiness and next integration gate

**Ready for first connected slice:** AOI polygon + 2023–2025 satellite stack/panel/summary, with edge clipping and source/fill quality preserved.

**Context-only layers:** Open-Meteo weather, crop calendar, and coarse SoilGrids estimates.

**Demo-only layers:** synthetic water and external image/model demonstrations.

**Not ready for local prediction claims:** yield, disease, soil recommendations, irrigation/water status, or any field-level accuracy statement. Local labelled yield, disease, soil, and water observations are not yet available.

Before adding a layer to the operational map, record its source/version, CRS, resolution, timestamp or period, nodata/quality semantics, spatial coverage, and evidence class. The next implementation step is to wire the clipped satellite time-series to the AOI map/timeline using this contract; it does not require the database password and must not expose credentials in source control.

### Illustrative UAV mission scenario (Phase 5)

- **Class:** `SYNTHETIC`; the route is generated from the AOI polygon and user-selected assumed flight settings. It is not an observation, survey result, or operational flight plan.
- **Geometry:** the current planner accepts only one convex GeoJSON exterior ring. It reprojects the supplied Sekinchan boundary from EPSG:4326 to EPSG:32647 for metric calculations and clips displayed footprint polygons to that boundary.
- **Assumptions:** constant altitude, camera field of view, side overlap, cruise speed, flat ground, nadir camera, and straight connectors. Displayed 3D height/time are schematic, not a metric simulation.
- **Excluded:** turning radius, climb/descent, wind, battery reserve, obstacles, airspace, permissions, aircraft/camera calibration, terrain clearance, and coverage verification. Estimated flight time is path length divided by assumed speed only.
- **Product wording:** label every scenario “Illustrative” and `SYNTHETIC`; never call it flyable, legally cleared, or a guaranteed coverage plan. It must not imply that a UAV flight occurred over Sekinchan.

### External image-model run history (Phase 6)

- Saved U-Net run metadata is `MODELLED_EXTERNAL` and identifies the WeedyRice UAV image domain in An Giang, Vietnam. A run-history row is not a Sekinchan field inspection, disease report, or `LOCAL_OBSERVED` record.
- The read-only history API returns run ID, model label, and timestamp only. It does not expose server filesystem paths or promote mask coverage to a field-area measure.

### Bounded Field Intelligence Agent (Phase 7)

- **Access:** deterministic router to internal read-only service functions only. It has no web access, database write tool, model training/inference tool, filesystem browser, or ability to trigger field actions.
- **Supported data tools:** selected/latest AOI-clipped satellite-window summary (`LOCAL_REMOTE_SENSING`), selected-window regional weather and recurring crop-calendar context (`REFERENCE`), coarse soil summary (`REFERENCE`), and explicitly requested synthetic yield/water examples (`SYNTHETIC`). Citations return tool name, source, evidence class, and scope details.
- **Uncertainty:** satellite values remain remote-sensing estimates; weather is regional context; calendar stages are recurring references; soil grids are coarse model estimates; synthetic examples are not field observations.
- **Refusals:** no local yield prediction, pest/disease diagnosis, soil/fertilizer prescription, irrigation scheduling/status claim, or chemical advice. The agent must state when there are no suitable local labels or measurements rather than infer them from proxies.
- **No implicit joins:** synthetic campaigns, external disease imagery, Arkansas UAV products, and the 67 ha Sekinchan AOI are not merged into one field identity by the agent.
