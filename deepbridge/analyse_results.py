"""
analyse_results.py
==================
Analyse et validation de l'arborescence DICOM après organisation.

Usage :
    py analyse_results.py                                      # utilise OUTPUT_DIR (config.py)
    py analyse_results.py <sorted_folder>
    py analyse_results.py <source_folder> <sorted_folder>
    py analyse_results.py <source_folder> <sorted_folder> --export rapport.json
"""

import os
import json
import argparse
import logging
import sys
from pathlib import Path
from typing import Generator

import pydicom
from pydicom.errors import InvalidDicomError

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("analyse_results")


# ---------------------------------------------------------------------------
# Fonctions de collecte — pures, sans effet de bord
# ---------------------------------------------------------------------------

def count_direct_subdirs(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for e in path.iterdir() if e.is_dir() and not e.name.startswith("_"))


def count_dcm_recursive(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1 for _, _, files in os.walk(path)
        for f in files
        if f.endswith(".dcm") and not f.startswith(".")
    )


def count_all_subdirs(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(len(dirs) for _, dirs, _ in os.walk(path))


def scans_per_patient(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    if not path.exists():
        return result
    for patient_dir in path.iterdir():
        if patient_dir.is_dir() and not patient_dir.name.startswith("_"):
            result[patient_dir.name] = sum(1 for e in patient_dir.iterdir() if e.is_dir())
    return result


def dcm_per_series(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    if not path.exists():
        return result
    for patient_dir in path.iterdir():
        if not patient_dir.is_dir() or patient_dir.name.startswith("_"):
            continue
        for series_dir in patient_dir.iterdir():
            if not series_dir.is_dir():
                continue
            count = sum(1 for f in series_dir.iterdir() if f.is_file() and f.suffix == ".dcm" and not f.name.startswith("."))
            if count > 0:
                result[series_dir.name] = count
    return result


def iter_series_without_slice_location(path: Path) -> Generator[str, None, None]:
    """Générateur — mémoire constante quelle que soit la taille de l'arborescence."""
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        dcm_files = [f for f in files if f.endswith(".dcm") and not f.startswith(".")]
        if not dcm_files:
            continue

        has_slice = False
        for filename in dcm_files:
            try:
                ds = pydicom.dcmread(os.path.join(root, filename), stop_before_pixels=True)
                if "SliceLocation" in ds:
                    has_slice = True
                    break
            except (InvalidDicomError, Exception):
                pass

        if not has_slice:
            yield os.path.basename(root)


# ---------------------------------------------------------------------------
# Construction du rapport
# ---------------------------------------------------------------------------

def build_report(source_path: Optional[Path], sorted_path: Path) -> dict:
    report: dict = {"sorted": str(sorted_path)}

    if source_path and source_path.exists():
        logger.info("Analyse source : %s", source_path)
        nb_patients_before  = count_direct_subdirs(source_path)
        total_files_before  = count_dcm_recursive(source_path)
        total_subdirs_before = count_all_subdirs(source_path)
        report["source"] = str(source_path)
        report["avant_tri"] = {
            "nb_patients":      nb_patients_before,
            "nb_fichiers_dcm":  total_files_before,
            "nb_scans_estimes": max(0, total_subdirs_before - nb_patients_before),
        }

    logger.info("Analyse destination : %s", sorted_path)
    nb_patients_after   = count_direct_subdirs(sorted_path)
    total_files_after   = count_dcm_recursive(sorted_path)
    total_subdirs_after = count_all_subdirs(sorted_path)

    report["apres_tri"] = {
        "nb_patients":              nb_patients_after,
        "nb_fichiers_dcm":          total_files_after,
        "nb_scans":                 max(0, total_subdirs_after - nb_patients_after),
        "nb_fichiers_non_utilisables": (
            report["avant_tri"]["nb_fichiers_dcm"] - total_files_after
            if "avant_tri" in report else "N/A"
        ),
    }

    logger.info("Calcul scans par patient…")
    report["scans_par_patient"] = scans_per_patient(sorted_path)

    logger.info("Calcul fichiers par série…")
    report["fichiers_par_serie"] = dcm_per_series(sorted_path)

    logger.info("Recherche séries sans SliceLocation…")
    series_no_slice = list(iter_series_without_slice_location(sorted_path))
    report["series_sans_slice_location"]    = series_no_slice
    report["nb_series_sans_slice_location"] = len(series_no_slice)

    return report


# ---------------------------------------------------------------------------
# Affichage console
# ---------------------------------------------------------------------------

def print_report(report: dict) -> None:
    sep = "─" * 62
    print(f"\n{sep}")
    print("  RAPPORT D'ANALYSE DICOM — DeepBridge")
    print(sep)

    if "avant_tri" in report and "apres_tri" in report:
        av, ap = report["avant_tri"], report["apres_tri"]
        print(f"\n  {'MÉTRIQUE':<42} {'AVANT':>8}  {'APRÈS':>8}")
        print(f"  {'':─<60}")
        print(f"  {'Patients':<42} {av['nb_patients']:>8}  {ap['nb_patients']:>8}")
        print(f"  {'Fichiers DICOM (.dcm)':<42} {av['nb_fichiers_dcm']:>8}  {ap['nb_fichiers_dcm']:>8}")
        print(f"  {'Scans':<42} {av['nb_scans_estimes']:>8}  {ap['nb_scans']:>8}")
        print(f"  {'Fichiers non utilisables':<42} {'—':>8}  {ap['nb_fichiers_non_utilisables']:>8}")
        print(f"  {'':─<60}")
    else:
        ap = report["apres_tri"]
        print(f"\n  Patients : {ap['nb_patients']}")
        print(f"  Fichiers : {ap['nb_fichiers_dcm']}")
        print(f"  Scans    : {ap['nb_scans']}")

    print(f"\n  Scans par patient :")
    for patient, nb in sorted(report["scans_par_patient"].items()):
        print(f"    {patient:<52} {nb:>4} scan(s)")

    nb_no_slice = report["nb_series_sans_slice_location"]
    print(f"\n  Séries sans SliceLocation ({nb_no_slice}) :")
    if nb_no_slice == 0:
        print("    ✓ Toutes les séries ont un SliceLocation.")
    else:
        for serie in report["series_sans_slice_location"]:
            print(f"    ⚠  {serie}")

    print(f"\n{sep}\n")


def export_report(report: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Rapport JSON exporté : %s", path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyse de l'arborescence DICOM — DeepBridge")
    parser.add_argument("source_folder", nargs="?", type=Path, default=None,
                        help="Dossier source original (optionnel)")
    parser.add_argument("sorted_folder", nargs="?", type=Path, default=config.OUTPUT_DIR,
                        help=f"Dossier trié (défaut : {config.OUTPUT_DIR})")
    parser.add_argument("--export", type=Path, default=None, help="Export JSON du rapport")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.sorted_folder.exists():
        print(f"Erreur : dossier introuvable : {args.sorted_folder}", file=sys.stderr)
        sys.exit(1)

    report = build_report(args.source_folder, args.sorted_folder)
    print_report(report)

    if args.export:
        export_report(report, args.export)
