"""
validate_dataset.py
===================
Couche 1 — Ingestion | DeepBridge — CHU Nice 2020-2021

Validation clinique et technique des séries DICOM organisées par
organize_dicom_files.py. Chaque série est évaluée selon trois critères
médicalement fondés avant d'entrer dans le pipeline de prétraitement.

Critères de validation
----------------------
1. Nombre de coupes    — couverture anatomique minimale de l'aorte.
                         En dessous de MIN_SLICES, le volume est incomplet.

2. SliceLocation       — tag DICOM indiquant la position anatomique de chaque
                         coupe. Requis pour la reconstruction volumétrique 3D.

3. PixelSpacing        — résolution spatiale dans le plan axial (mm/pixel).
                         Au-delà de MAX_PIXEL_SPACING, la résolution est
                         insuffisante pour segmenter les structures aortiques.

Sorties
-------
- validation_report.csv  : statut (valid / rejected) de chaque série
- Logs JSON rotatifs      : trace d'exécution dans output/logs/

État de l'art par promotion
----------------------------
- Groupe 2022-2023 : détection des séries sans SliceLocation uniquement,
                     pas de rejet, pas de validation PixelSpacing ni nb_slices.
- Groupe 2023-2024 : aucune validation DICOM (code PIL/image générique).
- Groupe 2025-2026 : validation complète des 3 critères, rapport CSV structuré.

Usage
-----
    py validate_dataset.py
    py validate_dataset.py <sorted_dir>
    py validate_dataset.py <sorted_dir> --move-rejected
    py validate_dataset.py <sorted_dir> --report mon_rapport.csv --workers 8
"""

import csv
import json
import logging
import logging.handlers
import argparse
import shutil
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pydicom
from pydicom.errors import InvalidDicomError


# ---------------------------------------------------------------------------
# Configuration — seuils cliniques
# ---------------------------------------------------------------------------

# Nombre minimum de coupes pour qu'un volume soit exploitable.
# En dessous de ce seuil, l'aorte n'est pas couverte en entier.
MIN_SLICES = 50

# PixelSpacing maximum accepté (mm). Au-delà, la résolution spatiale est
# insuffisante pour segmenter les structures aortiques avec précision.
MAX_PIXEL_SPACING = 1.5

# Nombre de threads parallèles pour la lecture des métadonnées DICOM.
DEFAULT_WORKERS = 4

# Nom du rapport CSV produit.
REPORT_FILENAME = "validation_report.csv"

# Nom du dossier où sont déplacées les séries rejetées.
REJECTED_DIR_NAME = "_rejected"

# Champs du rapport CSV — un enregistrement par série.
REPORT_FIELDS = [
    "timestamp",
    "patient_id",
    "series_uid",
    "series_path",
    "nb_slices",
    "has_slice_location",
    "pixel_spacing",
    "pixel_spacing_ok",
    "status",
    "reason",
]


# ---------------------------------------------------------------------------
# Structure de données
# ---------------------------------------------------------------------------

@dataclass
class SeriesReport:
    """
    Résultat de la validation d'une série DICOM.
    Un enregistrement par série — directement sérialisable en CSV.
    """
    timestamp:          str
    patient_id:         str
    series_uid:         str
    series_path:        str
    nb_slices:          int
    has_slice_location: bool
    pixel_spacing:      str   # ex: "0.742x0.742" ou "N/A"
    pixel_spacing_ok:   bool
    status:             str   # "valid" | "rejected"
    reason:             str   # vide si valide


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(output_dir: Path) -> logging.Logger:
    """
    Configure un logger avec deux handlers :
      - Console : format lisible en temps réel
      - Fichier JSON rotatif (10 Mo x 5 backups) dans output_dir/logs/
    """
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("validate_dataset")
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
        log_dir / "validate.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Critères de validation — fonctions pures et testables unitairement
# ---------------------------------------------------------------------------

def check_slice_count(dcm_files: list) -> tuple:
    """
    Critère 1 — Nombre de coupes.

    Compte les fichiers .dcm dans le dossier de la série.
    Un volume avec moins de MIN_SLICES coupes ne couvre pas l'aorte
    en entier et ne peut pas être utilisé pour l'entraînement.

    Historique des promotions
    -------------------------
    - Groupe 2022-2023 : non réalisé.
    - Groupe 2023-2024 : non réalisé.
    - Groupe 2025-2026 : ajouté — seuil configurable via MIN_SLICES.

    Returns
    -------
    (ok: bool, nb_slices: int)
    """
    nb = len(dcm_files)
    return nb >= MIN_SLICES, nb


