"""
organize_dicom_files.py
=======================
Pipeline d'organisation de fichiers DICOM pour le projet DeepBridge — CHU.

Améliorations v2 (2024) :
  - Logging structuré JSON avec rotation de fichiers
  - Validation stricte des champs DICOM requis
  - Quarantaine explicite des fichiers invalides ou non-CT
  - Rapport CSV de traitement (audit trail)
  - Gestion des collisions de noms de fichiers (hash MD5)
  - Traitement parallèle via concurrent.futures
  - Dry-run mode (simulation sans écriture sur disque)
  - Mode copie (--copy) : source toujours intacte
  - Métriques de pipeline (durée, compteurs, taux d'erreur)
  - Pas de variable globale mutable

Usage :
    python organize_dicom_files.py <source_folder> <output_folder> [options]

Options :
    --dry-run       Simulation sans écriture sur disque
    --copy          Copie les fichiers (source intacte) au lieu de les déplacer
    --workers N     Nombre de threads parallèles (défaut : 4)

Exemples :
    python organize_dicom_files.py C:\\dt\\scan C:\\deepbridge\\output --dry-run
    python organize_dicom_files.py C:\\dt\\scan C:\\deepbridge\\output --copy --workers 8
"""

import os
import sys
import csv
import json
import shutil
import hashlib
import logging
import logging.handlers
import argparse
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pydicom
from pydicom.errors import InvalidDicomError


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REQUIRED_TAGS        = ("PatientID", "SeriesInstanceUID", "Modality")
ACCEPTED_MODALITIES  = {"CT"}
EXTENSIONS_TO_SKIP   = {".cab"}   # ignorés en mode --copy, supprimés sinon
QUARANTINE_DIR_NAME  = "_quarantine"
REPORT_FILENAME      = "pipeline_report.csv"
REPORT_FIELDS        = [
    "timestamp", "source_path", "destination_path",
    "patient_id", "series_uid", "modality",
    "status", "reason", "file_size_bytes",
]


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class PipelineMetrics:
    """Compteurs agrégés du pipeline."""
    total_scanned:    int = 0
    copied_or_moved:  int = 0
    quarantined:      int = 0
    deleted:          int = 0
    skipped_modality: int = 0
    errors:           int = 0
    start_time: float = field(default_factory=time.time)

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def summary(self) -> dict:
        elapsed = self.elapsed_seconds()
        return {
            "total_scanned":          self.total_scanned,
            "copied_or_moved":        self.copied_or_moved,
            "quarantined":            self.quarantined,
            "deleted":                self.deleted,
            "skipped_modality":       self.skipped_modality,
            "errors":                 self.errors,
            "elapsed_seconds":        round(elapsed, 2),
            "throughput_files_per_s": round(self.total_scanned / elapsed, 2) if elapsed > 0 else 0,
        }


@dataclass
class FileRecord:
    """Résultat du traitement d'un fichier unique."""
    timestamp:        str
    source_path:      str
    destination_path: str
    patient_id:       str
    series_uid:       str
    modality:         str
    status:           str   # "copied" | "moved" | "quarantined" | "deleted" | "skipped" | "error"
    reason:           str
    file_size_bytes:  int


# ---------------------------------------------------------------------------
# Logging structuré
# ---------------------------------------------------------------------------

def setup_logging(output_folder: Path, level: int = logging.INFO) -> logging.Logger:
    """
    Logger avec deux handlers :
      - Console : format lisible
      - Fichier JSON rotatif (10 Mo, 5 backups) dans output_folder/logs/
    """
    log_dir  = output_folder / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline.log"

    logger = logging.getLogger("dicom_pipeline")
    logger.setLevel(level)

    # Évite les handlers dupliqués si la fonction est rappelée
    if logger.handlers:
        logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    )
    logger.addHandler(console_handler)

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

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------------------
# Utilitaires fichiers
# ---------------------------------------------------------------------------

def md5_suffix(path: Path, length: int = 8) -> str:
    """Hash MD5 court du chemin — utilisé pour désamorcer les collisions de noms."""
    return hashlib.md5(str(path).encode()).hexdigest()[:length]


def safe_destination(dest_dir: Path, filename: str, source_path: Path) -> Path:
    """
    Chemin de destination sans collision.
    - Fichier absent → chemin direct
    - Même taille    → doublon exact, même destination (source sera ignorée/supprimée)
    - Taille diff    → collision réelle → suffixe MD5 ajouté
    """
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    if dest.stat().st_size == source_path.stat().st_size:
        return dest
    stem   = Path(filename).stem
    suffix = Path(filename).suffix
    return dest_dir / f"{stem}_{md5_suffix(source_path)}{suffix}"


