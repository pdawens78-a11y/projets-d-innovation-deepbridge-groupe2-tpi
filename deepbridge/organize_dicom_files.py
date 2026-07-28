"""
organize_dicom_files.py
=======================
Pipeline principal d'organisation des fichiers DICOM — DeepBridge / CHU.

Usage :
    py organize_dicom_files.py                          # utilise DATA_DIR → OUTPUT_DIR (config.py)
    py organize_dicom_files.py <source> <output>        # chemins personnalisés
    py organize_dicom_files.py <source> <output> --dry-run
    py organize_dicom_files.py <source> <output> --workers 8
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

import config


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class PipelineMetrics:
    total_scanned: int = 0
    moved: int = 0
    quarantined: int = 0
    deleted: int = 0
    skipped_modality: int = 0
    errors: int = 0
    start_time: float = field(default_factory=time.time)

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def summary(self) -> dict:
        elapsed = self.elapsed()
        return {
            "total_scanned":          self.total_scanned,
            "moved":                  self.moved,
            "quarantined":            self.quarantined,
            "deleted":                self.deleted,
            "skipped_modality":       self.skipped_modality,
            "errors":                 self.errors,
            "elapsed_seconds":        round(elapsed, 2),
            "throughput_files_per_s": round(self.total_scanned / elapsed, 2) if elapsed > 0 else 0,
        }


@dataclass
class FileRecord:
    timestamp: str
    source_path: str
    destination_path: str
    patient_id: str
    series_uid: str
    modality: str
    status: str
    reason: str
    file_size_bytes: int


# ---------------------------------------------------------------------------
# Logging structuré
# ---------------------------------------------------------------------------

def setup_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "pipeline.log"

    logger = logging.getLogger("dicom_pipeline")
    logger.setLevel(getattr(logging, config.LOG_LEVEL))

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(console)

    # Fichier JSON rotatif
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
        log_path,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def md5_suffix(path: Path, length: int = 8) -> str:
    return hashlib.md5(str(path).encode()).hexdigest()[:length]


def safe_destination(dest_dir: Path, filename: str, source: Path) -> Path:
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    if dest.stat().st_size == source.stat().st_size:
        return dest  # doublon exact
    stem, suffix = Path(filename).stem, Path(filename).suffix
    return dest_dir / f"{stem}_{md5_suffix(source)}{suffix}"


def move_or_copy(source: Path, destination: Path, dry_run: bool) -> None:
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == source.stat().st_size:
        source.unlink()
        return
    shutil.move(str(source), str(destination))


# ---------------------------------------------------------------------------
# Validation DICOM
# ---------------------------------------------------------------------------

def validate_dicom(ds: pydicom.Dataset) -> tuple[bool, str]:
    for tag in config.REQUIRED_TAGS:
        if not hasattr(ds, tag) or not getattr(ds, tag):
            return False, f"Champ manquant ou vide : {tag}"
    return True, ""


# ---------------------------------------------------------------------------
# Traitement d'un fichier
# ---------------------------------------------------------------------------

def process_file(filepath: Path, output_folder: Path, dry_run: bool, logger: logging.Logger) -> FileRecord:
    ts   = datetime.utcnow().isoformat() + "Z"
    size = filepath.stat().st_size if filepath.exists() else 0

    base = dict(
        timestamp=ts, source_path=str(filepath), destination_path="",
        patient_id="", series_uid="", modality="", file_size_bytes=size,
    )

    # Fichiers parasites connus
    if filepath.suffix.lower() in config.EXTENSIONS_TO_DELETE:
        if not dry_run:
            filepath.unlink()
        logger.debug("Supprimé (parasite) : %s", filepath.name)
        return FileRecord(**base, status="deleted", reason=f"extension {filepath.suffix}")

    # Lecture DICOM
    try:
        ds = pydicom.dcmread(str(filepath), stop_before_pixels=True)
    except InvalidDicomError as exc:
        logger.warning("DICOM invalide : %s", filepath.name)
        dest = config.QUARANTINE_DIR / "invalid_dicom" / filepath.name
        move_or_copy(filepath, dest, dry_run)
        return FileRecord(**base, destination_path=str(dest), status="quarantined", reason=str(exc))
    except Exception as exc:
        logger.error("Erreur inattendue : %s — %s", filepath.name, exc)
        return FileRecord(**base, status="error", reason=str(exc))

    # Validation des champs
    valid, reason = validate_dicom(ds)
    if not valid:
        dest = config.QUARANTINE_DIR / "missing_tags" / filepath.name
        move_or_copy(filepath, dest, dry_run)
        return FileRecord(**base, destination_path=str(dest), status="quarantined", reason=reason)

    patient_id = str(ds.PatientID).strip()
    series_uid = str(ds.SeriesInstanceUID).strip()
    modality   = str(ds.Modality).strip().upper()
    base.update(patient_id=patient_id, series_uid=series_uid, modality=modality)

    # Filtre modalité
    if modality not in config.ACCEPTED_MODALITIES:
        dest = config.QUARANTINE_DIR / f"modality_{modality}" / filepath.name
        move_or_copy(filepath, dest, dry_run)
        return FileRecord(**base, destination_path=str(dest), status="skipped", reason=f"Modalité : {modality}")

    # Organisation finale : output / PatientID / SeriesUID / fichier.dcm
    dest_dir  = output_folder / patient_id / series_uid
    dest_path = safe_destination(dest_dir, filepath.name, filepath)
    move_or_copy(filepath, dest_path, dry_run)

    logger.debug("Déplacé : %s → %s/%s", filepath.name, patient_id, series_uid)
    return FileRecord(**base, destination_path=str(dest_path), status="moved", reason="")


# ---------------------------------------------------------------------------
# Scan source + rapport CSV
# ---------------------------------------------------------------------------

def iter_files(source: Path) -> list[Path]:
    return [p for p in source.rglob("*") if p.is_file() and not p.name.startswith(".")]


def write_report(records: list[FileRecord], output_folder: Path) -> Path:
    path = output_folder / config.REPORT_FILENAME
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=config.REPORT_FIELDS)
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))
    return path


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def main(source_folder: Path, output_folder: Path, dry_run: bool, workers: int) -> None:
    output_folder.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(config.LOGS_DIR)

    label = "[DRY-RUN] " if dry_run else ""
    logger.info("%sDémarrage du pipeline DeepBridge", label)
    logger.info("Source      : %s", source_folder)
    logger.info("Destination : %s", output_folder)
    logger.info("Workers     : %d", workers)

    all_files = iter_files(source_folder)
    metrics   = PipelineMetrics(total_scanned=len(all_files))
    logger.info("%d fichiers trouvés", metrics.total_scanned)

    if not all_files:
        logger.warning("Aucun fichier à traiter.")
        return

    records: list[FileRecord] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, fp, output_folder, dry_run, logger): fp for fp in all_files}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
                records.append(record)
                match record.status:
                    case "moved":       metrics.moved += 1
                    case "quarantined": metrics.quarantined += 1
                    case "deleted":     metrics.deleted += 1
                    case "skipped":     metrics.skipped_modality += 1
                    case "error":       metrics.errors += 1
            except Exception as exc:
                metrics.errors += 1
                logger.error("Erreur future : %s", exc)

            if i % 500 == 0 or i == metrics.total_scanned:
                logger.info("Progression : %d/%d (%.1f%%)", i, metrics.total_scanned, 100 * i / metrics.total_scanned)

    if not dry_run:
        report_path = write_report(records, output_folder)
        logger.info("Rapport CSV : %s", report_path)

    summary = metrics.summary()
    logger.info("─── Résumé ──────────────────────────────────────────")
    for k, v in summary.items():
        logger.info("  %-35s %s", k, v)
    logger.info("─────────────────────────────────────────────────────")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline d'organisation DICOM — DeepBridge")
    parser.add_argument("source_folder", nargs="?", type=Path, default=config.DATA_DIR,
                        help=f"Dossier source (défaut : {config.DATA_DIR})")
    parser.add_argument("output_folder", nargs="?", type=Path, default=config.OUTPUT_DIR,
                        help=f"Dossier de sortie (défaut : {config.OUTPUT_DIR})")
    parser.add_argument("--dry-run",  action="store_true", help="Simulation sans déplacement de fichiers")
    parser.add_argument("--workers",  type=int, default=config.DEFAULT_WORKERS, help="Threads parallèles")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.source_folder.exists():
        print(f"Erreur : dossier source introuvable : {args.source_folder}", file=sys.stderr)
        sys.exit(1)
    main(args.source_folder, args.output_folder, args.dry_run, args.workers)