def check_slice_location(ds: pydicom.Dataset) -> bool:
    """
    Critère 2 — Présence du tag SliceLocation.

    SliceLocation indique la position de chaque coupe dans l'espace
    anatomique (en mm le long de l'axe z). Sans ce tag, il est impossible
    d'ordonner les coupes et de reconstruire un volume 3D cohérent.

    Historique des promotions
    -------------------------
    - Groupe 2022-2023 : détecté dans slice_location_search() mais sans
                         rejet — simple affichage console, aucune traçabilité.
    - Groupe 2023-2024 : non réalisé.
    - Groupe 2025-2026 : détection + rejet + raison dans le rapport CSV.

    Returns
    -------
    True si SliceLocation est présent et non nul, False sinon.
    """
    return hasattr(ds, "SliceLocation") and ds.SliceLocation is not None


def check_pixel_spacing(ds: pydicom.Dataset) -> tuple:
    """
    Critère 3 — PixelSpacing (résolution spatiale axiale).

    PixelSpacing = [row_spacing, col_spacing] en mm/pixel.
    Si l'un des deux axes dépasse MAX_PIXEL_SPACING (1.5 mm par défaut),
    la résolution est trop faible pour segmenter avec précision les
    structures aortiques, dont l'épaisseur de paroi est de l'ordre de
    1 à 2 mm.

    Historique des promotions
    -------------------------
    - Groupe 2022-2023 : non réalisé.
    - Groupe 2023-2024 : non réalisé.
    - Groupe 2025-2026 : ajouté — seuil configurable via MAX_PIXEL_SPACING.

    Returns
    -------
    (ok: bool, pixel_spacing_str: str)
    """
    if not hasattr(ds, "PixelSpacing") or ds.PixelSpacing is None:
        return False, "N/A"

    ps     = ds.PixelSpacing
    row_sp = float(ps[0])
    col_sp = float(ps[1])
    ps_str = f"{row_sp:.3f}x{col_sp:.3f}"
    ok     = row_sp <= MAX_PIXEL_SPACING and col_sp <= MAX_PIXEL_SPACING

    return ok, ps_str


# ---------------------------------------------------------------------------
# Validation d'une série complète
# ---------------------------------------------------------------------------

def validate_series(series_dir: Path) -> SeriesReport:
    """
    Valide une série DICOM complète en appliquant les trois critères
    dans l'ordre optimal — du moins coûteux (listdir) au plus coûteux
    (lecture DICOM) :

      1. Comptage des coupes     — listdir rapide
      2. Lecture des métadonnées — ouverture d'un seul fichier DICOM
      3. SliceLocation           — vérification du tag sur le dataset
      4. PixelSpacing            — vérification de la résolution spatiale

    En cas d'échec d'un critère, la fonction retourne immédiatement
    sans exécuter les critères suivants (early return pattern).

    Parameters
    ----------
    series_dir : Path
        Dossier de la série.
        Structure attendue : output / patient_id / series_uid / *.dcm

    Returns
    -------
    SeriesReport : résultat complet de la validation
    """
    ts         = datetime.utcnow().isoformat() + "Z"
    patient_id = series_dir.parent.name
    series_uid = series_dir.name

    def make_report(status, reason, nb=0, has_sl=False,
                    ps_ok=False, ps_str="N/A"):
        return SeriesReport(
            timestamp=ts,
            patient_id=patient_id,
            series_uid=series_uid,
            series_path=str(series_dir),
            nb_slices=nb,
            has_slice_location=has_sl,
            pixel_spacing=ps_str,
            pixel_spacing_ok=ps_ok,
            status=status,
            reason=reason,
        )

    # Collecter les fichiers .dcm du dossier de la série
    dcm_files = sorted(
        f for f in series_dir.iterdir()
        if f.is_file() and f.suffix == ".dcm" and not f.name.startswith(".")
    )

    # ── Critère 1 : nombre de coupes ──────────────────────────────────────
    slices_ok, nb_slices = check_slice_count(dcm_files)

    if nb_slices == 0:
        return make_report("rejected", "Aucun fichier .dcm dans le dossier")

    if not slices_ok:
        return make_report(
            "rejected",
            f"Nombre de coupes insuffisant : {nb_slices} < {MIN_SLICES}",
            nb=nb_slices,
        )

    # ── Lecture du premier fichier .dcm pour les métadonnées ──────────────
    try:
        ds = pydicom.dcmread(str(dcm_files[0]), stop_before_pixels=True)
    except InvalidDicomError as exc:
        return make_report(
            "rejected",
            f"Fichier DICOM invalide : {exc}",
            nb=nb_slices,
        )
    except Exception as exc:
        return make_report(
            "rejected",
            f"Erreur de lecture : {exc}",
            nb=nb_slices,
        )

    # ── Critère 2 : SliceLocation ─────────────────────────────────────────
    has_slice_loc = check_slice_location(ds)
    if not has_slice_loc:
        return make_report(
            "rejected",
            "Tag SliceLocation absent — reconstruction volumétrique 3D impossible",
            nb=nb_slices,
            has_sl=False,
        )

    # ── Critère 3 : PixelSpacing ──────────────────────────────────────────
    ps_ok, ps_str = check_pixel_spacing(ds)
    if not ps_ok:
        return make_report(
            "rejected",
            f"PixelSpacing hors seuil : {ps_str} mm (max autorisé : {MAX_PIXEL_SPACING} mm)",
            nb=nb_slices,
            has_sl=True,
            ps_ok=False,
            ps_str=ps_str,
        )

    # ── Série valide — les 3 critères sont satisfaits ─────────────────────
    return make_report(
        "valid", "",
        nb=nb_slices, has_sl=True, ps_ok=True, ps_str=ps_str,
    )


