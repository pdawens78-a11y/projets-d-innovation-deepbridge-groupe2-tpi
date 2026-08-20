"""
annotation/nascet_calculator.py
================================
Couche 3 — Calcul automatique du taux de sténose (méthode NASCET).
NASCET = (1 - diamètre_stenose / diamètre_distal) × 100 %
"""
import logging, sys
import numpy as np
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("nascet_calculator")


@dataclass
class NascetResult:
    patient_id: str
    series_uid: str
    stenosis_diameter_mm: float    # diamètre minimal à la sténose
    distal_diameter_mm: float      # diamètre de référence distal
    nascet_percent: float          # taux de sténose NASCET (%)
    is_significant: bool           # True si >= NASCT_THRESHOLD (70%)
    method: str = "NASCET"


def compute_nascet(stenosis_diam: float, distal_diam: float) -> float:
    """
    Calcule le taux de sténose NASCET.

    Args:
        stenosis_diam: diamètre luminal minimal à la sténose (mm)
        distal_diam:   diamètre de référence distal sain (mm)

    Returns:
        taux de sténose en pourcentage [0, 100]
    """
    if distal_diam <= 0:
        raise ValueError(f"Diamètre distal invalide : {distal_diam}")
    if stenosis_diam < 0:
        raise ValueError(f"Diamètre sténose invalide : {stenosis_diam}")
    if stenosis_diam > distal_diam:
        logger.warning("Diamètre sténose (%.2f) > distal (%.2f) — taux forcé à 0%%",
                       stenosis_diam, distal_diam)
        return 0.0

    return (1 - stenosis_diam / distal_diam) * 100.0


def measure_from_mask(
    mask_volume: np.ndarray,
    spacing: tuple[float, float, float],
    stenosis_slice_idx: int,
    distal_slice_idx: int,
) -> tuple[float, float]:
    """
    Mesure les diamètres (sténose + distal) à partir d'un masque binaire 3D.
    Approximation : diamètre = 2 * sqrt(aire / π), en mm.

    Args:
        mask_volume:       masque binaire (Z, H, W) bool/int
        spacing:           (dz, dy, dx) en mm par voxel
        stenosis_slice_idx: indice Z de la coupe à la sténose
        distal_slice_idx:   indice Z de la coupe de référence distale

    Returns:
        (stenosis_diameter_mm, distal_diameter_mm)
    """
    _, dy, dx = spacing
    pixel_area_mm2 = dy * dx

    def diameter_at(z: int) -> float:
        slc = mask_volume[z].astype(bool)
        area_mm2 = slc.sum() * pixel_area_mm2
        return 2.0 * np.sqrt(area_mm2 / np.pi)

    stenosis_diam = diameter_at(stenosis_slice_idx)
    distal_diam   = diameter_at(distal_slice_idx)

    logger.debug("Diamètre sténose: %.2f mm | distal: %.2f mm", stenosis_diam, distal_diam)
    return stenosis_diam, distal_diam


def evaluate(
    patient_id: str,
    series_uid: str,
    mask_volume: np.ndarray,
    spacing: tuple[float, float, float],
    stenosis_slice_idx: int,
    distal_slice_idx: int,
) -> NascetResult:
    """
    Point d'entrée principal : calcule le NASCET complet pour un patient.
    """
    stenosis_diam, distal_diam = measure_from_mask(
        mask_volume, spacing, stenosis_slice_idx, distal_slice_idx
    )
    nascet = compute_nascet(stenosis_diam, distal_diam)
    is_sig = (nascet / 100.0) >= config.NASCT_THRESHOLD

    logger.info("Patient %s — NASCET: %.1f%% (%s)",
                patient_id, nascet, "SIGNIFICATIVE" if is_sig else "non significative")

    return NascetResult(
        patient_id=patient_id,
        series_uid=series_uid,
        stenosis_diameter_mm=round(stenosis_diam, 3),
        distal_diameter_mm=round(distal_diam, 3),
        nascet_percent=round(nascet, 2),
        is_significant=is_sig,
    )
