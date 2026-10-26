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
from api.database import get_db
from api.runtime_paths import get_runtime_data_dir
from api.services.satellite_data import (
    SatelliteDataError,
    get_satellite_catalogue,
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

app = FastAPI(
    title="PaddyVision AI · Sekinchan Digital Twin API",
    description="Sekinchan satellite, weather, crop-calendar, soil-reference, synthetic-demo, and external image-model services. No locally validated Sekinchan yield or disease model is exposed.",
    version="2.0.0"
)
logger = logging.getLogger(__name__)
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


@app.post("/predict/segmentation")
async def predict_segmentation_endpoint(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        image_bytes = await image.read()
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

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    
    
    
@app.get("/digital-twin/satellite/windows")
def get_satellite_windows():
    try:
        return get_satellite_catalogue()
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
    image_bytes = await file.read()
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