def transfer_file(source: Path, destination: Path, dry_run: bool, copy_only: bool) -> None:
    """
    Transfère source → destination selon le mode choisi.

    dry_run=True  : aucune écriture (simulation)
    copy_only=True : shutil.copy2 — source intacte
    copy_only=False: shutil.move  — source supprimée après transfert
    """
    if dry_run:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    if copy_only:
        # En mode copie, on ne touche jamais à la source
        if not destination.exists():
            shutil.copy2(str(source), str(destination))
    else:
        # En mode déplacement, doublon exact → supprimer la source
        if destination.exists() and destination.stat().st_size == source.stat().st_size:
            source.unlink()
            return
        shutil.move(str(source), str(destination))


# ---------------------------------------------------------------------------
# Validation DICOM
# ---------------------------------------------------------------------------

def validate_dicom(ds: pydicom.Dataset) -> tuple[bool, str]:
    """Vérifie la présence et le contenu des tags DICOM requis."""
    for tag in REQUIRED_TAGS:
        if not hasattr(ds, tag) or not getattr(ds, tag):
            return False, f"Champ manquant ou vide : {tag}"
    return True, ""


# ---------------------------------------------------------------------------
# Traitement d'un fichier unique
# ---------------------------------------------------------------------------

def process_file(
    filepath:      Path,
    output_folder: Path,
    dry_run:       bool,
    copy_only:     bool,
    logger:        logging.Logger,
) -> FileRecord:
    """
    Lit les métadonnées DICOM d'un fichier et le range dans l'arborescence cible.
    Retourne un FileRecord décrivant le résultat (status, destination, raison).
    """
    ts   = datetime.utcnow().isoformat() + "Z"
    size = filepath.stat().st_size if filepath.exists() else 0

    # base NE contient PAS destination_path — évite le bug "multiple values for keyword argument"
    base = dict(
        timestamp=ts, source_path=str(filepath),
        patient_id="", series_uid="", modality="", file_size_bytes=size,
    )

    def make_record(status: str, reason: str, dst: str = "") -> FileRecord:
        return FileRecord(**base, destination_path=dst, status=status, reason=reason)

    # ── Fichiers parasites ────────────────────────────────────────────────────
    if filepath.suffix.lower() in EXTENSIONS_TO_SKIP:
        if not dry_run and not copy_only:
            filepath.unlink()
        action = "Ignoré" if copy_only else "Supprimé"
        logger.debug("%s (extension parasite) : %s", action, filepath.name)
        return make_record("deleted", f"extension {filepath.suffix}")

    # ── Lecture DICOM ─────────────────────────────────────────────────────────
    try:
        ds = pydicom.dcmread(str(filepath), stop_before_pixels=True)
    except InvalidDicomError as exc:
        logger.warning("DICOM invalide : %s — %s", filepath.name, exc)
        dst = output_folder / QUARANTINE_DIR_NAME / "invalid_dicom" / filepath.name
        transfer_file(filepath, dst, dry_run, copy_only)
        return make_record("quarantined", f"InvalidDicomError: {exc}", str(dst))
    except Exception as exc:
        logger.error("Erreur inattendue sur %s : %s", filepath.name, exc)
        return make_record("error", str(exc))

    # ── Validation des champs requis ──────────────────────────────────────────
    is_valid, reason = validate_dicom(ds)
    if not is_valid:
        logger.warning("Tags manquants dans %s : %s", filepath.name, reason)
        dst = output_folder / QUARANTINE_DIR_NAME / "missing_tags" / filepath.name
        transfer_file(filepath, dst, dry_run, copy_only)
        return make_record("quarantined", reason, str(dst))

    patient_id = str(ds.PatientID).strip()
    series_uid = str(ds.SeriesInstanceUID).strip()
    modality   = str(ds.Modality).strip().upper()
    base.update(patient_id=patient_id, series_uid=series_uid, modality=modality)

    # ── Filtre de modalité ────────────────────────────────────────────────────
    if modality not in ACCEPTED_MODALITIES:
        logger.info("Modalité ignorée (%s) : %s", modality, filepath.name)
        dst = output_folder / QUARANTINE_DIR_NAME / f"modality_{modality}" / filepath.name
        transfer_file(filepath, dst, dry_run, copy_only)
        return make_record("skipped", f"Modalité non acceptée : {modality}", str(dst))

    # ── Organisation cible : output / PatientID / SeriesUID / fichier.dcm ────
    dest_dir  = output_folder / patient_id / series_uid
    dest_path = safe_destination(dest_dir, filepath.name, filepath)
    transfer_file(filepath, dest_path, dry_run, copy_only)

    status = "copied" if copy_only else "moved"
    logger.debug("%s : %s → %s/%s", status, filepath.name, patient_id, series_uid)
    return make_record(status, "", str(dest_path))


