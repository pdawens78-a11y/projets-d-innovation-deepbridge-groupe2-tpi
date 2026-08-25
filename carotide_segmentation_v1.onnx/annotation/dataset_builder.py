# Non utilisé en production depuis le passage à TotalSegmentator — conservé pour référence et couvert par les tests unitaires.
"""
annotation/dataset_builder.py
==============================
Couche 3 — Construction du dataset nnU-Net à partir des volumes + masques + CSV.
Produit la structure de dossiers attendue par nnU-Net v2.
"""
import csv, json, logging, random, shutil, sys
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("dataset_builder")

# Structure nnU-Net v2 attendue :
# nnUNet_raw/Dataset001_Aorta/
#   ├── imagesTr/        # volumes entraînement
#   ├── labelsTr/        # masques entraînement
#   ├── imagesTs/        # volumes test
#   ├── labelsTs/        # masques test
#   └── dataset.json


NNUNET_CHANNEL_NAMES = {"0": "CT"}
NNUNET_LABELS        = {"background": 0, "aorte": 1, "stenose": 2}


def build_dataset(
    matched_csv: Path,
    images_dir: Path,
    masks_dir: Path,
    output_dir: Path,
    dataset_id: int = 1,
    dataset_name: str = "Aorta",
    split: tuple[float, float, float] = config.DATASET_SPLIT,
    seed: int = 42,
) -> dict:
    """
    Construit le dataset nnU-Net depuis les fichiers matchés.

    Args:
        matched_csv:  fichier matched.csv produit par dicom_csv_matcher
        images_dir:   dossier contenant les volumes NIfTI (.nii.gz)
        masks_dir:    dossier contenant les masques NIfTI (.nii.gz)
        output_dir:   racine du dataset nnU-Net
        dataset_id:   identifiant numérique du dataset (ex: 1 → Dataset001)
        dataset_name: nom du dataset (ex: Aorta)
        split:        proportions train/val/test
        seed:         graine aléatoire

    Returns:
        dictionnaire de statistiques du dataset construit
    """
    random.seed(seed)

    df = pd.read_csv(matched_csv, dtype=str)
    cases = df["patient_id"].unique().tolist()
    random.shuffle(cases)

    n        = len(cases)
    n_train  = int(n * split[0])
    n_val    = int(n * split[1])
    # n_test = n - n_train - n_val

    train_cases = cases[:n_train]
    val_cases   = cases[n_train:n_train + n_val]
    test_cases  = cases[n_train + n_val:]

    dataset_folder = output_dir / f"Dataset{dataset_id:03d}_{dataset_name}"
    for sub in ("imagesTr", "labelsTr", "imagesTs", "labelsTs", "imagesVal", "labelsVal"):
        (dataset_folder / sub).mkdir(parents=True, exist_ok=True)

    stats = {"train": 0, "val": 0, "test": 0, "missing": 0}

    def copy_case(pid: str, img_subdir: str, lbl_subdir: str) -> bool:
        img_src  = images_dir / f"{pid}.nii.gz"
        mask_src = masks_dir  / f"{pid}.nii.gz"

        if not img_src.exists() or not mask_src.exists():
            logger.warning("Fichiers manquants pour %s", pid)
            stats["missing"] += 1
            return False

        case_id = f"{dataset_name}_{pid}_0000"
        shutil.copy2(img_src,  dataset_folder / img_subdir / f"{case_id}.nii.gz")
        shutil.copy2(mask_src, dataset_folder / lbl_subdir / f"{pid}.nii.gz")
        return True

    for pid in train_cases:
        if copy_case(pid, "imagesTr", "labelsTr"):
            stats["train"] += 1
    for pid in val_cases:
        if copy_case(pid, "imagesVal", "labelsVal"):
            stats["val"] += 1
    for pid in test_cases:
        if copy_case(pid, "imagesTs", "labelsTs"):
            stats["test"] += 1

    # dataset.json obligatoire pour nnU-Net
    dataset_json = {
        "channel_names": NNUNET_CHANNEL_NAMES,
        "labels":        NNUNET_LABELS,
        "numTraining":   stats["train"],
        "file_ending":   ".nii.gz",
        "name":          dataset_name,
        "description":   f"DeepBridge — {dataset_name} segmentation",
    }
    with open(dataset_folder / "dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset_json, f, indent=2)

    logger.info("Dataset nnU-Net construit : %s", dataset_folder)
    logger.info("Train: %d | Val: %d | Test: %d | Manquants: %d",
                stats["train"], stats["val"], stats["test"], stats["missing"])

    return stats


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Construction du dataset nnU-Net")
    p.add_argument("matched_csv", type=Path)
    p.add_argument("images_dir",  type=Path)
    p.add_argument("masks_dir",   type=Path)
    p.add_argument("output_dir",  type=Path)
    p.add_argument("--id",   type=int, default=1)
    p.add_argument("--name", default="Aorta")
    a = p.parse_args()
    build_dataset(a.matched_csv, a.images_dir, a.masks_dir, a.output_dir, a.id, a.name)
