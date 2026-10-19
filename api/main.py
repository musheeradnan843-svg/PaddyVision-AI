from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from api.services.deep_learning import predict_rice_yield
from api.services.segmentation import predict_segmentation
from pydantic import BaseModel
from api.services.agricultural_ml import (
    predict_agricultural_yield
)
from api.db_models import YieldPrediction, SegmentationResult, DroneImage, Field
from sqlalchemy.orm import Session
from fastapi import Depends
from api.database import get_db
from api.runtime_paths import get_runtime_data_dir

app = FastAPI(
    title="PaddyVision AI API",
    description="AI-based Paddy Field Monitoring and Yield Prediction API",
    version="1.0.0"
)
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
        image_path = (
            DRONE_IMAGE_DIR / image.filename)
        
        with open(image_path, "wb") as file:
            file.write(image_bytes)

        output_path = predict_segmentation(
            image_bytes
        )
        drone_record = DroneImage(
            field_id=1,
            image_type="RGB",
            file_path=str(image_path)
        )

        db.add(drone_record)
        db.commit()
        db.refresh(drone_record)

        record = SegmentationResult(
            field_id=1,
            image_id=drone_record.image_id,
            input_image_path=str(image_path),
            output_mask_path=str(output_path),
            model_name="U-Net"
        )

        db.add(record)
        db.commit()
        db.refresh(record)

    
        with open(output_path, "rb") as file:
            image_data = file.read()

        return StreamingResponse(
            BytesIO(image_data),
            media_type="image/png"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    
    
    
@app.post("/predict/image-yield")
async def predict_image_yield(
    blue: UploadFile = File(...),
    green: UploadFile = File(...),
    red: UploadFile = File(...),
    red_edge: UploadFile = File(...),
    nir: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    try:

        band_files = {
            "blue": await blue.read(),
            "green": await green.read(),
            "red": await red.read(),
            "red_edge": await red_edge.read(),
            "nir": await nir.read()
        }

        predicted_yield = predict_rice_yield(
            band_files
        )
        record = YieldPrediction(
            field_id=1,
            prediction_type="IMAGE",
            input_reference="multispectral_drone_images",
            predicted_yield=predicted_yield,
            model_name="Rice Yield CNN"
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "message": "Rice yield prediction completed successfully",
            "predicted_yield": predicted_yield,
            "prediction_id": record.prediction_id,
            "database_status": "saved"
        }

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

class AgriculturalYieldInput(BaseModel):

    YEAR: int
    Station: str
    LATITUDE: float
    LONGITUDE: float
    ALT: float
    Avg_Max_Temp: float
    Avg_Min_Temp: float
    Avg_Rainfall: float
    Avg_Relative_Humidity: float
    Avg_Windspeed: float
    Avg_Cloud_Coverage: float
    Avg_Bright_Sunshine: float

@app.post("/predict/agricultural-yield")
def predict_agricultural_yield_endpoint(
    data: AgriculturalYieldInput,
    db: Session = Depends(get_db)
):
    try:
        # AI prediction
        prediction = predict_agricultural_yield(
            data.model_dump()
        )

        # Save prediction in PostgreSQL
        record = YieldPrediction(
            field_id=1,
            prediction_type="AGRICULTURAL",
            input_reference="weather_and_field_data",
            predicted_yield=prediction,
            model_name="Random Forest"
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "predicted_aman_yield": prediction,
            "prediction_id": record.prediction_id,
            "database_status": "saved"
        }

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

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