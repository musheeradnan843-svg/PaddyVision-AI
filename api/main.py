import logging
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from api.services.segmentation import predict_segmentation
from api.db_models import SegmentationResult, DroneImage, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Depends
from pydantic import BaseModel, Field as SchemaField
from api.database import get_db
from api.runtime_paths import get_runtime_data_dir
from api.services.satellite_data import (
    SatelliteDataError,
    get_satellite_catalogue,
    get_satellite_management_grid,
    get_satellite_static_layer,
    get_satellite_window,
    get_satellite_year_difference_map,
    get_satellite_year_comparison,
)
from api.services.context_data import get_environment_context
from api.services.soil_reference import get_soil_reference, get_soil_spatial_layer
from api.services.synthetic_water import get_synthetic_water_campaign, get_synthetic_water_options
from api.services.synthetic_yield import get_synthetic_yield_outlook
from api.services.disease_data import get_external_disease_dataset_profile
from api.services.paddy_doctor_inference import predict_paddy_doctor
from api.services.uav_indices import MAX_BAND_BYTES, MAX_TOTAL_BYTES, calculate_uav_indices
from api.services.mission_simulator import MissionPlanError, build_illustrative_mission
from api.services.field_agent import ask_field_agent

app = FastAPI(
    title="PaddyVision AI · Sekinchan Digital Twin API",
    description="Sekinchan satellite, weather, crop-calendar, soil-reference, synthetic-demo, external image-model, and bounded read-only Field Intelligence Agent services. No locally validated Sekinchan yield or disease model is exposed.",
    version="2.0.0"
)
logger = logging.getLogger(__name__)
MAX_IMAGE_UPLOAD_BYTES = 12 * 1024 * 1024


class FieldAgentRequest(BaseModel):
    question: str = SchemaField(min_length=3, max_length=500)


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-PaddyVision-Persistence"],
)

DRONE_IMAGE_DIR = get_runtime_data_dir() / "drone_images"

DRONE_IMAGE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "message": "PaddyVision AI API is running"
    }


@app.post("/digital-twin/agent/ask")
def ask_field_agent_endpoint(request: FieldAgentRequest):
    """Ask the bounded read-only agent to summarize approved internal records."""
    try:
        return ask_field_agent(request.question)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SatelliteDataError, OSError, FileNotFoundError) as exc:
        logger.exception("A read-only Field Intelligence Agent tool was unavailable.")
        raise HTTPException(status_code=503, detail="A required internal data source is unavailable.") from exc


