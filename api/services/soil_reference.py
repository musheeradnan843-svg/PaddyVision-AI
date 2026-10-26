import csv
import os
from pathlib import Path
from typing import Any

from api.services.satellite_data import SatelliteDataError


def _root() -> Path:
    configured = os.getenv("PADDYVISION_DATASET_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path(r"C:\Paddyvision_AI_Dataset"))
    for candidate in candidates:
        summary = candidate / "04_Soil_and_Ground_Truth" / "03_Soil_Summary" / "soil_summary.csv"
        if summary.is_file():
            return candidate
    raise SatelliteDataError("Soil reference summary was not found. Set PADDYVISION_DATASET_ROOT.")


def get_soil_reference() -> dict[str, Any]:
    path = _root() / "04_Soil_and_Ground_Truth" / "03_Soil_Summary" / "soil_summary.csv"
    layers = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                layers.append({
                    "layer": row["layer"], "property": row["property"], "depth_cm": row["depth_cm"],
                    "unit": row["unit"], "area_weighted_mean": float(row["area_weighted_mean"]),
                    "resolution_m_approx": row["resolution_m_approx"], "pixel_count_center_rule": int(row["pixel_count_center_rule"]),
                    "pixels_touched": int(row["pixels_touched"]), "source": row["source"],
                    "confidence": row["confidence"], "note": row["note"],
                })
    except (OSError, KeyError, ValueError, csv.Error) as exc:
        raise SatelliteDataError(f"Could not read soil reference summary: {exc}") from exc
    return {
        "area_id": "sekinchan_67ha", "evidence_class": "REFERENCE", "layers": layers,
        "spatial_support": "66.878 ha AOI; about 10 pixel centres from approximately 251 x 264 m SoilGrids cells",
        "limitations": "Model-estimated soil context, not local lab samples. No within-field recommendations or fine-scale variability claims.",
        "low_confidence_properties": ["soil_organic_carbon", "nitrogen"],
    }


def get_soil_spatial_layer(property_name: str, depth_cm: str) -> dict[str, Any]:
    """Return valid coarse SoilGrids cells for a 3D reference overlay."""
    allowed_properties = {"clay", "sand", "silt", "phh2o", "nitrogen", "soil_organic_carbon", "cec"}
    if property_name not in allowed_properties or depth_cm not in {"0-5", "5-15"}:
        raise ValueError("Unsupported soil property or depth.")
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:
        raise SatelliteDataError("Rasterio and NumPy are required to load soil reference cells.") from exc

    raster_path = _root() / "04_Soil_and_Ground_Truth" / "01_Final_Soil_Rasters" / "ALL_14_layers_stack_masked.tif"
    band_name = f"{property_name}_{depth_cm.replace('-', '_')}cm"
    try:
        with rasterio.open(raster_path) as dataset:
            try:
                band = dataset.descriptions.index(band_name) + 1
            except ValueError as exc:
                raise SatelliteDataError(f"Soil raster band {band_name} is unavailable.") from exc
            raster = dataset.read(band, masked=True)
            points = []
            for row in range(dataset.height):
                for col in range(dataset.width):
                    value = raster[row, col]
                    if np.ma.is_masked(value) or not np.isfinite(float(value)):
                        continue
                    longitude, latitude = dataset.xy(row, col)
                    points.append({"longitude": longitude, "latitude": latitude, "value": float(value)})
            cell_size_m = {
                "width": float(abs(dataset.res[0]) * 111320 * np.cos(np.deg2rad(dataset.bounds.top))),
                "height": float(abs(dataset.res[1]) * 110574),
            }
    except (OSError, rasterio.errors.RasterioError) as exc:
        raise SatelliteDataError(f"Could not read the masked SoilGrids raster: {exc}") from exc

    summary = get_soil_reference()
    layer = next(item for item in summary["layers"] if item["property"] == property_name and item["depth_cm"] == depth_cm)
    values = [item["value"] for item in points]
    return {
        "area_id": "sekinchan_67ha", "layer_kind": "soil_reference",
        "property": property_name, "depth_cm": depth_cm, "unit": layer["unit"],
        "source": layer["source"], "confidence": layer["confidence"],
        "resolution_m_approx": layer["resolution_m_approx"], "cell_size_m": cell_size_m,
        "pixel_count": len(points), "min": min(values) if values else None,
        "max": max(values) if values else None, "points": points,
        "evidence_class": "REFERENCE",
        "limitations": "Coarse SoilGrids model estimates; not local lab measurements. Cells are clipped to the supplied AOI mask and do not support fine-scale recommendations.",
    }
