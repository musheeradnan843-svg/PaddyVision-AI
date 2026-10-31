"""Deterministic per-pixel vegetation indices for external UAV multispectral imagery."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any


REQUIRED_BANDS = ("blue", "green", "red", "red_edge", "nir")
MAX_BAND_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_PIXELS = 4_194_304


class UavIndexError(ValueError):
    """Raised when uploaded bands cannot safely form an aligned index set."""


def calculate_uav_indices(uploaded_files: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Calculate NDVI, NDRE, and GNDVI from five aligned single-band TIFFs.

    Inputs are read in memory and are never persisted. Outputs are downsampled
    PNG previews plus full-resolution statistics. Spatial metadata is checked
    for alignment but deliberately is not used to place the external data on
    the Sekinchan map.
    """
    try:
        import numpy as np
        import rasterio
        from PIL import Image
        from rasterio.io import MemoryFile
    except ImportError as exc:
        raise UavIndexError("UAV index processing requires NumPy, Rasterio, and Pillow in the API environment.") from exc

    if len(uploaded_files) != len(REQUIRED_BANDS):
        raise UavIndexError("Select exactly five TIFF files: blue, green, red, red_edge, and nir.")

    files_by_band: dict[str, bytes] = {}
    total_bytes = 0
    for filename, content in uploaded_files:
        band_name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower().rsplit(".", 1)[0]
        if band_name not in REQUIRED_BANDS:
            raise UavIndexError(f"Unexpected band filename '{filename}'. Use the five named TIFF files from one plot.")
        if band_name in files_by_band:
            raise UavIndexError(f"The '{band_name}' band was selected more than once.")
        if not content:
            raise UavIndexError(f"The '{band_name}' TIFF is empty.")
        if len(content) > MAX_BAND_BYTES:
            raise UavIndexError(f"The '{band_name}' TIFF exceeds the 32 MB per-band limit.")
        total_bytes += len(content)
        files_by_band[band_name] = content
    missing = [band for band in REQUIRED_BANDS if band not in files_by_band]
    if missing:
        raise UavIndexError("Missing band file(s): " + ", ".join(missing) + ".")
    if total_bytes > MAX_TOTAL_BYTES:
        raise UavIndexError("The five TIFF files exceed the 100 MB combined upload limit.")

    memories = []
    datasets = []
    try:
        for band_name in REQUIRED_BANDS:
            memory_file = MemoryFile(files_by_band[band_name])
            memories.append(memory_file)
            dataset = memory_file.open()
            datasets.append(dataset)
            if dataset.count != 1:
                raise UavIndexError(f"The {band_name} file must contain exactly one band.")

        reference = datasets[0]
        if reference.width * reference.height > MAX_PIXELS:
            raise UavIndexError("Each plot image must contain no more than 4,194,304 pixels (for example, 2048 × 2048).")
        for band_name, dataset in zip(REQUIRED_BANDS[1:], datasets[1:]):
            if (dataset.width, dataset.height) != (reference.width, reference.height):
                raise UavIndexError(f"Band '{band_name}' dimensions do not match the blue band.")
            if dataset.crs != reference.crs or not dataset.transform.almost_equals(reference.transform, precision=1e-9):
                raise UavIndexError(f"Band '{band_name}' spatial transform does not match the blue band; resample/align before use.")

        arrays = []
        common_valid = np.ones((reference.height, reference.width), dtype=bool)
        for dataset in datasets:
            masked = dataset.read(1, masked=True)
            values = np.asarray(masked.data, dtype=np.float32)
            valid = ~np.ma.getmaskarray(masked) & np.isfinite(values)
            common_valid &= valid
            arrays.append(values)
        blue, green, red, red_edge, nir = arrays

        definitions = (
            ("NDVI", "Normalized Difference Vegetation Index", nir, red),
            ("NDRE", "Normalized Difference Red Edge", nir, red_edge),
            ("GNDVI", "Green Normalized Difference Vegetation Index", nir, green),
        )
        color_stops = np.asarray([[112, 70, 55], [218, 183, 102], [225, 222, 170], [113, 186, 106], [29, 112, 63]], dtype=np.float32)
        results = {}
        for metric, label, numerator_band, denominator_band in definitions:
            denominator = numerator_band + denominator_band
            valid = common_valid & np.isfinite(denominator) & (denominator > 0)
            index = np.full(denominator.shape, np.nan, dtype=np.float32)
            np.divide(numerator_band - denominator_band, denominator, out=index, where=valid)
            finite = np.isfinite(index)
            values = index[finite]
            if values.size:
                scaled = np.clip((np.nan_to_num(index, nan=-1.0) + 1.0) * 0.5, 0, 1) * (len(color_stops) - 1)
                lower = np.minimum(np.floor(scaled).astype(np.int8), len(color_stops) - 2)
                blend = (scaled - lower)[..., None]
                rgb = color_stops[lower] * (1 - blend) + color_stops[lower + 1] * blend
                rgba = np.zeros((reference.height, reference.width, 4), dtype=np.uint8)
                rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
                rgba[..., 3] = finite.astype(np.uint8) * 255
                preview = Image.fromarray(rgba, mode="RGBA")
                preview.thumbnail((512, 512), Image.Resampling.BILINEAR)
                encoded = BytesIO()
                preview.save(encoded, format="PNG", optimize=True)
                results[metric] = {
                    "label": label,
                    "unit": "unitless index",
                    "valid_pixel_count": int(values.size),
                    "min": float(values.min()),
                    "mean": float(values.mean(dtype=np.float64)),
                    "max": float(values.max()),
                    "preview_png_base64": base64.b64encode(encoded.getvalue()).decode("ascii"),
                }
            else:
                results[metric] = {
                    "label": label,
                    "unit": "unitless index",
                    "valid_pixel_count": 0,
                    "min": None,
                    "mean": None,
                    "max": None,
                    "preview_png_base64": None,
                }

        return {
            "evidence_class": "MODELLED_EXTERNAL",
            "source_label": "External UAV multispectral imagery · user-selected files",
            "input_bands": list(REQUIRED_BANDS),
            "input_filenames": [filename for filename, _ in uploaded_files],
            "dimensions": {"width": reference.width, "height": reference.height},
            "crs_present": reference.crs is not None,
            "spatial_alignment": "All five bands share dimensions, CRS, and affine transform.",
            "plot_identity_limit": "Alignment is checked, but the service cannot prove the five selected files came from the same date and plot; select all bands from one plot folder.",
            "spatial_use": "No geospatial placement on the Sekinchan AOI; the source imagery remains an external plot/image workspace.",
            "reflectance_note": "Indices are calculated directly from stored band values. Reflectance calibration/scale metadata is not verified, so interpret the maps as exploratory indices, not calibrated agronomic thresholds.",
            "nodata_policy": "A pixel is valid only where all five input bands are valid; index denominators must be positive. Invalid pixels remain transparent.",
            "index_method": "NDVI=(NIR−Red)/(NIR+Red); NDRE=(NIR−RedEdge)/(NIR+RedEdge); GNDVI=(NIR−Green)/(NIR+Green).",
            "results": results,
        }
    except rasterio.errors.RasterioError as exc:
        raise UavIndexError(f"Could not read one of the selected TIFF files: {exc}") from exc
    finally:
        for dataset in datasets:
            dataset.close()
        for memory_file in memories:
            memory_file.close()
