# PaddyVision AI

### Sekinchan Paddy Digital-Twin Prototype

PaddyVision AI is a research and demonstration platform that brings satellite
observations, environmental context, soil references, synthetic examples, and
external image-model demos into one interactive paddy dashboard. Its study area
is a user-supplied **66.878 ha area of interest (AOI) in Sekinchan, Malaysia**.

The platform is designed to make the origin and limitations of each layer
visible. It is **not** a locally validated crop-yield predictor, disease
diagnostic system, irrigation record, or field-management recommendation tool.

## Contents

- [What is included](#what-is-included)
- [Dashboard and digital twin](#dashboard-and-digital-twin)
- [Data sources and evidence limits](#data-sources-and-evidence-limits)
- [Backend and API](#backend-and-api)
- [Models and notebooks](#models-and-notebooks)
- [Databases and file storage](#databases-and-file-storage)
- [Project layout](#project-layout)
- [Setup and run](#setup-and-run)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Known limitations](#known-limitations)
- [Data and responsible-use policy](#data-and-responsible-use-policy)

## What is included

| Component | Purpose |
|---|---|
| Interactive dashboard | Browse study-area context, satellite time windows, weather/calendar context, soil references, synthetic yield/water examples, and image-model demos. |
| 2D satellite views | Explore Sentinel-1/2-derived metrics, observation/fill sources, yearly comparisons, paired-pixel differences, and AOI-clipped relative grid screening. |
| 3D field scene | Explore an illustrative crop scene with satellite and soil-reference overlays. |
| FastAPI service | Serves digital-twin data, the bounded read-only Field Intelligence Agent, and external Paddy Doctor/U-Net image demos. |
| Research notebooks | Inspect datasets and reproduce exploratory/training workflows for segmentation, image classification, and historical yield experiments. |
| Data contract | Records provenance, evidence classes, known data-quality issues, and permitted interpretation. |

## Dashboard and digital twin

The browser application is in `frontend/`. The entry point is
[`frontend/index.html`](frontend/index.html); the Three.js scene is implemented
in [`frontend/script.js`](frontend/script.js).

### Sekinchan context and satellite layers

- A gallery presents five bundled Google Earth Pro reference images, including
  regional, field, boundary, 2020, and 2024 views.
- Select a satellite window and inspect NDVI, NDMI, NDWI, Sentinel-1 VV, or
  Sentinel-1 VH. Sentinel-2 source selection distinguishes direct observations
  from monthly fills.
- Select the static `elevation_m`, `gsw_occurrence`, or `gsw_seasonality`
  layers independently of the time window. Elevation is shown in metres from
  an approximately 30 m source model; GSW values retain their stored scale
  because the supplied metadata does not specify units, native resolution, or
  time period. These
  are AOI-clipped map/texture overlays, not current water measurements or a
  surveyed terrain model.
- Temporal layer responses expose `bright_flag` and `s1_outlier_flag` counts;
  `bright_flag=1` marks possible haze and `s1_outlier_flag=1` follows the
  package threshold (VV > 5 dB or VH > -5 dB). Missing flag values remain
  distinct from zero. Some source summary rows mark a window unusable despite
  nonzero S2 counts, so the dashboard surfaces those cases for review rather
  than relabelling the source flag.
- Compare annual NDVI summaries for 2023–2025 and view a paired-pixel
  2025-minus-2023 difference map.
- Enable **Relative management-grid screening** to summarize selected
  time-window satellite values in stable 50 m or 100 m EPSG:32647 zones. Hover
  over a zone for its mean, range, valid source-pixel count, and standardized
  difference from the selected window's AOI mean. The map is clipped to the
  study boundary; pixel centres are assigned once, zones with fewer than five
  values are left unclassified, and the labels describe relative metric
  differences only. These derived cells are not cadastral plots, field-health
  diagnoses, yield predictions, or management prescriptions.
- Satellite and soil layers can be displayed over the 3D scene with an opacity
  control. The satellite geometry/data is separate from the decorative crop
  meshes. Hover over or click an overlay cell to inspect its nearest source
  cell centre, value, date or depth, source/fill information, quality flags,
  and evidence class. The inspector reverses the same local projected map
  transform used to draw the texture; it reports the nearest supplied source
  coordinate, not a field-surveyed location or a value interpolated at the
  pointer. Empty raster areas remain unreported rather than being treated as
  zero.
- The **External UAV multispectral index lab** accepts five aligned single-band
  TIFFs from one external plot and calculates NDVI, NDRE, and GNDVI. It checks
  dimensions/CRS/transforms, keeps nodata transparent, and returns in-memory
  previews plus full-resolution summaries. The RiceUAS sample is from Arkansas;
  reflectance calibration is unverified, and these values are never projected
  onto the Sekinchan AOI.

### Other dashboard panels

- **Weather and crop calendar:** regional weather context associated with the
  selected period and recurring reference crop stages.
- **Soil:** SoilGrids-derived reference properties and depth layers.
- **Yield:** synthetic historical examples and trend scenarios; the displayed
  satellite/weather/calendar context does not make these a validated yield
  model.
- **Water:** simulated campaign timelines with water-depth and event markers.
- **Paddy Doctor:** external image-classification demo and class-profile
  metadata.
- **U-Net segmentation:** upload an RGB image and display a returned binary
  mask, with the percentage of mask pixels marked positive.
- **Field Intelligence Agent:** ask for selected/latest satellite summaries,
  regional weather/calendar context, or coarse soil references. It is a
  deterministic read-only tool router, not an LLM; each answer cites tool,
  source, and evidence class. It refuses local yield claims, disease diagnosis,
  and field-action or chemical advice. Synthetic yield/water records are only
  returned when explicitly requested as demos.

The dashboard calls the API at `http://localhost:8000` by default. Serve it
through VS Code Live Server at `http://127.0.0.1:5500` or
`http://localhost:5500`; opening the HTML directly as a `file://` URL is not the
documented setup. The 3D scene imports Three.js and OrbitControls from jsDelivr,
so that part of the UI requires network access to the CDN.

## Data sources and evidence limits

The full provenance register and known quality issues are documented in
[`DATA_CONTRACT.md`](DATA_CONTRACT.md). The table below summarizes how sources
are used by the application.

| Data | Source / period | Use and limitations |
|---|---|---|
| Study boundary | User-supplied GeoJSON; reported area 66.878 ha | Defines the AOI for spatial displays. It is not an administrative boundary for all of Sekinchan. |
| Satellite | PaddyVision v3 merged Sentinel-1/2 package, 2023–2025; 10 m grid | Local remote-sensing observations for the AOI, not field-measured crop condition. Respect nodata, quality flags, direct-observation/fill source, and polygon clipping. |
| Weather | Open-Meteo historical archive, 2021–2025 | Regional grid context, not a field sensor or proof of crop condition, disease, irrigation, or yield. |
| Crop calendar | Recurring Sekinchan reference calendar | Context only; dates are not verified planting, transplanting, or harvest dates for a specific field/year. |
| Soil | SoilGrids-derived gridded estimates | Coarse cells (about 252 × 264 m), with only about ten pixel centres over the AOI. Not local lab results or field-level fertilizer advice. |
| Yield examples | Generated rows in `data/demo/sekinchan_yield_synthetic.csv` | Synthetic 2023–2025 examples and 2026–2027 trend scenarios, not harvest observations or a locally validated model. |
| Water campaigns | `SIM-F01`–`SIM-F12` synthetic campaign records | Demonstration data, separate from the Sekinchan AOI; not measured irrigation records. |
| Paddy Doctor images | External labelled image dataset | Image-model demonstration only. Dataset class labels are not Sekinchan disease observations. Check licensing and evaluation-label availability before redistribution or research claims. |
| U-Net images | WeedyRice UAV RGB/mask data from An Giang, Vietnam | External image-to-mask demo. Mask semantics must be interpreted according to the dataset labels; output is not a Sekinchan field map. |
| Google Earth images | Bundled reference imagery in `frontend/assets/study-area/` | Visual study-area context, not field-verified measurements. |

### Satellite package details

The external data package is not fully committed to this repository. The
satellite service expects files such as:

```text
01_Satellite_Imagery_Spatial_Data/
  paddyvision_v3_pixels_panel_2023_2025.csv
  paddyvision_v3_window_summary_2023_2025.csv
04_Soil_and_Ground_Truth/
  02_Boundary/sekinchan_study_area_polygon.geojson
```

The data contract records a 10 m EPSG:32647 raster stack (157 × 124 pixels,
558 bands), 6,681 unique coordinate pairs and 706,394 panel rows. The window
summary has 111 expected windows; the pixel panel has 109, with no S1/S2 data
for `2023-021` and `2025-321`. The package audit also identified panel edge
coordinates outside the AOI. The application should preserve those source
distinctions and clip map/statistical outputs to the supplied polygon.

## Backend and API

The backend is a FastAPI application in `api/main.py`, with data-processing
services in `api/services/`. The documented API includes:

- Health status and PostgreSQL-backed field lookup.
- Satellite catalogue, per-window layers, year comparison, and difference map.
- AOI-clipped satellite summaries for derived relative grid zones.
- External UAV NDVI/NDRE/GNDVI calculation from aligned single-band TIFFs.
- Weather/calendar context for a satellite window.
- Soil reference properties and spatial layers.
- Synthetic yield outlook and synthetic water campaign browser.
- External Paddy Doctor dataset profile and image classification.
- U-Net RGB-to-mask segmentation.

See [API reference](#api-reference) for routes and parameters. The UI/API
contract is configured in `frontend/index.html`; CORS is enabled for the
localhost Live Server origins `http://localhost:5500` and
`http://127.0.0.1:5500`.

## Models and notebooks

### Active image-model demos

- **U-Net:** [`api/unet_model.py`](api/unet_model.py) defines the model;
  [`api/services/segmentation.py`](api/services/segmentation.py) preprocesses
  an RGB input and returns a 320 × 240 binary mask. The checkpoint is
  `models/best_unet.pth`. The training workflow is in
  [`notebooks/02_cv_segmentation.ipynb`](notebooks/02_cv_segmentation.ipynb).
- **Paddy Doctor:** inference and model definitions are in
  `api/services/paddy_doctor_inference.py` and
  `api/services/paddy_doctor_model.py`; the checkpoint and validation summary
  are `models/paddy_doctor_classifier.pth` and
  `models/paddy_doctor_validation.json`. The reported validation accuracy is
  0.667 and macro-F1 is 0.660 on an image-level 80/20 split. The report warns
  that near-duplicate images may cross the split and that this does not
  establish generalization to Sekinchan.

### Research notebooks and legacy models

| Notebook | Scope |
|---|---|
| `notebooks/01_dataset_inspection.ipynb` | Dataset inspection and exploratory analysis. |
| `notebooks/02_cv_segmentation.ipynb` | WeedyRice RGB/mask segmentation with U-Net. |
| `notebooks/03-deep-learning.ipynb` | Historical RiceUAS yield CNN experiment. |
| `notebooks/04_agricultural_ml_and_data_analytics.ipynb` | External agriculture/weather/yield analysis. |
| `notebooks/paddy_doctor_colab_training_run.ipynb` | Paddy Doctor classifier training workflow. |

The RiceUAS yield CNN and external weather/yield Random Forest are historical
research artifacts, not active Sekinchan prediction endpoints. The data
contract reports the RiceUAS test R² near −0.004 and identifies its data as
external to the AOI. Do not use these artifacts as local yield estimates.

## Databases and file storage

This project uses distinct stores for distinct purposes:

1. **PostgreSQL** is the configured relational database for field records and
   image/segmentation history. SQLAlchemy models are defined in
   [`api/db_models.py`](api/db_models.py): `fields`, `drone_images`,
   `segmentation_results`, and `yield_predictions`. The current dashboard uses
   the field lookup and the segmentation endpoint may persist input/history.
   Create/provision the database and schema separately; this repository does
   not include a migration or schema-creation workflow.
2. **SQLite** is used as a runtime-built satellite panel index/cache. It is not
   the PostgreSQL field-record database and can be rebuilt from the source
   panel.
3. **Local files** hold input datasets, model checkpoints, image assets, and
   generated prediction artifacts. Runtime artifacts default to
   `%LOCALAPPDATA%\PaddyVisionAI` on Windows.

No cloud database is configured by default. The project has no checked-in
dependency lockfile or `requirements.txt` at the time of writing.

## Project layout

```text
PaddyVision-AI/
├── api/                 FastAPI application, ORM models, and services
├── data/
│   ├── demo/            Synthetic demo data
│   ├── external/        Optional external datasets
│   ├── processed/       Processed project data
│   └── raw/             Local raw data area
├── frontend/            Dashboard HTML, 3D JavaScript, and image assets
├── models/               Model checkpoints and validation report
├── notebooks/            Dataset, training, and research notebooks
├── scripts/              Standalone training utilities
├── DATA_CONTRACT.md      Data provenance, quality, and interpretation rules
└── README.md             Project guide
```

Large source data files may be stored outside this repository. Point
`PADDYVISION_DATASET_ROOT` at the root directory that contains the numbered
source folders described in [Configuration](#configuration).

## Setup and run

### Prerequisites

- Windows or another Python-capable environment.
- A Python environment compatible with the packages in `requirements.txt`.
  That file contains the minimal API runtime dependency set; notebook training
  and exploration may require additional packages.
- The required model checkpoints under `models/`.
- The local source dataset package for satellite/context endpoints.
- PostgreSQL for DB-backed field and inference-history functionality; run the
  explicit schema setup described below before using those features.
- VS Code Live Server for the dashboard; internet access for the Three.js CDN.

The checked-in manifest is intentionally limited to API imports and is not a
lockfile: package versions are not pinned. The repository's current `.venv` is
Python 3.14.7 and does not contain the core API packages, so its installed
packages do not verify API compatibility. Install into a project-specific
environment and confirm that PyTorch and Rasterio wheels are available for
your Python version. For CUDA inference, use the matching PyTorch command from
the official PyTorch installer; the manifest's `torch` entry alone does not
select a CUDA build.

From PowerShell at the repository root:

```powershell
py -m venv .venv-api
.\.venv-api\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Configure environment variables

Edit `.env` with your local paths and PostgreSQL URL. Environment variables
already set in the process take precedence over `.env`:

```dotenv
PADDYVISION_DATASET_ROOT=C:\Paddyvision_AI_Dataset
PADDYVISION_DATABASE_URL=postgresql+psycopg2://paddyvision_user:CHANGE_ME@localhost:5432/paddyvision_db
PADDYVISION_RUNTIME_DIR=C:\PaddyVisionRuntime
```

Replace the sample database username/password and paths with your own. Never
commit `.env` or real credentials. `.env` is loaded by the API without
overriding environment variables already supplied by the shell.

The satellite service also checks `C:\Paddyvision_AI_Dataset` and
`data/external/sekinchan-67ha` as fallback roots. The dataset root must contain
the expected numbered folders; see the
[satellite package details](#satellite-package-details).

### Set up the database

Create the PostgreSQL database itself first, then run the explicit, versioned
schema setup from the repository root:

```powershell
python -m api.setup_db
```

This applies pending entries in `api/setup_db.py`, creates missing ORM tables,
and records applied versions in `schema_migrations`. It does not drop tables
or alter existing columns. If an existing database is missing model columns,
the command stops with an explanation; add a new migration before changing
that schema. Do not delete an existing database to resolve a schema mismatch.

### Start the API

From the repository root:

```powershell
python -m uvicorn api.main:app --reload
```

The API listens on `http://127.0.0.1:8000` by default. Check
`http://127.0.0.1:8000/health` or open the interactive API docs at
`http://127.0.0.1:8000/docs`.

### Start the dashboard

1. In VS Code, open the project folder and serve
   `frontend/index.html` with Live Server.
2. Use the Live Server address on port 5500, for example
   `http://127.0.0.1:5500/frontend/index.html`.
3. Keep the API running at `http://localhost:8000`.

If the API uses another origin, define
`window.PADDYVISION_API_BASE_URL` before the page's inline application script
runs, then reload. Configure the API's CORS allowed origins to match the
dashboard origin as well.

### Database-dependent behavior

Satellite, context, soil-reference, and synthetic demo endpoints do not rely on
the PostgreSQL field-record tables. `/digital-twin/fields` requires a working
PostgreSQL connection and schema. Segmentation inference can return the mask if
history persistence fails, but saving the image/history requires PostgreSQL;
the API response includes `X-PaddyVision-Persistence` to indicate persistence
status. Recent saved U-Net run metadata is available at `/history/segmentation`
and shown below the mask workspace. This history represents external WeedyRice
image-model runs, not Sekinchan inspections or disease observations; stored
file paths are never returned by the history endpoint.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PADDYVISION_DATASET_ROOT` | `C:\Paddyvision_AI_Dataset` fallback | Root of the local Sekinchan source data package. |
| `PADDYVISION_DATABASE_URL` | `postgresql://postgres@localhost:5432/paddyvision_db` | SQLAlchemy PostgreSQL connection URL; set in `.env` or the process environment. |
| `PADDYVISION_RUNTIME_DIR` | `%LOCALAPPDATA%\PaddyVisionAI` on Windows | Runtime artifacts, generated images, and satellite SQLite index. |
| `.env` file | None | Project-local configuration loaded with process environment variables taking precedence; `.env.example` is safe to copy and customize. |
| `window.PADDYVISION_API_BASE_URL` | `http://localhost:8000` | Browser-side API origin override. Set before app script execution. |

## API reference

### Health and field records

| Method | Endpoint | Notes |
|---|---|---|
| `GET` | `/health` | API status. |
| `GET` | `/digital-twin/fields` | PostgreSQL-backed field list. |
| `GET` | `/history/segmentation` | Optional `limit` (1–100, default 20); external U-Net run metadata only, without filesystem paths. |
| `POST` | `/digital-twin/agent/ask` | JSON `question` (3–500 characters); bounded read-only internal summaries with source/evidence citations and uncertainty. |

### Satellite, weather, and soil

| Method | Endpoint | Parameters / purpose |
|---|---|---|
| `GET` | `/digital-twin/satellite/windows` | Catalogue and study boundary. |
| `GET` | `/digital-twin/satellite/window/{window_id}` | `metric` (default `NDVI`), `s2_source` (default `all`). |
| `GET` | `/digital-twin/satellite/management-grid/{window_id}` | `metric`, `s2_source`, `grid_size_m` (`50` or `100`); center-assigned AOI satellite summaries and relative screening classes. |
| `GET` | `/digital-twin/satellite/static-layer` | Required: `layer` (`elevation_m`, `gsw_occurrence`, or `gsw_seasonality`); AOI-clipped static layer. |
| `GET` | `/digital-twin/satellite/year-comparison` | Yearly comparison data. |
| `GET` | `/digital-twin/satellite/year-difference-map` | Required: `month`, `dekad`. |
| `POST` | `/digital-twin/external-uav/indices` | Multipart `files`: exactly one each of `blue.tiff`, `green.tiff`, `red.tiff`, `red_edge.tiff`, and `nir.tiff` from one plot. Returns index summaries/previews as `MODELLED_EXTERNAL`; never places them on Sekinchan. |
| `GET` | `/digital-twin/mission/illustrative` | Optional `altitude_m`, `camera_fov_deg`, `side_overlap_percent`, `cruise_speed_mps`; returns a `SYNTHETIC` AOI-clipped scenario, not a flight plan. |
| `GET` | `/digital-twin/context/window/{window_id}` | Regional weather and crop-calendar context. |
| `GET` | `/digital-twin/soil/reference` | Soil reference summary. |
| `GET` | `/digital-twin/soil/spatial-layer` | `property` (default `phh2o`), `depth_cm` (default `0-5`). |

### Synthetic examples and image models

| Method | Endpoint | Parameters / request |
|---|---|---|
| `GET` | `/digital-twin/yield/synthetic` | Synthetic yield examples and outlook. |
| `GET` | `/digital-twin/water/synthetic/options` | Available simulated campaigns. |
| `GET` | `/digital-twin/water/synthetic/campaign` | Required: `field_id`, `year`, `season`. |
| `GET` | `/digital-twin/disease/external-dataset` | External image-dataset profile. |
| `POST` | `/predict/paddy-doctor` | Multipart image field named `file`; image uploads are limited to 12 MiB. |
| `POST` | `/predict/segmentation` | Multipart image field named `image`; image uploads are limited to 12 MiB and return a PNG mask. |

Both image endpoints reject non-image content types and oversized uploads
before inference. Empty or unreadable image files receive a client error;
unexpected inference failures are logged by the API and returned without
exposing internal exception details.

The older RiceUAS yield and weather/year Random Forest models do not have
active API endpoints.

## Known limitations

- No completed local soil-lab measurements, plot-linked harvest records, field
  water measurements, or Sekinchan-labelled disease images were supplied.
- The 3D plant geometry and crop appearance are visual illustrations; they are
  not a crop-growth simulation calibrated to field measurements.
- The satellite product is a remote-sensing estimate. Direct observations,
  monthly fills, quality flags, nodata, and AOI clipping must remain distinct.
- Regional weather, recurring calendar dates, and SoilGrids estimates are
  contextual sources, not field sensors or observations.
- Yield and water examples are synthetic. External image-model outputs are not
  validated for Sekinchan.
- The Paddy Doctor validation report records a 0.667 accuracy and 0.660
  macro-F1 image-level split, with potential near-duplicate leakage and no
  evidence of local generalization.
- The RiceUAS yield CNN is an external research artifact; its notebook reports
  test R² near −0.004. It is not an active or reliable local yield model.
- PostgreSQL schema provisioning is not automated. Large source datasets are
  not included by default. Dependency versions are not pinned.

## Data and responsible-use policy

Follow [`DATA_CONTRACT.md`](DATA_CONTRACT.md) when adding data or changing
product wording. In particular:

- Preserve each value's source, date/period, spatial support, processing
  status, quality flags, and evidence class.
- Keep `LOCAL_OBSERVED`, `LOCAL_REMOTE_SENSING`, `MODELLED_EXTERNAL`,
  `REFERENCE`, `SYNTHETIC`, and `TEMPLATE` evidence clearly separated.
- Do not describe external model outputs, synthetic examples, reference
  calendars, regional weather, or coarse soil grids as local ground truth.
- Do not map external disease predictions as confirmed outbreaks or present
  outputs as agronomic advice.

## License and attribution

No project-wide license file or dependency lockfile was found during this
repository review. Confirm the licensing and redistribution terms of all
bundled imagery, external datasets, model checkpoints, and third-party
libraries before redistribution or deployment. Cite the original providers
when distributing derived work.

## Illustrative UAV mission scenario

The 3D field overlay includes an optional synthetic lawnmower-route scenario for
the supplied Sekinchan AOI. It accepts assumed altitude, camera field of view,
side overlap, and cruise speed, then draws AOI-clipped footprint shapes and a
schematic route. A route marker can be played or paused. The service is exposed
at `GET /digital-twin/mission/illustrative`.

This is a visualization aid only. It assumes a flat surface, constant altitude,
a nadir camera, and straight connectors; the displayed 3D scale is schematic.
The time estimate is route length divided by assumed cruise speed and excludes
turns, climb/descent, wind, battery reserve, obstacles, airspace, permissions,
and operational checks. It is not a flyable plan or a coverage guarantee. See
the `Illustrative UAV mission scenario (Phase 5)` data-contract entry for scope.
