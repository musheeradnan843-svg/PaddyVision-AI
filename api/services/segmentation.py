import torch
import numpy as np

from PIL import Image
from io import BytesIO
from uuid import uuid4
from api.runtime_paths import get_runtime_data_dir

from api.model_loader import model, device


IMAGE_SIZE = (320, 240)
THRESHOLD = 0.5


OUTPUT_DIR = get_runtime_data_dir() / "segmentation"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def predict_segmentation(image_bytes: bytes):

    image = Image.open(
        BytesIO(image_bytes)
    ).convert("RGB")

    image = image.resize(
        IMAGE_SIZE,
        Image.Resampling.BILINEAR
    )

    image = np.array(image)

    image = torch.tensor(
        image,
        dtype=torch.float32
    )

    image = image.permute(2, 0, 1)

    image = image / 255.0

    image = image.unsqueeze(0)

    image = image.to(device)

    with torch.no_grad():

        output = model(image)

        probabilities = torch.sigmoid(output)

        prediction = (
            probabilities > THRESHOLD
        ).float()

    mask = (
        prediction
        .squeeze()
        .cpu()
        .numpy()
    )

    mask_image = (
        mask * 255
    ).astype(np.uint8)

    mask_image = Image.fromarray(
        mask_image
    )

    filename = (
        f"mask_{uuid4().hex}.png"
    )

    output_path = (
        OUTPUT_DIR / filename
    )

    mask_image.save(output_path)

    return output_path