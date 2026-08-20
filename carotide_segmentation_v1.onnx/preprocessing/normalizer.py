"""
normalizer.py
=============
Couche 2 — Prétraitement | DeepBridge — CHU Nice 2020-2021

Normalisation des volumes NIfTI rééchantillonnés via deux techniques
successives : Z-score sur le volume entier, puis CLAHE coupe par coupe.

Pourquoi normaliser après le resampling
-----------------------------------------
Après la conversion HU et le resampling, les volumes sont dans [0, 1]
grâce au fenêtrage. Cependant, la distribution des intensités varie
encore d'un patient à l'autre selon :
  - L'état clinique (présence de calcifications, sténose sévère)
  - Le protocole d'injection de produit de contraste
  - L'indice de masse corporelle du patient

Sans normalisation, le modèle nnU-Net reçoit des données dont la
distribution statistique est hétérogène, ce qui ralentit la convergence
et dégrade les performances de segmentation.

Deux normalisations complémentaires
-------------------------------------
1. Z-score : standardise la distribution globale du volume (mean=0, std=1)
2. CLAHE   : améliore le contraste local coupe par coupe pour rendre
             les structures aortiques fines plus visibles

État de l'art par promotion
----------------------------
- Groupe 2022-2023 : non réalisé.
- Groupe 2023-2024 : non réalisé.
- Groupe 2025-2026 : réalisé — Z-score + CLAHE, fonctions pures testables,
                     rapport JSON, sauvegarde NIfTI.

Dépendances
-----------
    pip install opencv-python nibabel numpy

Usage
-----
    py normalizer.py
    py normalizer.py <resampled_dir>
    py normalizer.py <resampled_dir> --output-dir <normalized_dir>
    py normalizer.py <resampled_dir> --no-clahe
"""

import json
import logging
import logging.handlers
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import nibabel as nib
    NIBABEL_AVAILABLE = True
except ImportError:
    NIBABEL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Paramètres CLAHE
CLAHE_CLIP_LIMIT  = 2.0        # limite de contraste — évite la sur-amplification
CLAHE_TILE_GRID   = (8, 8)     # grille de tuiles pour l'adaptation locale

