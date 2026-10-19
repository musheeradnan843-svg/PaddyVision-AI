from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    Float
)

from sqlalchemy.sql import func

from api.database import Base


class YieldPrediction(Base):

    __tablename__ = "yield_predictions"

    prediction_id = Column(
        Integer,
        primary_key=True
    )

    field_id = Column(
        Integer
    )

    prediction_type = Column(
        String(50),
        nullable=False
    )

    input_reference = Column(
        String
    )

    predicted_yield = Column(
        Numeric(10, 4)
    )

    model_name = Column(
        String(100)
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

class SegmentationResult(Base):

    __tablename__ = "segmentation_results"

    segmentation_id = Column(
        Integer,
        primary_key=True
    )

    field_id = Column(
        Integer
    )

    image_id = Column(
        Integer,
        nullable=True
    )

    input_image_path = Column(
        String
    )

    output_mask_path = Column(
        String
    )

    model_name = Column(
        String(100)
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

class DroneImage(Base):

    __tablename__ = "drone_images"

    image_id = Column(
        Integer,
        primary_key=True
    )

    field_id = Column(
        Integer
    )

    image_type = Column(
        String(50)
    )

    file_path = Column(
        String,
        nullable=False
    )

    captured_at = Column(
        DateTime,
        nullable=True
    )

class Field(Base):
    __tablename__ = "fields"

    field_id = Column(Integer, primary_key=True)
    farmer_id = Column(Integer)
    field_name = Column(String(100), nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    area = Column(Float)
    crop = Column(String(50))
    season = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())