@app.post("/predict/segmentation")
async def predict_segmentation_endpoint(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        if image.content_type and not image.content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="Upload an image file.")

        # Read only one byte beyond the cap so a large request is rejected
        # without buffering its entire body in memory.
        image_bytes = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
        if not image_bytes:
            raise HTTPException(status_code=422, detail="The uploaded image is empty.")
        if len(image_bytes) > MAX_IMAGE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image must be no larger than 12 MB.")

        output_path = predict_segmentation(
            image_bytes
        )

        with open(output_path, "rb") as file:
            image_data = file.read()

        persistence_failed = False
        image_path = DRONE_IMAGE_DIR / f"image_{uuid4().hex}"
        try:
            image_path.write_bytes(image_bytes)
            drone_record = DroneImage(
                field_id=1,
                image_type="RGB",
                file_path=str(image_path)
            )
            db.add(drone_record)
            db.flush()

            record = SegmentationResult(
                field_id=1,
                image_id=drone_record.image_id,
                input_image_path=str(image_path),
                output_mask_path=str(output_path),
                model_name="U-Net"
            )
            db.add(record)
            db.commit()
        except (OSError, SQLAlchemyError):
            persistence_failed = True
            logger.exception("Segmentation succeeded but its history could not be saved.")
            try:
                db.rollback()
            except SQLAlchemyError:
                logger.exception("Could not roll back the failed segmentation history save.")
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove the untracked segmentation input image.")

        return StreamingResponse(
            BytesIO(image_data),
            media_type="image/png",
            headers={
                "X-PaddyVision-Persistence": (
                    "failed" if persistence_failed else "saved"
                )
            }
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as e:
        logger.exception("U-Net segmentation request failed.")
        raise HTTPException(
            status_code=500,
            detail="Segmentation could not be completed. Check the API logs for details.",
        ) from e
    
    
    
@app.get("/digital-twin/satellite/windows")
def get_satellite_windows():
    try:
        return get_satellite_catalogue()
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/satellite/static-layer")
def get_satellite_static_layer_endpoint(layer: str):
    try:
        return get_satellite_static_layer(layer)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/satellite/year-comparison")
def get_satellite_year_comparison_endpoint():
    try:
        return get_satellite_year_comparison()
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/satellite/year-difference-map")
def get_satellite_year_difference_map_endpoint(month: int, dekad: int):
    try:
        return get_satellite_year_difference_map(month, dekad)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/satellite/window/{window_id}")
def get_satellite_window_endpoint(
    window_id: str,
    metric: str = "NDVI",
    s2_source: str = "all",
):
    try:
        return get_satellite_window(window_id, metric, s2_source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/satellite/management-grid/{window_id}")
def get_satellite_management_grid_endpoint(
    window_id: str,
    metric: str = "NDVI",
    s2_source: str = "all",
    grid_size_m: int = 50,
):
    try:
        return get_satellite_management_grid(window_id, metric, s2_source, grid_size_m)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/digital-twin/external-uav/indices")
async def calculate_external_uav_indices_endpoint(files: list[UploadFile] = File(...)):
    if len(files) != 5:
        raise HTTPException(status_code=422, detail="Select exactly five TIFF band files.")
    uploaded = []
    total_bytes = 0
    for file in files:
        content = await file.read(MAX_BAND_BYTES + 1)
        if len(content) > MAX_BAND_BYTES:
            raise HTTPException(status_code=413, detail=f"{file.filename or 'Band file'} exceeds the 32 MB per-band limit.")
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="The five TIFF files exceed the 100 MB combined upload limit.")
        uploaded.append((file.filename or "", content))
    try:
        return calculate_uav_indices(uploaded)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/digital-twin/mission/illustrative")
def get_illustrative_mission_endpoint(
    altitude_m: float = 60,
    camera_fov_deg: float = 60,
    side_overlap_percent: float = 70,
    cruise_speed_mps: float = 5,
):
    """Return a synthetic route scenario; it is not an operational flight plan."""
    try:
        boundary = get_satellite_catalogue()["boundary"]
        return build_illustrative_mission(
            boundary,
            altitude_m=altitude_m,
            camera_fov_deg=camera_fov_deg,
            side_overlap_percent=side_overlap_percent,
            cruise_speed_mps=cruise_speed_mps,
        )
    except MissionPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/context/window/{window_id}")
def get_digital_twin_context(window_id: str):
    try:
        return get_environment_context(window_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SatelliteDataError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/soil/reference")
def get_digital_twin_soil_reference():
    try:
        return get_soil_reference()
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/soil/spatial-layer")
def get_digital_twin_soil_spatial_layer(property: str = "phh2o", depth_cm: str = "0-5"):
    try:
        return get_soil_spatial_layer(property, depth_cm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SatelliteDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/yield/synthetic")
def get_synthetic_yield_outlook_endpoint():
    try:
        return get_synthetic_yield_outlook()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Synthetic yield demo records are unavailable.") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Synthetic yield demo could not be loaded.") from exc


@app.get("/digital-twin/water/synthetic/options")
def get_synthetic_water_options_endpoint():
    try:
        return get_synthetic_water_options()
    except (SatelliteDataError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/water/synthetic/campaign")
def get_synthetic_water_campaign_endpoint(field_id: str, year: int, season: str):
    try:
        return get_synthetic_water_campaign(field_id, year, season)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SatelliteDataError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/predict/paddy-doctor")
async def predict_paddy_doctor_endpoint(file: UploadFile = File(...)):
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload an image file.")
    image_bytes = await file.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    if not image_bytes or len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be non-empty and no larger than 12 MB.")
    try:
        return predict_paddy_doctor(image_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/digital-twin/disease/external-dataset")
def get_external_disease_profile_endpoint():
    try:
        return get_external_disease_dataset_profile()
    except (SatelliteDataError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/digital-twin/fields")
def get_digital_twin_fields(db: Session = Depends(get_db)):
    fields = db.query(Field).all()

    return [
        {
            "field_id": field.field_id,
            "field_name": field.field_name,
            "latitude": field.latitude,
            "longitude": field.longitude,
            "area": field.area,
            "crop": field.crop,
            "season": field.season
        }
        for field in fields
    ]


@app.get("/history/segmentation")
def get_segmentation_history(limit: int = 20, db: Session = Depends(get_db)):
    """List recent external U-Net runs without exposing stored file paths."""
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    try:
        records = (
            db.query(SegmentationResult)
            .order_by(SegmentationResult.created_at.desc(), SegmentationResult.segmentation_id.desc())
            .limit(limit)
            .all()
        )
        return {
            "evidence_class": "MODELLED_EXTERNAL",
            "model_domain": "WeedyRice UAV imagery · An Giang, Vietnam",
            "scope_note": "Image-level external model runs; not Sekinchan field inspections or disease observations.",
            "items": [
                {
                    "segmentation_id": record.segmentation_id,
                    "model_name": record.model_name,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                }
                for record in records
            ],
        }
    except SQLAlchemyError as exc:
        logger.exception("Could not read segmentation history.")
        raise HTTPException(status_code=503, detail="Segmentation history is unavailable; check database setup and connection.") from exc
