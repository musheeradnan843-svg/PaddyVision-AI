from io import BytesIO
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from api.services.paddy_doctor_model import PaddyDoctorCNN


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models" / "paddy_doctor_classifier.pth"
_MODEL = None
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_CLASSES: list[str] = []
_IMAGE_SIZE = 160


def predict_paddy_doctor(image_bytes: bytes) -> dict:
    global _MODEL, _CLASSES, _IMAGE_SIZE
    if not MODEL_PATH.is_file():
        raise FileNotFoundError("Paddy Doctor classifier is not trained yet. Run scripts/train_paddy_doctor.py first.")
    try:
        if _MODEL is None:
            checkpoint = torch.load(MODEL_PATH, map_location=_DEVICE, weights_only=True)
            _CLASSES = checkpoint["class_names"]
            _IMAGE_SIZE = int(checkpoint["image_size"])
            _MODEL = PaddyDoctorCNN(len(_CLASSES)).to(_DEVICE)
            _MODEL.load_state_dict(checkpoint["state_dict"])
            _MODEL.eval()
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB").resize((_IMAGE_SIZE, _IMAGE_SIZE), Image.Resampling.BILINEAR)
            array = np.asarray(image, dtype=np.float32) / 255.0
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError(f"Could not read the uploaded image or classifier checkpoint: {exc}") from exc
    tensor = torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).to(_DEVICE)
    with torch.inference_mode():
        probabilities = torch.softmax(_MODEL(tensor), dim=1)[0].cpu()
    top = torch.topk(probabilities, k=min(3, len(_CLASSES)))
    return {
        "evidence_class": "MODELLED_EXTERNAL",
        "dataset_name": "Paddy Doctor",
        "predicted_class": _CLASSES[int(top.indices[0])],
        "top_predictions": [{"class": _CLASSES[int(index)], "probability": float(score)} for score, index in zip(top.values, top.indices)],
        "caveat": "External dataset classifier result only. It is not a confirmed diagnosis and is not linked to Sekinchan field observations or the 67 ha map.",
    }
