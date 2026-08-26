"""
hu_converter.py
===============
Couche 2 — Prétraitement | DeepBridge — CHU Nice 2020-2021

Conversion des pixels DICOM bruts en Unités Hounsfield (HU) et
application d'un fenêtrage aortique pour normaliser les intensités
avant le resampling et la segmentation.

Pourquoi cette conversion est nécessaire
-----------------------------------------
Les valeurs de pixels stockées dans un fichier DICOM ne sont pas
directement comparables entre scanners. Chaque constructeur applique
une transformation affine propre (RescaleSlope, RescaleIntercept).
Sans cette conversion, un pixel de valeur 200 chez un scanner GE
n'a pas la même signification que chez un scanner Siemens.

Les Unités Hounsfield sont une échelle standardisée internationale :
  - Air           : -1000 HU
  - Eau           :     0 HU
  - Tissus mous   :  20-80 HU
  - Sang          :  40-60 HU
  - Os cortical   : +400 HU et au-delà

Fenêtrage aortique
------------------
Après conversion HU, un fenêtrage est appliqué pour ne conserver que
les densités pertinentes pour la segmentation aortique :
  - HU_MIN = -100  (exclut l'air et les poumons)
  - HU_MAX =  400  (exclut les os trop denses)
Les valeurs hors de cette fenêtre sont clippées, puis normalisées
dans [0, 1] pour l'entrée dans le réseau de neurones.

État de l'art par promotion
----------------------------
- Groupe 2022-2023 : lecture des pixels avec pydicom mais sans
                     application de RescaleSlope/RescaleIntercept.
                     Les valeurs brutes étaient utilisées directement.
- Groupe 2023-2024 : conversion PIL/numpy générique, pas de HU.
- Groupe 2025-2026 : conversion HU complète avec RescaleSlope,
                     RescaleIntercept, gestion des valeurs hors-champ
                     (-2000), fenêtrage aortique configurable,
                     sauvegarde NIfTI pour nnU-Net.

Usage
-----
    py hu_converter.py
    py hu_converter.py <sorted_dir>
    py hu_converter.py <sorted_dir> --output-dir <hu_dir>
    py hu_converter.py <sorted_dir> --hu-min -100 --hu-max 400
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
import pydicom
from pydicom.errors import InvalidDicomError

try:
    import nibabel as nib
    NIBABEL_AVAILABLE = True
except ImportError:
    NIBABEL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration — fenêtrage aortique
# ---------------------------------------------------------------------------

# Fenêtre Hounsfield pour la segmentation aortique.
# Ces valeurs encadrent les densités pertinentes : sang, paroi aortique,
# tissus mous environnants. L'air (-1000 HU) et les os denses (>400 HU)
# sont exclus car ils ne contribuent pas à la segmentation de l'aorte.
HU_MIN = -100
HU_MAX =  400

# Valeur hors-champ DICOM standard — pixels non acquis (bords du scout).
# Ces pixels doivent être remis à 0 avant la conversion HU pour ne pas
# fausser la normalisation.
DICOM_OUT_OF_FIELD_VALUE = -2000

# Dossier de sortie par défaut pour les volumes HU
DEFAULT_SORTED_DIR  = Path(r"C:\deepbridge\output")
DEFAULT_HU_DIR      = Path(r"C:\deepbridge\hu_volumes")


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

    logger = logging.getLogger("hu_converter")
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
        log_dir / "hu_converter.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Conversion HU — fonctions pures et testables
# ---------------------------------------------------------------------------

def to_hounsfield(
    pixel_array: np.ndarray,
    slope:       float,
    intercept:   float,
) -> np.ndarray:
    """
    Applique la transformation affine DICOM pour convertir les pixels
    bruts en Unités Hounsfield.

    Formule : HU = pixel_brut × slope + intercept

    Les pixels avec la valeur hors-champ (-2000) sont remis à 0 avant
    la conversion. Ces pixels correspondent aux zones non acquises
    (coins du volume, zones hors du champ de vue du scanner).

    État de l'art par promotion
    ----------------------------
    - Groupe 2022-2023 : utilisait ds.pixel_array directement sans
                         appliquer slope ni intercept.
    - Groupe 2023-2024 : conversion PIL, pas de HU.
    - Groupe 2025-2026 : conversion complète avec gestion hors-champ.

    Parameters
    ----------
    pixel_array : tableau numpy 2D des pixels bruts (une coupe)
    slope       : RescaleSlope extrait du fichier DICOM
    intercept   : RescaleIntercept extrait du fichier DICOM

    Returns
    -------
    Tableau numpy float32 en Unités Hounsfield
    """
    arr = pixel_array.astype(np.float32)

    # Remettre les pixels hors-champ à 0 avant la conversion
    arr[arr == DICOM_OUT_OF_FIELD_VALUE] = 0

    # Appliquer la transformation affine
    if slope != 1:
        arr = arr * float(slope)
    arr = arr + float(intercept)

    return arr


def window_hounsfield(
    hu_array: np.ndarray,
    hu_min:   float = HU_MIN,
    hu_max:   float = HU_MAX,
) -> np.ndarray:
    """
    Applique le fenêtrage aortique sur un volume ou une coupe en HU.

    Deux opérations successives :
      1. Clipping : valeurs hors [hu_min, hu_max] ramenées aux bornes
      2. Normalisation : ramène [hu_min, hu_max] vers [0, 1]

    La normalisation dans [0, 1] est requise par nnU-Net et la plupart
    des architectures de réseaux de neurones pour la segmentation.

    Parameters
    ----------
    hu_array : tableau numpy en HU (2D ou 3D)
    hu_min   : borne inférieure de la fenêtre (défaut : -100 HU)
    hu_max   : borne supérieure de la fenêtre (défaut :  400 HU)

    Returns
    -------
    Tableau numpy float32 normalisé dans [0, 1]
    """
    clipped = np.clip(hu_array, hu_min, hu_max)
    normalized = (clipped - hu_min) / (hu_max - hu_min)
    return normalized.astype(np.float32)


# ---------------------------------------------------------------------------
# Lecture et tri d'une série DICOM
# ---------------------------------------------------------------------------

def load_series(series_dir: Path) -> list:
    """
    Charge tous les fichiers .dcm d'une série et les trie par
    SliceLocation pour garantir l'ordre anatomique correct
    (crâne → pieds).

    Pourquoi trier par SliceLocation ?
    -----------------------------------
    Les fichiers DICOM dans un dossier ne sont pas nécessairement dans
    l'ordre anatomique. Sans tri, les coupes peuvent être empilées dans
    le mauvais ordre, produisant un volume anatomiquement incohérent.
    SliceLocation indique la position réelle de chaque coupe en mm.

    Parameters
    ----------
    series_dir : dossier contenant les fichiers .dcm d'une série

    Returns
    -------
    Liste de pydicom.Dataset triés par SliceLocation croissant.
    Lève ValueError si la série est vide ou illisible.
    """
    dcm_files = sorted(
        f for f in series_dir.iterdir()
        if f.is_file() and f.suffix == ".dcm" and not f.name.startswith(".")
    )

    if not dcm_files:
        raise ValueError(f"Aucun fichier .dcm dans : {series_dir}")

    slices = []
    for f in dcm_files:
        try:
            ds = pydicom.dcmread(str(f))   # avec pixels cette fois
            slices.append(ds)
        except InvalidDicomError as exc:
            raise ValueError(f"Fichier DICOM invalide : {f.name} — {exc}")

    # Tri par SliceLocation
    try:
        slices.sort(key=lambda ds: float(ds.SliceLocation))
    except AttributeError:
        raise ValueError(
            "Tag SliceLocation absent — impossible de trier les coupes. "
            "Cette série aurait dû être rejetée par validate_dataset.py."
        )

    return slices


def get_voxel_spacing(slices: list) -> tuple:
    """
    Extrait l'espacement voxel (dz, dy, dx) depuis les métadonnées DICOM.

    dz : distance inter-coupes (mm) — calculée depuis deux SliceLocation
    dy : espacement ligne (mm)       — extrait de PixelSpacing[0]
    dx : espacement colonne (mm)     — extrait de PixelSpacing[1]

    Cet espacement est requis pour le resampling (hu_converter → resampler).

    Parameters
    ----------
    slices : liste de datasets DICOM triés par SliceLocation

    Returns
    -------
    (dz, dy, dx) en millimètres
    """
    ds = slices[0]
    ps = ds.PixelSpacing if hasattr(ds, "PixelSpacing") else [1.0, 1.0]
    dy, dx = float(ps[0]), float(ps[1])

    if len(slices) >= 2:
        dz = abs(float(slices[1].SliceLocation) - float(slices[0].SliceLocation))
    else:
        dz = float(getattr(ds, "SliceThickness", 1.0))

    return dz, dy, dx


# ---------------------------------------------------------------------------
# Conversion d'une série complète
# ---------------------------------------------------------------------------

def convert_series(slices: list) -> tuple:
    """
    Convertit une liste de coupes DICOM en deux volumes 3D numpy :
      - volume_hu       : valeurs en Unités Hounsfield (float32)
      - volume_windowed : valeurs normalisées [0, 1] après fenêtrage

    Pipeline appliqué coupe par coupe
    -----------------------------------
    Pour chaque coupe ds dans slices :
      1. Extraire RescaleSlope et RescaleIntercept (défaut : 1 et 0)
      2. Appliquer to_hounsfield(ds.pixel_array, slope, intercept)
      3. Empiler toutes les coupes → volume 3D (Z, H, W)
      4. Appliquer window_hounsfield() sur le volume entier

    État de l'art par promotion
    ----------------------------
    - Groupe 2022-2023 : pas de conversion HU, valeurs brutes utilisées.
    - Groupe 2023-2024 : pas de traitement volumétrique 3D.
    - Groupe 2025-2026 : conversion complète, deux volumes produits.

    Parameters
    ----------
    slices : liste de pydicom.Dataset triés par SliceLocation

    Returns
    -------
    (volume_hu, volume_windowed) — deux tableaux (Z, H, W) float32
    """
    if not slices:
        raise ValueError("Liste de coupes vide.")

    hu_slices = []
    for ds in slices:
        slope     = float(getattr(ds, "RescaleSlope",     1))
        intercept = float(getattr(ds, "RescaleIntercept", 0))
        hu_slice  = to_hounsfield(ds.pixel_array, slope, intercept)
        hu_slices.append(hu_slice)

    # Empiler les coupes → volume 3D (Z, H, W)
    volume_hu       = np.stack(hu_slices, axis=0).astype(np.float32)
    volume_windowed = window_hounsfield(volume_hu)

    return volume_hu, volume_windowed


# ---------------------------------------------------------------------------
# Sauvegarde NIfTI
# ---------------------------------------------------------------------------

def save_nifti(
    volume:      np.ndarray,
    spacing:     tuple,
    output_path: Path,
) -> Path:
    """
    Sauvegarde un volume numpy au format NIfTI (.nii.gz).

    Le format NIfTI est le standard d'entrée de nnU-Net. L'affine
    matrix encode l'espacement voxel pour que le modèle connaisse
    les dimensions réelles du volume en mm.

    Parameters
    ----------
    volume      : tableau (Z, H, W) float32
    spacing     : (dz, dy, dx) en mm
    output_path : chemin de sortie (.nii.gz)

    Returns
    -------
    Chemin du fichier NIfTI créé
    """
    if not NIBABEL_AVAILABLE:
        raise RuntimeError(
            "nibabel non installé. Lancez : pip install nibabel"
        )

    dz, dy, dx = spacing

    # NIfTI attend (X, Y, Z) — on transpose depuis (Z, H, W)
    volume_nifti = volume.transpose(2, 1, 0)

    # Affine matrix : encode l'espacement voxel
    affine = np.diag([dx, dy, dz, 1.0])

    nifti_img = nib.Nifti1Image(volume_nifti, affine)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nifti_img, str(output_path))

    return output_path


# ---------------------------------------------------------------------------
# Traitement d'une série complète
# ---------------------------------------------------------------------------

def process_series(
    series_dir:  Path,
    output_dir:  Path,
    hu_min:      float,
    hu_max:      float,
    logger:      logging.Logger,
) -> dict:
    """
    Traite une série DICOM complète :
      1. Charge et trie les coupes par SliceLocation
      2. Convertit en volume HU
      3. Applique le fenêtrage aortique
      4. Sauvegarde en NIfTI

    Parameters
    ----------
    series_dir : dossier de la série (output/PatientID/SeriesUID/)
    output_dir : dossier de sortie pour les volumes NIfTI
    hu_min     : borne inférieure du fenêtrage
    hu_max     : borne supérieure du fenêtrage

    Returns
    -------
    dict : métadonnées de la conversion (patient, série, stats HU, spacing)
    """
    patient_id = series_dir.parent.name
    series_uid = series_dir.name

    try:
        # Étape 1 : charger et trier les coupes
        slices  = load_series(series_dir)
        spacing = get_voxel_spacing(slices)

        # Étape 2 : convertir en HU et appliquer le fenêtrage
        volume_hu, volume_windowed = convert_series(slices)

        # Étape 3 : sauvegarder en NIfTI
        patient_out = output_dir / patient_id
        patient_out.mkdir(parents=True, exist_ok=True)

        nifti_path = patient_out / f"{patient_id}_{series_uid[:20]}_0000.nii.gz"

        # save_nifti() lève RuntimeError si nibabel est absent, ou toute
        # autre exception si l'écriture échoue (disque plein, permissions,
        # etc.). Dans les deux cas, l'exception remonte au except ci-dessous
        # et la série est marquée "error" — jamais "ok" sans fichier écrit.
        save_nifti(volume_windowed, spacing, nifti_path)

        result = {
            "status":     "ok",
            "patient_id": patient_id,
            "series_uid": series_uid,
            "nb_slices":  volume_hu.shape[0],
            "shape":      list(volume_hu.shape),
            "spacing_mm": list(spacing),
            "hu_min":     float(volume_hu.min()),
            "hu_max":     float(volume_hu.max()),
            "hu_mean":    float(volume_hu.mean()),
            "nifti_path": str(nifti_path),
        }

        logger.debug(
            "OK %s/%s — shape=%s, HU=[%.0f, %.0f], spacing=%.2fmm",
            patient_id, series_uid[:20],
            volume_hu.shape,
            volume_hu.min(), volume_hu.max(),
            spacing[0],
        )

        return result

    except Exception as exc:
        logger.error("ERREUR %s/%s — %s", patient_id, series_uid[:20], exc)
        return {
            "status":     "error",
            "patient_id": patient_id,
            "series_uid": series_uid,
            "reason":     str(exc),
        }


# ---------------------------------------------------------------------------
# Collecte des séries valides
# ---------------------------------------------------------------------------

def collect_series(sorted_dir: Path) -> list:
    """
    Collecte tous les dossiers de séries valides dans sorted_dir.
    Exclut les dossiers commençant par '_' (quarantaine, rejected, logs).
    """
    series_dirs = []
    for patient_dir in sorted(sorted_dir.iterdir()):
        if not patient_dir.is_dir() or patient_dir.name.startswith("_"):
            continue
        for series_dir in sorted(patient_dir.iterdir()):
            if series_dir.is_dir():
                series_dirs.append(series_dir)
    return series_dirs


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(
    sorted_dir:  Path,
    output_dir:  Optional[Path] = None,
    hu_min:      float = HU_MIN,
    hu_max:      float = HU_MAX,
) -> list:
    """
    Orchestre la conversion HU de toutes les séries valides.

    Traitement séquentiel (pas de parallélisme) car chaque série
    charge l'intégralité des pixels en mémoire — opération RAM-intensive.
    Sur 156 séries de ~500 coupes à 512×512 pixels en float32 :
    chaque volume occupe ~256 Mo RAM.

    Parameters
    ----------
    sorted_dir : arborescence validée produite par validate_dataset.py
    output_dir : dossier de sortie pour les volumes NIfTI
    hu_min     : borne inférieure du fenêtrage (défaut : -100 HU)
    hu_max     : borne supérieure du fenêtrage (défaut :  400 HU)

    Returns
    -------
    list[dict] : résultats de conversion pour chaque série
    """
    out    = output_dir or Path(str(sorted_dir).replace("output", "hu_volumes"))
    logger = setup_logging(out)
    t0     = time.time()

    logger.info("Démarrage de la conversion HU")
    logger.info("Source      : %s", sorted_dir)
    logger.info("Destination : %s", out)
    logger.info("Fenêtrage   : [%d HU, %d HU]", int(hu_min), int(hu_max))

    if not NIBABEL_AVAILABLE:
        logger.error(
            "nibabel non installé — impossible d'écrire les volumes NIfTI. "
            "Lancez : pip install nibabel (ou activez le venv du projet)."
        )
        raise RuntimeError(
            "nibabel non installé — arrêt immédiat pour ne pas produire un "
            "rapport de conversion faussement marqué 'ok' sans fichiers NIfTI écrits."
        )

    series_dirs = collect_series(sorted_dir)
    total       = len(series_dirs)
    logger.info("%d série(s) à convertir", total)

    if total == 0:
        logger.error(
            "Aucune série trouvée. Vérifiez que validate_dataset.py "
            "a été exécuté et que --move-rejected a été utilisé."
        )
        return []

    results = []
    ok      = 0
    errors  = 0

    for i, series_dir in enumerate(series_dirs, start=1):
        result = process_series(series_dir, out, hu_min, hu_max, logger)
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
        "hu_window":   [hu_min, hu_max],
        "elapsed_sec": round(time.time() - t0, 2),
        "results":     results,
    }
    report_path = out / "hu_conversion_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("─── Résumé conversion HU ──────────────────────────────────")
    logger.info("  Séries converties : %d / %d", ok, total)
    logger.info("  Erreurs           : %d", errors)
    logger.info("  Durée totale      : %.2f secondes", time.time() - t0)
    logger.info("  Rapport           : %s", report_path)
    logger.info("───────────────────────────────────────────────────────────")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Conversion HU des séries DICOM — DeepBridge / CHU Nice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Fenêtrage aortique appliqué :
  HU_MIN = {HU_MIN} (exclut l'air et les poumons)
  HU_MAX = {HU_MAX} (exclut les os trop denses)

Les volumes sont sauvegardés au format NIfTI (.nii.gz) compatible nnU-Net.

Exemples :
  py hu_converter.py
  py hu_converter.py C:\\deepbridge\\output
  py hu_converter.py C:\\deepbridge\\output --output-dir C:\\deepbridge\\hu_volumes
  py hu_converter.py C:\\deepbridge\\output --hu-min -200 --hu-max 600
        """,
    )
    parser.add_argument(
        "sorted_dir", nargs="?", type=Path,
        default=DEFAULT_SORTED_DIR,
        help=f"Dossier validé (défaut : {DEFAULT_SORTED_DIR})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Dossier de sortie pour les volumes NIfTI",
    )
    parser.add_argument(
        "--hu-min", type=float, default=HU_MIN,
        help=f"Borne inférieure du fenêtrage HU (défaut : {HU_MIN})",
    )
    parser.add_argument(
        "--hu-max", type=float, default=HU_MAX,
        help=f"Borne supérieure du fenêtrage HU (défaut : {HU_MAX})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.sorted_dir.exists():
        print(
            f"Erreur : dossier introuvable : {args.sorted_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    run(
        sorted_dir=args.sorted_dir,
        output_dir=args.output_dir,
        hu_min=args.hu_min,
        hu_max=args.hu_max,
    )