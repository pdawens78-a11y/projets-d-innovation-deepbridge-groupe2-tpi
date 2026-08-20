"""
preprocessing/augmentor.py
===========================
Couche 2 — Augmentation de données 3D via TorchIO (×50 par défaut).
Produit des volumes NIfTI augmentés pour l'entraînement nnU-Net.
"""
import logging, sys, random
from pathlib import Path
import numpy as np
import nibabel as nib

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("augmentor")

try:
    import torchio as tio
    TORCHIO_AVAILABLE = True
except ImportError:
    TORCHIO_AVAILABLE = False
    logger.warning("TorchIO non disponible — augmentation désactivée.")


# Pipeline d'augmentation TorchIO standard pour l'imagerie aortique CT
def build_augmentation_pipeline() -> "tio.Compose":
    """
    Construit le pipeline d'augmentation TorchIO.
    Chaque transformation est appliquée avec une probabilité p.
    """
    return tio.Compose([
        tio.RandomFlip(axes=(0, 1, 2), p=0.5),
        tio.RandomAffine(
            scales=(0.9, 1.1),
            degrees=15,
            translation=10,
            p=0.7,
        ),
        tio.RandomElasticDeformation(
            num_control_points=7,
            max_displacement=7.5,
            p=0.3,
        ),
        tio.RandomGamma(log_gamma=(-0.3, 0.3), p=0.5),
        tio.RandomNoise(mean=0, std=(0, 0.05), p=0.4),
        tio.RandomBlur(std=(0, 1.0), p=0.2),
    ])


def augment_volume(
    image_nii: Path,
    mask_nii: Path,
    output_dir: Path,
    n: int = config.AUGMENTATION_FACTOR,
    seed: int = 42,
) -> list[tuple[Path, Path]]:
    """
    Génère n volumes augmentés à partir d'une paire image/masque NIfTI.

    Args:
        image_nii:  chemin vers le volume image (.nii.gz)
        mask_nii:   chemin vers le masque de segmentation (.nii.gz)
        output_dir: dossier de sortie des volumes augmentés
        n:          nombre de volumes à générer
        seed:       graine aléatoire pour reproductibilité

    Returns:
        liste de tuples (image_augmentée_path, masque_augmenté_path)
    """
    if not TORCHIO_AVAILABLE:
        raise RuntimeError("TorchIO est requis pour l'augmentation. pip install torchio")

    output_dir.mkdir(parents=True, exist_ok=True)
    random.seed(seed)

    subject = tio.Subject(
        image=tio.ScalarImage(str(image_nii)),
        mask=tio.LabelMap(str(mask_nii)),
    )

    pipeline = build_augmentation_pipeline()
    results  = []

    for i in range(n):
        augmented = pipeline(subject)
        stem = image_nii.stem.replace(".nii", "")

        img_path  = output_dir / f"{stem}_aug{i:03d}_image.nii.gz"
        mask_path = output_dir / f"{stem}_aug{i:03d}_mask.nii.gz"

        augmented.image.save(str(img_path))
        augmented.mask.save(str(mask_path))

        results.append((img_path, mask_path))
        logger.debug("Augmentation %d/%d : %s", i + 1, n, img_path.name)

    logger.info("Augmentation terminée : %d volumes générés dans %s", n, output_dir)
    return results


def volume_to_nifti(volume: np.ndarray, spacing: tuple, output_path: Path) -> Path:
    """
    Sauvegarde un volume numpy en NIfTI (.nii.gz) avec le bon affine spacing.

    Args:
        volume:      tableau (Z, H, W) float32
        spacing:     (dz, dy, dx) en mm
        output_path: chemin de sortie

    Returns:
        chemin du fichier NIfTI créé
    """
    dz, dy, dx = spacing
    affine = np.diag([dx, dy, dz, 1.0])
    nifti  = nib.Nifti1Image(volume.transpose(2, 1, 0), affine)  # NIfTI attend (X, Y, Z)
    nib.save(nifti, str(output_path))
    logger.debug("NIfTI sauvegardé : %s — shape %s", output_path.name, volume.shape)
    return output_path