# Dossiers par défaut
DEFAULT_RESAMPLED_DIR  = Path(r"C:\deepbridge\resampled_volumes")
DEFAULT_NORMALIZED_DIR = Path(r"C:\deepbridge\normalized_volumes")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(output_dir: Path) -> logging.Logger:
    """
    Logger avec deux handlers :
      - Console : format lisible en temps réel
      - Fichier JSON rotatif dans output_dir/logs/
    """
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("normalizer")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    )
    logger.addHandler(console)

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "ts":    datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "level": record.levelname,
                "msg":   record.getMessage(),
            }
            if record.exc_info:
                payload["exc"] = self.formatException(record.exc_info)
            return json.dumps(payload, ensure_ascii=False)

    fh = logging.handlers.RotatingFileHandler(
        log_dir / "normalizer.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Normalisation — fonctions pures et testables
# ---------------------------------------------------------------------------

def zscore(volume: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """
    Normalisation Z-score sur le volume entier.

    Transforme la distribution des intensités pour obtenir mean=0, std=1.
    Un epsilon évite la division par zéro sur des volumes constants.

    Formule : z = (x - mean) / (std + eps)

    Pourquoi Z-score sur le volume entier (et non coupe par coupe) ?
    -----------------------------------------------------------------
    Si on normalise coupe par coupe, chaque coupe a sa propre moyenne
    et son propre écart-type. Une coupe axiale dans le poumon et une
    coupe dans l'aorte auraient des distributions incomparables.
    En normalisant le volume entier, on préserve les relations d'intensité
    entre les différentes régions anatomiques — information cruciale pour
    la segmentation.

    État de l'art par promotion
    ----------------------------
    - Groupe 2022-2023 : non réalisé.
    - Groupe 2023-2024 : non réalisé.
    - Groupe 2025-2026 : réalisé — Z-score sur volume entier.

    Parameters
    ----------
    volume : tableau numpy (Z, H, W) float32
    eps    : terme de lissage pour éviter la division par zéro

    Returns
    -------
    Tableau numpy float32 normalisé (mean≈0, std≈1)
    """
    mean = volume.mean()
    std  = volume.std()
    return ((volume - mean) / (std + eps)).astype(np.float32)


def clahe_slice(
    slice_2d:   np.ndarray,
    clip_limit: float = CLAHE_CLIP_LIMIT,
    tile_grid:  tuple = CLAHE_TILE_GRID,
) -> np.ndarray:
    """
    Applique CLAHE (Contrast Limited Adaptive Histogram Equalization)
    sur une coupe 2D via OpenCV.

    CLAHE améliore le contraste local en égalisant l'histogramme dans
    des petites régions (tuiles) plutôt que sur l'image entière. La
    limite de contraste (clip_limit) évite l'amplification excessive
    du bruit dans les régions homogènes.

    Pipeline interne
    ----------------
    1. Convertir la coupe float32 [0,1] → uint8 [0,255] pour OpenCV
    2. Appliquer CLAHE sur l'image uint8
    3. Reconvertir en float32 [0,1]

    Pourquoi CLAHE coupe par coupe (et non sur le volume entier) ?
    ---------------------------------------------------------------
    CLAHE est une opération 2D. Appliquer un CLAHE 3D serait possible
    mais très lent et moins standard. Les réseaux de segmentation médicale
    travaillent souvent en 2D+1 ou en 3D — le CLAHE axial coupe par coupe
    est le compromis qualité/vitesse adopté en imagerie médicale clinique.

    État de l'art par promotion
    ----------------------------
    - Groupe 2022-2023 : non réalisé.
    - Groupe 2023-2024 : non réalisé.
    - Groupe 2025-2026 : réalisé — CLAHE axial via OpenCV.

    Parameters
    ----------
    slice_2d   : coupe 2D float32, valeurs quelconques après Z-score
    clip_limit : limite de contraste CLAHE (défaut : 2.0)
    tile_grid  : taille de la grille de tuiles (défaut : 8×8)

    Returns
    -------
    Coupe 2D float32 dans [0, 1] après CLAHE
    """
    if not CV2_AVAILABLE:
        raise RuntimeError(
            "OpenCV non installé. Lancez : pip install opencv-python"
        )

    s_min = slice_2d.min()
    s_max = slice_2d.max()

    # Cas dégénéré : coupe constante (ex: hors du champ de vue)
    if s_max - s_min < 1e-8:
        return np.zeros_like(slice_2d, dtype=np.float32)

    # Normaliser en [0, 255] pour OpenCV
    normalized = ((slice_2d - s_min) / (s_max - s_min) * 255).astype(np.uint8)

    # Appliquer CLAHE
    clahe_obj = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    enhanced  = clahe_obj.apply(normalized)

    # Reconvertir en float32 [0, 1]
    return (enhanced.astype(np.float32) / 255.0)


def apply_clahe_volume(
    volume:     np.ndarray,
    clip_limit: float = CLAHE_CLIP_LIMIT,
    tile_grid:  tuple = CLAHE_TILE_GRID,
) -> np.ndarray:
    """
    Applique CLAHE sur chaque coupe axiale d'un volume (Z, H, W).

    Parameters
    ----------
    volume     : tableau (Z, H, W) float32
    clip_limit : limite de contraste CLAHE
    tile_grid  : taille de la grille de tuiles

    Returns
    -------
    Volume (Z, H, W) float32 après CLAHE coupe par coupe
    """
    result = np.zeros_like(volume, dtype=np.float32)
    for i in range(volume.shape[0]):
        result[i] = clahe_slice(volume[i], clip_limit, tile_grid)
    return result


def normalize(
    volume:     np.ndarray,
    use_clahe:  bool  = True,
    clip_limit: float = CLAHE_CLIP_LIMIT,
    tile_grid:  tuple = CLAHE_TILE_GRID,
) -> np.ndarray:
    """
    Pipeline de normalisation complet :
      1. Z-score sur le volume entier
      2. CLAHE coupe par coupe (optionnel, activé par défaut)

    Parameters
    ----------
    volume     : tableau (Z, H, W) float32
    use_clahe  : appliquer CLAHE après Z-score (défaut : True)
    clip_limit : paramètre CLAHE
    tile_grid  : paramètre CLAHE

    Returns
    -------
    Volume (Z, H, W) float32 normalisé
    """
    vol = zscore(volume)

    if use_clahe:
        vol = apply_clahe_volume(vol, clip_limit, tile_grid)

    return vol


# ---------------------------------------------------------------------------
# Lecture et écriture NIfTI
# ---------------------------------------------------------------------------

def load_nifti(nifti_path: Path) -> tuple:
    """Charge un volume NIfTI. Retourne (volume_zyx, spacing_zyx)."""
    if not NIBABEL_AVAILABLE:
        raise RuntimeError("nibabel non installé. Lancez : pip install nibabel")

    img    = nib.load(str(nifti_path))
    data   = img.get_fdata(dtype=np.float32)
    affine = img.affine

    dx = abs(float(affine[0, 0]))
    dy = abs(float(affine[1, 1]))
    dz = abs(float(affine[2, 2]))

    volume = data.transpose(2, 1, 0).astype(np.float32)
    return volume, (dz, dy, dx)


def save_nifti(volume: np.ndarray, spacing: tuple, output_path: Path) -> None:
    """Sauvegarde un volume numpy (Z, H, W) au format NIfTI."""
    if not NIBABEL_AVAILABLE:
        raise RuntimeError("nibabel non installé. Lancez : pip install nibabel")

    dz, dy, dx   = spacing
    affine        = np.diag([dx, dy, dz, 1.0])
    volume_nifti  = volume.transpose(2, 1, 0)
    nifti_img     = nib.Nifti1Image(volume_nifti, affine)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nifti_img, str(output_path))


# ---------------------------------------------------------------------------
# Traitement d'un volume NIfTI
# ---------------------------------------------------------------------------

def process_volume(
    nifti_path:  Path,
    output_dir:  Path,
    use_clahe:   bool,
    logger:      logging.Logger,
) -> dict:
    """
    Charge un volume NIfTI rééchantillonné, le normalise, et le sauvegarde.

    Parameters
    ----------
    nifti_path : chemin vers le .nii.gz produit par resampler.py
    output_dir : dossier de sortie
    use_clahe  : appliquer CLAHE après Z-score

    Returns
    -------
    dict : statistiques avant/après normalisation
    """
    patient_folder = nifti_path.parent.name
    filename       = nifti_path.name

    try:
        # Charger le volume rééchantillonné
        volume, spacing = load_nifti(nifti_path)

        # Statistiques avant normalisation
        mean_before = float(volume.mean())
        std_before  = float(volume.std())
        min_before  = float(volume.min())
        max_before  = float(volume.max())

        # Normaliser
        volume_normalized = normalize(volume, use_clahe=use_clahe)

        # Statistiques après normalisation
        mean_after = float(volume_normalized.mean())
        std_after  = float(volume_normalized.std())
        min_after  = float(volume_normalized.min())
        max_after  = float(volume_normalized.max())

        # Sauvegarder
        out_path = output_dir / patient_folder / filename
        save_nifti(volume_normalized, spacing, out_path)

        result = {
            "status":         "ok",
            "patient_folder": patient_folder,
            "filename":       filename,
            "shape":          list(volume.shape),
            "spacing_mm":     list(spacing),
            "use_clahe":      use_clahe,
            "before": {
                "mean": round(mean_before, 4),
                "std":  round(std_before,  4),
                "min":  round(min_before,  4),
                "max":  round(max_before,  4),
            },
            "after": {
                "mean": round(mean_after, 4),
                "std":  round(std_after,  4),
                "min":  round(min_after,  4),
                "max":  round(max_after,  4),
            },
            "output_path": str(out_path),
        }

        logger.debug(
            "OK %s — mean %.3f→%.3f | std %.3f→%.3f",
            patient_folder,
            mean_before, mean_after,
            std_before, std_after,
        )

        return result

    except Exception as exc:
        logger.error("ERREUR %s — %s", patient_folder, exc)
        return {
            "status":         "error",
            "patient_folder": patient_folder,
            "filename":       filename,
            "reason":         str(exc),
        }


# ---------------------------------------------------------------------------
# Collecte des volumes NIfTI
# ---------------------------------------------------------------------------

def collect_nifti_files(resampled_dir: Path) -> list:
    """
    Collecte tous les fichiers .nii.gz dans resampled_dir.
    Structure attendue : resampled_dir / patient_folder / *.nii.gz
    """
    nifti_files = []
    for patient_dir in sorted(resampled_dir.iterdir()):
        if not patient_dir.is_dir() or patient_dir.name.startswith("_"):
            continue
        for f in sorted(patient_dir.glob("*.nii.gz")):
            nifti_files.append(f)
    return nifti_files


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(
    resampled_dir: Path,
    output_dir:    Optional[Path] = None,
    use_clahe:     bool = True,
) -> list:
    """
    Orchestre la normalisation de tous les volumes rééchantillonnés.

    Parameters
    ----------
    resampled_dir : dossier produit par resampler.py
    output_dir    : dossier de sortie
    use_clahe     : appliquer CLAHE après Z-score (défaut : True)

    Returns
    -------
    list[dict] : résultats de normalisation pour chaque volume
    """
    out    = output_dir or DEFAULT_NORMALIZED_DIR
    logger = setup_logging(out)
    t0     = time.time()

    logger.info("Démarrage de la normalisation")
    logger.info("Source      : %s", resampled_dir)
    logger.info("Destination : %s", out)
    logger.info("Z-score     : activé")
    logger.info("CLAHE       : %s", "activé" if use_clahe else "désactivé")

    if not CV2_AVAILABLE and use_clahe:
        logger.error(
            "OpenCV non installé mais CLAHE activé. "
            "Lancez : pip install opencv-python"
        )
        sys.exit(1)

    nifti_files = collect_nifti_files(resampled_dir)
    total       = len(nifti_files)
    logger.info("%d volume(s) à normaliser", total)

    if total == 0:
        logger.error(
            "Aucun fichier .nii.gz trouvé dans %s. "
            "Vérifiez que resampler.py a été exécuté.", resampled_dir
        )
        return []

    results = []
    ok      = 0
    errors  = 0

    for i, nifti_path in enumerate(nifti_files, start=1):
        result = process_volume(nifti_path, out, use_clahe, logger)
        results.append(result)

        if result["status"] == "ok":
            ok += 1
        else:
            errors += 1

        if i % 10 == 0 or i == total:
            logger.info(
                "Progression : %d/%d (%.1f%%) — OK: %d | Erreurs: %d",
                i, total, 100 * i / total, ok, errors,
            )

    # Rapport JSON
    report = {
        "timestamp":   datetime.utcnow().isoformat() + "Z",
        "total":       total,
        "ok":          ok,
        "errors":      errors,
        "use_clahe":   use_clahe,
        "clahe_params": {
            "clip_limit": CLAHE_CLIP_LIMIT,
            "tile_grid":  list(CLAHE_TILE_GRID),
        },
        "elapsed_sec": round(time.time() - t0, 2),
        "results":     results,
    }
    report_path = out / "normalization_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("─── Résumé normalisation ──────────────────────────────────")
    logger.info("  Volumes normalisés : %d / %d", ok, total)
    logger.info("  Erreurs            : %d", errors)
    logger.info("  Durée totale       : %.2f secondes", time.time() - t0)
    logger.info("  Rapport            : %s", report_path)
    logger.info("───────────────────────────────────────────────────────────")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalisation Z-score + CLAHE — DeepBridge / CHU Nice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Normalisations appliquées :
  1. Z-score  : mean=0, std=1 sur le volume entier
  2. CLAHE    : clip_limit={CLAHE_CLIP_LIMIT}, tile_grid={CLAHE_TILE_GRID} (coupe par coupe)

Dépendances requises :
  pip install opencv-python nibabel numpy

Exemples :
  py normalizer.py
  py normalizer.py C:\\deepbridge\\resampled_volumes
  py normalizer.py C:\\deepbridge\\resampled_volumes --output-dir C:\\deepbridge\\normalized_volumes
  py normalizer.py C:\\deepbridge\\resampled_volumes --no-clahe
        """,
    )
    parser.add_argument(
        "resampled_dir", nargs="?", type=Path,
        default=DEFAULT_RESAMPLED_DIR,
        help=f"Dossier des volumes rééchantillonnés (défaut : {DEFAULT_RESAMPLED_DIR})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Dossier de sortie (défaut : C:\\deepbridge\\normalized_volumes)",
    )
    parser.add_argument(
        "--no-clahe", action="store_true",
        help="Désactiver CLAHE — appliquer uniquement le Z-score",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.resampled_dir.exists():
        print(
            f"Erreur : dossier introuvable : {args.resampled_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    run(
        resampled_dir=args.resampled_dir,
        output_dir=args.output_dir,
        use_clahe=not args.no_clahe,
    )