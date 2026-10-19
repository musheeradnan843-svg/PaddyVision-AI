import torch
import torch.nn.functional as F
import rasterio
import numpy as np
import tempfile
import os

from api.model_loader import yield_model, device


IMAGE_SIZE = (64, 64)

REQUIRED_BANDS = [
    "blue",
    "green",
    "red",
    "red_edge",
    "nir"
]


def save_temp_tiff(file_bytes: bytes):

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".tiff",
        delete=False
    )

    temp_file.write(file_bytes)
    temp_file.close()

    return temp_file.name


def read_band(file_path: str):

    with rasterio.open(file_path) as src:

        band = src.read(1).astype(
            np.float32
        )

        # Handle NoData
        if src.nodata is not None:

            band[
                band == src.nodata
            ] = np.nan

    # Same as training
    band = np.nan_to_num(
        band,
        nan=0.0
    )

    return band


def preprocess_bands(band_files):

    temp_paths = []

    try:

        bands = []

        # Save and read each band
        for band_name in REQUIRED_BANDS:

            file_bytes = band_files[band_name]

            temp_path = save_temp_tiff(
                file_bytes
            )

            temp_paths.append(temp_path)

            band = read_band(
                temp_path
            )

            bands.append(band)

        # 5 × H × W
        image = np.stack(
            bands,
            axis=0
        )

        # NumPy → Tensor
        image = torch.tensor(
            image,
            dtype=torch.float32
        )

        # Add batch dimension
        image = image.unsqueeze(0)

        # Resize → 64 × 64
        image = F.interpolate(
            image,
            size=IMAGE_SIZE,
            mode="bilinear",
            align_corners=False
        )

        # Remove batch dimension
        image = image.squeeze(0)

        # Band-wise standardization
        normalized = torch.zeros_like(
            image
        )

        for i in range(
            image.shape[0]
        ):

            band = image[i]

            mean = band.mean()
            std = band.std()

            if std > 0:

                normalized[i] = (
                    (band - mean) / std
                )

            else:

                normalized[i] = (
                    band - mean
                )

        return normalized

    finally:

        # Delete temporary files
        for path in temp_paths:

            if os.path.exists(path):

                os.remove(path)


def predict_rice_yield(band_files):

    # Preprocess 5 bands
    image = preprocess_bands(
        band_files
    )

    # Add batch dimension
    image = image.unsqueeze(0)

    image = image.to(device)

    # CNN prediction
    with torch.no_grad():

        prediction = yield_model(
            image
        )

    predicted_yield = (
        prediction.item()
    )

    return float(
        predicted_yield
    )