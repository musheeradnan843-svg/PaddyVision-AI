import csv
import os
from collections import Counter
from pathlib import Path
from typing import Any

from api.services.satellite_data import SatelliteDataError


def _dataset_dir() -> Path:
    configured = os.getenv("PADDYVISION_DATASET_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path(r"C:\Paddyvision_AI_Dataset"))
    for root in candidates:
        folder = root / "05_Pest_and_Disease_Data" / "Paddy_Doctor"
        if (folder / "train.csv").is_file():
            return folder
    raise SatelliteDataError("Paddy Doctor external training metadata was not found. Set PADDYVISION_DATASET_ROOT.")


def get_external_disease_dataset_profile() -> dict[str, Any]:
    folder = _dataset_dir()
    counts: Counter[str] = Counter()
    try:
        with (folder / "train.csv").open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                label = (row.get("label") or "").strip()
                if label:
                    counts[label] += 1
    except (OSError, csv.Error) as exc:
        raise SatelliteDataError(f"Could not read Paddy Doctor class labels: {exc}") from exc
    test_dir = folder / "test_images"
    has_test_images = test_dir.is_dir() and any(path.suffix.lower() in {".jpg", ".jpeg", ".png"} for path in test_dir.iterdir())
    model_path = Path(__file__).resolve().parents[2] / "models" / "paddy_doctor_classifier.pth"
    classifier_ready = model_path.is_file()
    return {
        "evidence_class": "MODELLED_EXTERNAL",
        "dataset_name": "Paddy Doctor",
        "provenance_status": "external dataset; exact image collection location is not confirmed in the supplied files",
        "training_images_by_class": [{"label": label, "count": count} for label, count in sorted(counts.items())],
        "training_image_count": sum(counts.values()),
        "unlabelled_test_split_present": has_test_images,
        "classifier_ready": classifier_ready,
        "classifier_status": "External classifier is trained and ready for demo inference; no Sekinchan evaluation exists." if classifier_ready else "No Paddy Doctor classifier artifact is registered yet.",
        "limitations": "Training folder labels describe the external dataset only. They are not Sekinchan disease observations or outbreak evidence.",
    }
