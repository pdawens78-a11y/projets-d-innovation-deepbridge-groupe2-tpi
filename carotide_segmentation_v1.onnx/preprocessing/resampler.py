"""
resampler.py
============
Couche 2 — Prétraitement | DeepBridge — CHU Nice 2020-2021

Rééchantillonnage des volumes NIfTI vers un espacement voxel uniforme
de 1×1×1 mm via SimpleITK.

Pourquoi le resampling est nécessaire
--------------------------------------
Les scanners du CHU Nice n'ont pas tous le même espacement voxel.
Selon le protocole d'acquisition et le constructeur, un voxel peut
mesurer 0.5 mm, 0.742 mm ou 1.2 mm. Cette hétérogénéité pose un
problème majeur pour nnU-Net :

  - Le modèle apprend des filtres convolutifs de taille fixe (ex: 3×3×3).
  - Si un voxel fait 0.5 mm chez un patient et 1.2 mm chez un autre,
    un filtre 3×3×3 capture 1.5 mm chez le premier et 3.6 mm chez le
    second — pas la même région anatomique.
  - Le resampling garantit que le même filtre capture toujours la
    même région physique en mm, quel que soit le scanner.

Cible : espacement isotropique 1.0 × 1.0 × 1.0 mm (configurable).

État de l'art par promotion
----------------------------
- Groupe 2022-2023 : non réalisé.
- Groupe 2023-2024 : non réalisé.
- Groupe 2025-2026 : réalisé — SimpleITK, interpolation linéaire,
                     espacement cible configurable, rapport JSON.

Dépendances
-----------
    pip install SimpleITK nibabel numpy

Usage
-----
    py resampler.py
    py resampler.py <hu_volumes_dir>
    py resampler.py <hu_volumes_dir> --output-dir <resampled_dir>
    py resampler.py <hu_volumes_dir> --spacing 1.0 1.0 1.0
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
    import SimpleITK as sitk
    SITK_AVAILABLE = True
except ImportError:
    SITK_AVAILABLE = False

try:
    import nibabel as nib
    NIBABEL_AVAILABLE = True
except ImportError:
    NIBABEL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Espacement voxel cible en mm (dz, dy, dx).
# Isotropique 1 mm³ — standard nnU-Net pour la segmentation aortique.
TARGET_SPACING = (1.0, 1.0, 1.0)

# Dossiers par défaut
DEFAULT_HU_DIR         = Path(r"C:\deepbridge\hu_volumes")
DEFAULT_RESAMPLED_DIR  = Path(r"C:\deepbridge\resampled_volumes")


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

    logger = logging.getLogger("resampler")
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
        log_dir / "resampler.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Lecture et écriture NIfTI
# ---------------------------------------------------------------------------

def load_nifti(nifti_path: Path) -> tuple:
    """
    Charge un volume NIfTI produit par hu_converter.py.

    Parameters
    ----------
    nifti_path : chemin vers le fichier .nii.gz

    Returns
    -------
    (volume_zyx, spacing_zyx) :
        volume_zyx  — tableau numpy (Z, H, W) float32
        spacing_zyx — (dz, dy, dx) en mm extrait de l'affine matrix
    """
    if not NIBABEL_AVAILABLE:
        raise RuntimeError("nibabel non installé. Lancez : pip install nibabel")

    img     = nib.load(str(nifti_path))
    data    = img.get_fdata(dtype=np.float32)   # (X, Y, Z) en NIfTI
    affine  = img.affine

    # Extraire l'espacement depuis la diagonale de l'affine matrix
    dx = abs(float(affine[0, 0]))
    dy = abs(float(affine[1, 1]))
    dz = abs(float(affine[2, 2]))

    # Transposer de (X, Y, Z) NIfTI → (Z, H, W) numpy
    volume = data.transpose(2, 1, 0).astype(np.float32)

    return volume, (dz, dy, dx)


def save_nifti(
    volume:      np.ndarray,
    spacing:     tuple,
    output_path: Path,
) -> None:
    """
    Sauvegarde un volume numpy (Z, H, W) au format NIfTI (.nii.gz).

    Parameters
    ----------
    volume      : tableau (Z, H, W) float32
    spacing     : (dz, dy, dx) en mm
    output_path : chemin de sortie
    """
    if not NIBABEL_AVAILABLE:
        raise RuntimeError("nibabel non installé. Lancez : pip install nibabel")

    dz, dy, dx = spacing
    affine = np.diag([dx, dy, dz, 1.0])

    # Transposer de (Z, H, W) → (X, Y, Z) pour NIfTI
    volume_nifti = volume.transpose(2, 1, 0)

    nifti_img = nib.Nifti1Image(volume_nifti, affine)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nifti_img, str(output_path))


# ---------------------------------------------------------------------------
# Resampling — fonction pure et testable
# ---------------------------------------------------------------------------

def resample_volume(
    volume:           np.ndarray,
    original_spacing: tuple,
    target_spacing:   tuple = TARGET_SPACING,
    interpolator:     int   = None,
) -> tuple:
    """
    Rééchantillonne un volume 3D vers target_spacing via SimpleITK.

    Algorithme
    ----------
    1. Convertir le volume numpy en image SimpleITK
    2. Définir l'espacement original (dx, dy, dz) — convention SimpleITK
    3. Calculer la nouvelle taille en voxels :
       new_size = original_size × original_spacing / target_spacing
    4. Appliquer le filtre ResampleImageFilter avec interpolation linéaire
    5. Convertir le résultat en tableau numpy

    Interpolation linéaire (sitkLinear)
    ------------------------------------
    L'interpolation linéaire est le compromis optimal entre qualité et
    vitesse pour des images médicales en niveaux de gris. Elle évite
    les artefacts de l'interpolation au plus proche voisin (sitkNearest)
    tout en étant plus rapide que l'interpolation cubique (sitkBSpline).

    État de l'art par promotion
    ----------------------------
    - Groupe 2022-2023 : non réalisé.
    - Groupe 2023-2024 : non réalisé.
    - Groupe 2025-2026 : réalisé — SimpleITK, interpolation linéaire.

    Parameters
    ----------
    volume           : tableau (Z, H, W) float32
    original_spacing : (dz, dy, dx) en mm — espacement d'origine
    target_spacing   : (dz, dy, dx) en mm — espacement cible (défaut 1 mm)
    interpolator     : interpolateur SimpleITK (défaut : sitkLinear)

    Returns
    -------
    (volume_resampled, new_spacing) :
        volume_resampled — tableau (Z', H', W') float32 rééchantillonné
        new_spacing      — espacement effectif après resampling
    """
    if not SITK_AVAILABLE:
        raise RuntimeError(
            "SimpleITK non installé. Lancez : pip install SimpleITK"
        )

    if interpolator is None:
        interpolator = sitk.sitkLinear

    # Convertir numpy (Z, H, W) → SimpleITK image
    # SimpleITK utilise la convention (X, Y, Z) = (W, H, Z)
    sitk_image = sitk.GetImageFromArray(volume)

    # SimpleITK attend le spacing en (dx, dy, dz) — ordre inversé
    orig_sp_sitk = [
        float(original_spacing[2]),   # dx
        float(original_spacing[1]),   # dy
        float(original_spacing[0]),   # dz
    ]
    sitk_image.SetSpacing(orig_sp_sitk)

    # Taille originale et cible
    orig_size = np.array(sitk_image.GetSize())          # (W, H, Z)
    orig_sp   = np.array(sitk_image.GetSpacing())       # (dx, dy, dz)
    tgt_sp    = np.array([
        target_spacing[2],   # dx
        target_spacing[1],   # dy
        target_spacing[0],   # dz
    ])

    # Nouvelle taille : new_size = orig_size × orig_spacing / target_spacing
    new_size = np.round(orig_size * orig_sp / tgt_sp).astype(int).tolist()

    # Configurer le filtre de rééchantillonnage
    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputSpacing(tgt_sp.tolist())
    resampler.SetSize(new_size)
    resampler.SetInterpolator(interpolator)
    resampler.SetOutputDirection(sitk_image.GetDirection())
    resampler.SetOutputOrigin(sitk_image.GetOrigin())
    resampler.SetTransform(sitk.Transform())
    resampler.SetDefaultPixelValue(0)

    # Appliquer le resampling
    resampled_sitk = resampler.Execute(sitk_image)

    # Convertir en numpy (Z, H, W)
    volume_resampled = sitk.GetArrayFromImage(resampled_sitk).astype(np.float32)

    # Espacement effectif après resampling (dz, dy, dx)
    actual_sp = tuple(reversed(resampled_sitk.GetSpacing()))

    return volume_resampled, actual_sp


# ---------------------------------------------------------------------------
# Traitement d'un volume NIfTI
# ---------------------------------------------------------------------------

def process_volume(
    nifti_path:     Path,
    output_dir:     Path,
    target_spacing: tuple,
    logger:         logging.Logger,
) -> dict:
    """
    Charge un volume NIfTI, le rééchantillonne, et le sauvegarde.

    Parameters
    ----------
    nifti_path     : chemin vers le .nii.gz produit par hu_converter.py
    output_dir     : dossier de sortie
    target_spacing : (dz, dy, dx) cible en mm

    Returns
    -------
    dict : métadonnées du resampling (shapes avant/après, spacings, ratio)
    """
    patient_folder = nifti_path.parent.name
    filename       = nifti_path.name

    try:
        # Charger le volume HU converti
        volume, original_spacing = load_nifti(nifti_path)
        shape_before = volume.shape

        # Rééchantillonner
        volume_resampled, actual_spacing = resample_volume(
            volume, original_spacing, target_spacing
        )
        shape_after = volume_resampled.shape

        # Sauvegarder
        out_path = output_dir / patient_folder / filename
        save_nifti(volume_resampled, actual_spacing, out_path)

        # Calcul du ratio de compression/expansion
        ratio = np.prod(shape_after) / np.prod(shape_before)

        result = {
            "status":            "ok",
            "patient_folder":    patient_folder,
            "filename":          filename,
            "original_spacing":  list(original_spacing),
            "target_spacing":    list(target_spacing),
            "actual_spacing":    list(actual_spacing),
            "shape_before":      list(shape_before),
            "shape_after":       list(shape_after),
            "volume_ratio":      round(ratio, 3),
            "output_path":       str(out_path),
        }

        logger.debug(
            "OK %s — %s → %s (spacing %.3f → %.3f mm)",
            patient_folder,
            shape_before, shape_after,
            original_spacing[0], actual_spacing[0],
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

def collect_nifti_files(hu_dir: Path) -> list:
    """
    Collecte tous les fichiers .nii.gz dans hu_dir.
    Structure attendue : hu_dir / patient_folder / *.nii.gz
    """
    nifti_files = []
    for patient_dir in sorted(hu_dir.iterdir()):
        if not patient_dir.is_dir() or patient_dir.name.startswith("_"):
            continue
        for f in sorted(patient_dir.glob("*.nii.gz")):
            nifti_files.append(f)
    return nifti_files


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(
    hu_dir:         Path,
    output_dir:     Optional[Path] = None,
    target_spacing: tuple = TARGET_SPACING,
) -> list:
    """
    Orchestre le resampling de tous les volumes NIfTI.

    Traitement séquentiel pour maîtriser la consommation mémoire.
    Chaque volume est chargé, rééchantillonné et sauvegardé avant
    de passer au suivant.

    Parameters
    ----------
    hu_dir         : dossier contenant les volumes produits par hu_converter.py
    output_dir     : dossier de sortie (défaut : resampled_volumes/)
    target_spacing : espacement cible (dz, dy, dx) en mm

    Returns
    -------
    list[dict] : résultats du resampling pour chaque volume
    """
    out    = output_dir or DEFAULT_RESAMPLED_DIR
    logger = setup_logging(out)
    t0     = time.time()

    logger.info("Démarrage du resampling")
    logger.info("Source          : %s", hu_dir)
    logger.info("Destination     : %s", out)
    logger.info("Espacement cible: %.1f × %.1f × %.1f mm",
                target_spacing[0], target_spacing[1], target_spacing[2])

    if not SITK_AVAILABLE:
        logger.error(
            "SimpleITK non installé. Lancez : pip install SimpleITK"
        )
        sys.exit(1)

    nifti_files = collect_nifti_files(hu_dir)
    total       = len(nifti_files)
    logger.info("%d volume(s) à rééchantillonner", total)

    if total == 0:
        logger.error(
            "Aucun fichier .nii.gz trouvé dans %s. "
            "Vérifiez que hu_converter.py a été exécuté.", hu_dir
        )
        return []

    results = []
    ok      = 0
    errors  = 0

    for i, nifti_path in enumerate(nifti_files, start=1):
        result = process_volume(nifti_path, out, target_spacing, logger)
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
        "timestamp":      datetime.utcnow().isoformat() + "Z",
        "total":          total,
        "ok":             ok,
        "errors":         errors,
        "target_spacing": list(target_spacing),
        "elapsed_sec":    round(time.time() - t0, 2),
        "results":        results,
    }
    report_path = out / "resampling_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("─── Résumé resampling ─────────────────────────────────────")
    logger.info("  Volumes rééchantillonnés : %d / %d", ok, total)
    logger.info("  Erreurs                  : %d", errors)
    logger.info("  Durée totale             : %.2f secondes", time.time() - t0)
    logger.info("  Rapport                  : %s", report_path)
    logger.info("───────────────────────────────────────────────────────────")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resampling des volumes NIfTI — DeepBridge / CHU Nice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Espacement cible par défaut : {TARGET_SPACING[0]} × {TARGET_SPACING[1]} × {TARGET_SPACING[2]} mm (isotropique)

Dépendances requises :
  pip install SimpleITK nibabel numpy

Exemples :
  py resampler.py
  py resampler.py C:\\deepbridge\\hu_volumes
  py resampler.py C:\\deepbridge\\hu_volumes --output-dir C:\\deepbridge\\resampled_volumes
  py resampler.py C:\\deepbridge\\hu_volumes --spacing 0.5 0.5 0.5
        """,
    )
    parser.add_argument(
        "hu_dir", nargs="?", type=Path,
        default=DEFAULT_HU_DIR,
        help=f"Dossier des volumes HU (défaut : {DEFAULT_HU_DIR})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Dossier de sortie (défaut : C:\\deepbridge\\resampled_volumes)",
    )
    parser.add_argument(
        "--spacing", type=float, nargs=3,
        default=list(TARGET_SPACING),
        metavar=("DZ", "DY", "DX"),
        help=f"Espacement cible en mm (défaut : {TARGET_SPACING})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.hu_dir.exists():
        print(
            f"Erreur : dossier introuvable : {args.hu_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    run(
        hu_dir=args.hu_dir,
        output_dir=args.output_dir,
        target_spacing=tuple(args.spacing),
    )