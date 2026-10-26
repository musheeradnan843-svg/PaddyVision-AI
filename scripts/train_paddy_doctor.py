import argparse
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from api.services.paddy_doctor_model import PaddyDoctorCNN


class RiceLeafDataset(Dataset):
    def __init__(self, samples, image_size, augment=False):
        self.samples = samples
        self.image_size = image_size
        self.augment = augment

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        path, label = self.samples[index]
        with Image.open(path) as image:
            image = image.convert("RGB")
            if self.augment and random.random() < 0.5:
                image = ImageOps.mirror(image)
            image = image.resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
            array = np.asarray(image, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1)
        return tensor, label


def metrics_for(model, loader, device, class_names):
    matrix = torch.zeros((len(class_names), len(class_names)), dtype=torch.int64)
    model.eval()
    with torch.inference_mode():
        for images, labels in loader:
            predictions = model(images.to(device)).argmax(1).cpu()
            for actual, predicted in zip(labels, predictions):
                matrix[int(actual), int(predicted)] += 1
    total = int(matrix.sum())
    accuracy = float(matrix.diag().sum()) / total if total else 0.0
    per_class = {}
    f1s = []
    for index, name in enumerate(class_names):
        tp = int(matrix[index, index])
        fp = int(matrix[:, index].sum()) - tp
        fn = int(matrix[index, :].sum()) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[name] = {"precision": precision, "recall": recall, "f1": f1, "support": int(matrix[index].sum())}
        f1s.append(f1)
    return {"accuracy": accuracy, "macro_f1": sum(f1s) / len(f1s), "per_class": per_class,
            "confusion_matrix": matrix.tolist(), "validation_image_count": total}


def main():
    parser = argparse.ArgumentParser(description="Train and validate the external Paddy Doctor image classifier.")
    parser.add_argument("--data-root", default=os.getenv("PADDYVISION_DATASET_ROOT", r"C:\Paddyvision_AI_Dataset"))
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=160)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, min(torch.get_num_threads(), 4)))
    dataset_dir = Path(args.data_root) / "05_Pest_and_Disease_Data" / "Paddy_Doctor" / "train_images"
    if not dataset_dir.is_dir():
        raise SystemExit(f"Training image folders not found: {dataset_dir}")
    classes = sorted(path.name for path in dataset_dir.iterdir() if path.is_dir())
    if len(classes) < 2:
        raise SystemExit("Expected class-named subfolders under train_images.")

    train_samples, val_samples, train_counts = [], [], {}
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    for label, class_name in enumerate(classes):
        files = sorted(path for path in (dataset_dir / class_name).iterdir() if path.suffix.lower() in extensions)
        if len(files) < 2:
            raise SystemExit(f"Class {class_name} needs at least two images for a train/validation split.")
        random.Random(args.seed + label).shuffle(files)
        val_count = max(1, round(len(files) * 0.2))
        val_samples.extend((path, label) for path in files[:val_count])
        train_samples.extend((path, label) for path in files[val_count:])
        train_counts[class_name] = len(files) - val_count

    train_loader = DataLoader(RiceLeafDataset(train_samples, args.image_size, True), batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(RiceLeafDataset(val_samples, args.image_size), batch_size=args.batch_size, shuffle=False, num_workers=0)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PaddyDoctorCNN(len(classes)).to(device)
    frequencies = Counter(label for _, label in train_samples)
    weights = torch.tensor([len(train_samples) / (len(classes) * frequencies[i]) for i in range(len(classes))], dtype=torch.float32, device=device)
    criterion = torch.nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=8e-4, weight_decay=1e-4)
    output_dir = PROJECT / "models"
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "paddy_doctor_classifier.pth"
    report_path = output_dir / "paddy_doctor_validation.json"
    best_f1 = -1.0
    patience, stale = 3, 0

    for epoch in range(args.epochs):
        model.train()
        loss_sum = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(images), labels)
            loss.backward(); optimizer.step()
            loss_sum += float(loss.detach()) * len(labels)
        report = metrics_for(model, val_loader, device, classes)
        report["epoch"] = epoch + 1
        report["train_loss"] = loss_sum / len(train_samples)
        print(f"epoch {epoch + 1}/{args.epochs} · loss {report['train_loss']:.4f} · val accuracy {report['accuracy']:.4f} · macro F1 {report['macro_f1']:.4f}", flush=True)
        if report["macro_f1"] > best_f1:
            best_f1, stale = report["macro_f1"], 0
            torch.save({"state_dict": model.state_dict(), "class_names": classes, "image_size": args.image_size,
                        "training_dataset": "Paddy Doctor external image dataset", "validation_split": "stratified 80/20 from labelled train_images; seed 42"}, checkpoint_path)
            report.update({"dataset": "Paddy Doctor external image dataset", "class_names": classes,
                           "train_image_count": len(train_samples), "split_seed": args.seed,
                           "split": "stratified 80/20 from labelled training folders",
                           "external_test_images_used": False,
                           "limitations": "Image-level holdout only; near-duplicate views may cross the split. Scores do not estimate generalization to new farms or Sekinchan field conditions."})
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        else:
            stale += 1
            if stale >= patience:
                print("Early stopping after validation macro F1 did not improve.", flush=True)
                break
    print(f"Best validation macro F1: {best_f1:.4f}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Validation report: {report_path}")


if __name__ == "__main__":
    main()