# ---------------------------------------------------------------------------
# Collecte des séries à valider
# ---------------------------------------------------------------------------

def collect_series(sorted_dir: Path) -> list:
    """
    Parcourt l'arborescence organisée et retourne la liste des dossiers
    de séries à valider.

    Les dossiers commençant par '_' (quarantaine, logs) sont exclus.

    Structure attendue
    ------------------
    sorted_dir/
    ├── PatientID_1/
    │   ├── SeriesUID_A/   ← dossier de série
    │   └── SeriesUID_B/
    ├── PatientID_2/
    │   └── SeriesUID_C/
    └── _quarantine/       ← exclu
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
# Rapport CSV et résumé console
# ---------------------------------------------------------------------------

def write_report(reports: list, report_path: Path) -> None:
    """
    Écrit le rapport de validation au format CSV.
    Les séries rejetées apparaissent en premier pour faciliter la lecture.
    """
    sorted_reports = sorted(reports, key=lambda r: (r.status, r.patient_id))

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for r in sorted_reports:
            writer.writerow(asdict(r))


def move_rejected_series(reports: list, sorted_dir: Path, logger: logging.Logger) -> int:
    """
    Déplace les séries rejetées hors de l'arborescence valide.

    Les séries rejetées sont déplacées dans :
        sorted_dir / _rejected / patient_id / series_uid /

    Cela permet de travailler dans sorted_dir avec uniquement les séries
    valides, sans supprimer les données rejetées définitivement.

    Les données originales dans C:\\deepbridge\\data\\ restent intactes.

    Parameters
    ----------
    reports    : résultats complets de la validation
    sorted_dir : arborescence organisée
    logger     : logger actif

    Returns
    -------
    int : nombre de séries effectivement déplacées
    """
    rejected = [r for r in reports if r.status == "rejected"]
    rejected_root = sorted_dir / REJECTED_DIR_NAME
    moved = 0

    for report in rejected:
        series_path = Path(report.series_path)

        if not series_path.exists():
            logger.warning("Série introuvable, ignorée : %s", series_path)
            continue

        # Destination : _rejected / patient_id / series_uid /
        dest = rejected_root / report.patient_id / report.series_uid

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(series_path), str(dest))
            moved += 1
            logger.debug("Déplacée : %s/%s → _rejected/",
                         report.patient_id, report.series_uid[:24])
        except Exception as exc:
            logger.error("Erreur déplacement %s : %s", series_path, exc)

        # Supprimer le dossier patient s'il est désormais vide
        patient_dir = series_path.parent
        try:
            if patient_dir.exists() and not any(patient_dir.iterdir()):
                patient_dir.rmdir()
        except Exception:
            pass

    logger.info("%d série(s) rejetée(s) déplacées dans %s/",
                moved, REJECTED_DIR_NAME)
    return moved


def print_summary(reports: list, logger: logging.Logger) -> None:
    """Affiche le résumé structuré dans la console et les logs."""
    valid    = [r for r in reports if r.status == "valid"]
    rejected = [r for r in reports if r.status == "rejected"]

    rej_slices    = [r for r in rejected if "coupes" in r.reason]
    rej_slice_loc = [r for r in rejected if "SliceLocation" in r.reason]
    rej_spacing   = [r for r in rejected if "PixelSpacing" in r.reason]
    rej_other     = [r for r in rejected
                     if r not in rej_slices + rej_slice_loc + rej_spacing]

    total = len(reports)
    pct   = lambda n: f"{100 * n / total:.1f}%" if total > 0 else "0%"

    logger.info("─── Résumé validation ─────────────────────────────────────")
    logger.info("  Séries analysées              : %d", total)
    logger.info("  Séries valides                : %d (%s)", len(valid), pct(len(valid)))
    logger.info("  Séries rejetées               : %d (%s)", len(rejected), pct(len(rejected)))
    logger.info("    dont coupes < %d             : %d", MIN_SLICES, len(rej_slices))
    logger.info("    dont SliceLocation absente   : %d", len(rej_slice_loc))
    logger.info("    dont PixelSpacing hors seuil : %d", len(rej_spacing))
    logger.info("    dont autres erreurs          : %d", len(rej_other))
    logger.info("───────────────────────────────────────────────────────────")


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(
    sorted_dir:    Path,
    report_path:   Optional[Path] = None,
    workers:       int = DEFAULT_WORKERS,
    move_rejected: bool = False,
) -> list:
    """
    Orchestre la validation de toutes les séries en parallèle.

    Parameters
    ----------
    sorted_dir    : arborescence produite par organize_dicom_files.py
    report_path   : chemin du CSV de sortie
    workers       : nombre de threads parallèles
    move_rejected : si True, déplace les séries rejetées dans _rejected/

    Returns
    -------
    list[SeriesReport] : résultats complets de la validation
    """
    logger = setup_logging(sorted_dir)
    t0     = time.time()

    logger.info("Démarrage de la validation — %s", sorted_dir)
    logger.info("Seuils appliqués : MIN_SLICES=%d | MAX_PIXEL_SPACING=%.1f mm",
                MIN_SLICES, MAX_PIXEL_SPACING)
    logger.info("Workers : %d", workers)

    series_dirs = collect_series(sorted_dir)
    total       = len(series_dirs)
    logger.info("%d série(s) à valider", total)

    if total == 0:
        logger.warning("Aucune série trouvée. Vérifiez le dossier source.")
        return []

    reports = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(validate_series, sd): sd
            for sd in series_dirs
        }
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                report = future.result()
                reports.append(report)
                icon = "OK" if report.status == "valid" else "KO"
                logger.debug("[%s] %s/%s — %s",
                             icon, report.patient_id,
                             report.series_uid[:24],
                             report.reason or "valide")
            except Exception as exc:
                logger.error("Erreur inattendue : %s", exc)

            if i % 50 == 0 or i == total:
                logger.info("Progression : %d/%d (%.1f%%)",
                            i, total, 100 * i / total)

    print_summary(reports, logger)

    # Déplacement des séries rejetées si demandé
    if move_rejected:
        move_rejected_series(reports, sorted_dir, logger)

    out = report_path or sorted_dir / REPORT_FILENAME
    write_report(reports, out)
    logger.info("Rapport CSV : %s", out)
    logger.info("Durée totale : %.2f secondes", time.time() - t0)

    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valide les séries DICOM organisées — DeepBridge / CHU Nice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Critères de validation appliqués :
  1. Nombre de coupes    >= {MIN_SLICES}
  2. SliceLocation       present dans les metadonnees DICOM
  3. PixelSpacing        <= {MAX_PIXEL_SPACING} mm sur les deux axes

Exemples :
  py validate_dataset.py
  py validate_dataset.py C:\\deepbridge\\output
  py validate_dataset.py C:\\deepbridge\\output --report rapport.csv
  py validate_dataset.py C:\\deepbridge\\output --workers 8
        """,
    )
    parser.add_argument(
        "sorted_dir", nargs="?", type=Path,
        default=Path("output"),
        help="Dossier organisé produit par organize_dicom_files.py (défaut : output/)",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="Chemin du rapport CSV (défaut : <sorted_dir>/validation_report.csv)",
    )
    parser.add_argument(
        "--move-rejected", action="store_true",
        help="Déplace les séries rejetées dans _rejected/ (source valide isolée)",
    )
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"Threads parallèles (défaut : {DEFAULT_WORKERS})",
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
        report_path=args.report,
        workers=args.workers,
        move_rejected=args.move_rejected,
    )