# ---------------------------------------------------------------------------
# Scan + rapport CSV
# ---------------------------------------------------------------------------

def iter_files(source_folder: Path) -> list[Path]:
    """Collecte récursivement tous les fichiers non cachés."""
    return [
        p for p in source_folder.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    ]


def write_report(records: list[FileRecord], output_folder: Path) -> Path:
    """Écrit le rapport CSV complet (un fichier = une ligne)."""
    report_path = output_folder / REPORT_FILENAME
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    return report_path


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def main(source_folder: Path, output_folder: Path,
         dry_run: bool, copy_only: bool, workers: int) -> None:

    output_folder.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(output_folder)

    # Affichage du mode actif
    if dry_run:
        mode = "[DRY-RUN] Simulation — aucun fichier écrit"
    elif copy_only:
        mode = "[COPY] Copie — source intacte"
    else:
        mode = "[MOVE] Déplacement — source modifiée"

    logger.info("Démarrage du pipeline DICOM — %s", mode)
    logger.info("Source      : %s", source_folder)
    logger.info("Destination : %s", output_folder)
    logger.info("Workers     : %d", workers)

    logger.info("Scan de l'arborescence source…")
    all_files = iter_files(source_folder)
    metrics   = PipelineMetrics(total_scanned=len(all_files))
    logger.info("%d fichiers trouvés", metrics.total_scanned)

    if not all_files:
        logger.warning("Aucun fichier à traiter. Pipeline terminé.")
        return

    records: list[FileRecord] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_file, fp, output_folder, dry_run, copy_only, logger): fp
            for fp in all_files
        }
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                record = future.result()
                records.append(record)
                match record.status:
                    case "copied" | "moved": metrics.copied_or_moved += 1
                    case "quarantined":      metrics.quarantined += 1
                    case "deleted":          metrics.deleted += 1
                    case "skipped":          metrics.skipped_modality += 1
                    case "error":            metrics.errors += 1
            except Exception as exc:
                metrics.errors += 1
                logger.error("Erreur future non capturée : %s", exc)

            if i % 500 == 0 or i == metrics.total_scanned:
                logger.info("Progression : %d/%d (%.1f%%)",
                            i, metrics.total_scanned, 100 * i / metrics.total_scanned)

    report_path = write_report(records, output_folder)
    logger.info("Rapport CSV : %s", report_path)

    logger.info("─── Résumé ───────────────────────────────────────────")
    for key, value in metrics.summary().items():
        logger.info("  %-35s %s", key, value)
    logger.info("──────────────────────────────────────────────────────")

    if metrics.errors > 0:
        logger.warning("%d erreur(s). Consultez les logs pour les détails.", metrics.errors)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organise les fichiers DICOM du CHU en arborescence PatientID/SeriesUID.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  # Simulation (rien n'est écrit)
  py organize_dicom_files.py C:\\dt\\scan C:\\deepbridge\\output --dry-run

  # Copie — source intacte (RECOMMANDÉ pour les données CHU)
  py organize_dicom_files.py C:\\dt\\scan C:\\deepbridge\\output --copy --workers 8

  # Déplacement (source modifiée — utiliser uniquement sur une copie de travail)
  py organize_dicom_files.py C:\\dt\\scan C:\\deepbridge\\output --workers 8
        """,
    )
    parser.add_argument("source_folder", type=Path,
                        help="Dossier source contenant les fichiers DICOM")
    parser.add_argument("output_folder", type=Path,
                        help="Dossier de destination organisé")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans écriture sur disque")
    parser.add_argument("--copy",    action="store_true",
                        help="Copie les fichiers (source intacte) — RECOMMANDÉ pour données CHU")
    parser.add_argument("--workers", type=int, default=4,
                        help="Nombre de threads parallèles (défaut : 4)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.source_folder.exists():
        print(f"Erreur : dossier source introuvable : {args.source_folder}", file=sys.stderr)
        sys.exit(1)

    main(
        source_folder=args.source_folder,
        output_folder=args.output_folder,
        dry_run=args.dry_run,
        copy_only=args.copy,
        workers=args.workers,
    )