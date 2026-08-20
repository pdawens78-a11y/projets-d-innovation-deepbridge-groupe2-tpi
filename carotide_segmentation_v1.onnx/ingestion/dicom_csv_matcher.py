"""
dicom_csv_matcher.py
====================
Couche 1 — Ingestion | DeepBridge — CHU Nice 2020-2021

Appariement entre les séries DICOM validées et les données cliniques
du fichier BaseCarotideAnonymisée.xlsx fourni par le CHU.

Clé de jointure
---------------
La colonne CODES du fichier Excel contient les noms des dossiers DICOM
(ex: SF103E8_10.241.3.232_20210118173900817_CT). La correspondance est
effectuée de façon insensible à la casse (majuscules = minuscules).

Gestion contraignante des cas non appariés
------------------------------------------
Le script ne plante jamais en cas de discordance. Il produit trois fichiers :

  matched.csv            — séries DICOM avec données cliniques correspondantes
  unmatched_dicom.csv    — séries DICOM sans entrée clinique dans le Excel
  unmatched_clinical.csv — entrées cliniques sans série DICOM correspondante

Normalisation de la clé de jointure
-------------------------------------
Certains noms de dossiers DICOM ont un suffixe _SR (Structured Report) absent
dans le Excel. La normalisation supprime ces suffixes avant la jointure.

État de l'art par promotion
----------------------------
- Groupe 2022-2023 : non réalisé.
- Groupe 2023-2024 : non réalisé.
- Groupe 2025-2026 : réalisé — jointure robuste, insensible à la casse,
                     avec gestion explicite des trois cas d'appariement.

Usage
-----
    py dicom_csv_matcher.py
    py dicom_csv_matcher.py <sorted_dir> <clinical_xlsx>
    py dicom_csv_matcher.py <sorted_dir> <clinical_xlsx> --output-dir <dir>
"""

import csv
import json
import logging
import logging.handlers
import argparse
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Chemin par défaut du fichier Excel clinique
DEFAULT_CLINICAL_XLSX = Path(
    r"C:\dt\dataset_chu_nice_2020_2021\BaseCarotideAnonymisée.xlsx"
)

# Chemin par défaut du dossier DICOM organisé et validé
DEFAULT_SORTED_DIR = Path(r"C:\deepbridge\output")

# Nom de la colonne de jointure dans le Excel clinique
CLINICAL_KEY_COLUMN = "CODES"

# Noms des fichiers de sortie
MATCHED_FILENAME            = "matched.csv"
UNMATCHED_DICOM_FILENAME    = "unmatched_dicom.csv"
UNMATCHED_CLINICAL_FILENAME = "unmatched_clinical.csv"
MATCH_REPORT_FILENAME       = "match_report.json"

# Suffixes à supprimer du nom de dossier DICOM avant la jointure
# ex: SF103E8_..._CT_SR → SF103E8_..._CT
SUFFIXES_TO_STRIP = ["_SR", "_sr"]


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

    logger = logging.getLogger("dicom_csv_matcher")
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
        log_dir / "matcher.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Normalisation de la clé de jointure
# ---------------------------------------------------------------------------

def normalize_key(name: str) -> str:
    """
    Normalise un identifiant DICOM ou clinique pour la jointure.

    Transformations appliquées :
      1. Conversion en minuscules (insensible à la casse)
      2. Suppression des suffixes parasites (_SR, _sr)
      3. Suppression des espaces en début et fin

    Exemples
    --------
    >>> normalize_key("SF103E8_10.241.3.232_20210118173900817_CT_SR")
    "sf103e8_10.241.3.232_20210118173900817_ct"

    >>> normalize_key("sf103e9_10.241.3.233_20210119124708117_CT")
    "sf103e9_10.241.3.233_20210119124708117_ct"
    """
    key = str(name).strip().lower()
    for suffix in SUFFIXES_TO_STRIP:
        if key.endswith(suffix.lower()):
            key = key[: -len(suffix)]
    return key


# ---------------------------------------------------------------------------
# Indexation de l'arborescence DICOM
# ---------------------------------------------------------------------------

def index_dicom_series(sorted_dir: Path, logger: logging.Logger) -> pd.DataFrame:
    """
    Parcourt l'arborescence validée et construit un DataFrame indexé
    par clé de jointure normalisée.

    Structure attendue
    ------------------
    sorted_dir / patient_folder / series_folder /

    Le nom du dossier racine (patient_folder) correspond à la valeur
    de la colonne CODES dans le Excel clinique.

    Colonnes produites
    ------------------
    dicom_key        : clé normalisée (minuscules, sans suffixe _SR)
    dicom_folder     : nom exact du dossier dans l'arborescence
    dicom_path       : chemin absolu vers le dossier de la série
    nb_series        : nombre de séries pour ce dossier patient
    """
    rows = []

    for patient_dir in sorted(sorted_dir.iterdir()):
        if not patient_dir.is_dir() or patient_dir.name.startswith("_"):
            continue

        series_dirs = [
            s for s in patient_dir.iterdir()
            if s.is_dir()
        ]
        nb_series = len(series_dirs)

        rows.append({
            "dicom_key":    normalize_key(patient_dir.name),
            "dicom_folder": patient_dir.name,
            "dicom_path":   str(patient_dir),
            "nb_series":    nb_series,
        })

    df = pd.DataFrame(rows)
    logger.info("%d dossiers patients DICOM indexes", len(df))
    return df


# ---------------------------------------------------------------------------
# Chargement du fichier clinique Excel
# ---------------------------------------------------------------------------

def load_clinical_data(xlsx_path: Path, logger: logging.Logger) -> pd.DataFrame:
    """
    Charge le fichier BaseCarotideAnonymisée.xlsx et prépare la clé
    de jointure normalisée.

    La feuille active (première feuille) est utilisée. Les lignes dont
    la colonne CODES est vide sont exclues.

    Parameters
    ----------
    xlsx_path : chemin vers le fichier Excel du CHU

    Returns
    -------
    DataFrame avec une colonne supplémentaire 'clinical_key' normalisée.
    """
    if not xlsx_path.exists():
        raise FileNotFoundError(
            f"Fichier clinique introuvable : {xlsx_path}\n"
            f"Vérifiez le chemin ou utilisez --clinical pour spécifier "
            f"le chemin correct."
        )

    logger.info("Chargement du fichier clinique : %s", xlsx_path.name)

    try:
        df = pd.read_excel(xlsx_path, dtype=str)
    except Exception as exc:
        raise RuntimeError(f"Impossible de lire le fichier Excel : {exc}")

    if CLINICAL_KEY_COLUMN not in df.columns:
        raise ValueError(
            f"Colonne '{CLINICAL_KEY_COLUMN}' introuvable dans le fichier Excel.\n"
            f"Colonnes disponibles : {list(df.columns)}"
        )

    # Supprimer les lignes sans code DICOM
    before = len(df)
    df = df[df[CLINICAL_KEY_COLUMN].notna() & (df[CLINICAL_KEY_COLUMN].str.strip() != "")]
    after = len(df)

    if before - after > 0:
        logger.warning(
            "%d ligne(s) ignorée(s) — colonne CODES vide", before - after
        )

    # Ajouter la clé normalisée
    df["clinical_key"] = df[CLINICAL_KEY_COLUMN].apply(normalize_key)

    logger.info("%d entrées cliniques chargées", len(df))
    return df


# ---------------------------------------------------------------------------
# Appariement
# ---------------------------------------------------------------------------

def match(
    dicom_df:    pd.DataFrame,
    clinical_df: pd.DataFrame,
    logger:      logging.Logger,
) -> tuple:
    """
    Effectue la jointure entre l'index DICOM et les données cliniques.

    La jointure est réalisée sur les clés normalisées (minuscules, sans
    suffixe _SR) pour garantir une correspondance insensible à la casse.

    Trois groupes sont produits :
      - matched            : DICOM + clinique (inner join)
      - unmatched_dicom    : DICOM sans entrée clinique (left anti-join)
      - unmatched_clinical : clinique sans DICOM (right anti-join)

    Parameters
    ----------
    dicom_df    : DataFrame de l'index DICOM
    clinical_df : DataFrame des données cliniques

    Returns
    -------
    (matched_df, unmatched_dicom_df, unmatched_clinical_df)
    """
    # Jointure principale (inner join sur les clés normalisées)
    matched = pd.merge(
        dicom_df,
        clinical_df,
        left_on="dicom_key",
        right_on="clinical_key",
        how="inner",
    )

    # DICOM sans correspondance clinique
    dicom_keys_matched = set(matched["dicom_key"])
    unmatched_dicom = dicom_df[
        ~dicom_df["dicom_key"].isin(dicom_keys_matched)
    ].copy()

    # Clinique sans correspondance DICOM
    clinical_keys_matched = set(matched["clinical_key"])
    unmatched_clinical = clinical_df[
        ~clinical_df["clinical_key"].isin(clinical_keys_matched)
    ].copy()

    logger.info("Apparies (DICOM + clinique)   : %d", len(matched))
    logger.info("DICOM sans clinique           : %d", len(unmatched_dicom))
    logger.info("Clinique sans DICOM           : %d", len(unmatched_clinical))

    return matched, unmatched_dicom, unmatched_clinical


# ---------------------------------------------------------------------------
# Écriture des sorties
# ---------------------------------------------------------------------------

def write_outputs(
    matched:             pd.DataFrame,
    unmatched_dicom:     pd.DataFrame,
    unmatched_clinical:  pd.DataFrame,
    output_dir:          Path,
    logger:              logging.Logger,
) -> dict:
    """
    Écrit les trois fichiers CSV de sortie et le rapport JSON de synthèse.

    Parameters
    ----------
    matched, unmatched_dicom, unmatched_clinical : DataFrames issus de match()
    output_dir : dossier de sortie

    Returns
    -------
    dict : chemins des fichiers produits
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    # matched.csv
    p_matched = output_dir / MATCHED_FILENAME
    matched.to_csv(p_matched, index=False, encoding="utf-8")
    paths["matched"] = str(p_matched)
    logger.info("matched.csv            : %s", p_matched)

    # unmatched_dicom.csv
    p_ud = output_dir / UNMATCHED_DICOM_FILENAME
    unmatched_dicom.to_csv(p_ud, index=False, encoding="utf-8")
    paths["unmatched_dicom"] = str(p_ud)
    logger.info("unmatched_dicom.csv    : %s", p_ud)

    # unmatched_clinical.csv
    p_uc = output_dir / UNMATCHED_CLINICAL_FILENAME
    unmatched_clinical.to_csv(p_uc, index=False, encoding="utf-8")
    paths["unmatched_clinical"] = str(p_uc)
    logger.info("unmatched_clinical.csv : %s", p_uc)

    # Rapport JSON de synthèse
    report = {
        "timestamp":              datetime.utcnow().isoformat() + "Z",
        "nb_matched":             len(matched),
        "nb_unmatched_dicom":     len(unmatched_dicom),
        "nb_unmatched_clinical":  len(unmatched_clinical),
        "unmatched_dicom_folders":    unmatched_dicom["dicom_folder"].tolist()
                                      if not unmatched_dicom.empty else [],
        "unmatched_clinical_codes":   unmatched_clinical[CLINICAL_KEY_COLUMN].tolist()
                                      if not unmatched_clinical.empty else [],
        "output_files": paths,
    }

    p_report = output_dir / MATCH_REPORT_FILENAME
    with open(p_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    paths["report"] = str(p_report)
    logger.info("match_report.json      : %s", p_report)

    return paths


# ---------------------------------------------------------------------------
# Résumé console
# ---------------------------------------------------------------------------

def print_summary(
    matched:            pd.DataFrame,
    unmatched_dicom:    pd.DataFrame,
    unmatched_clinical: pd.DataFrame,
    logger:             logging.Logger,
) -> None:
    """Affiche le résumé structuré dans la console."""
    total_dicom    = len(matched) + len(unmatched_dicom)
    total_clinical = len(matched) + len(unmatched_clinical)

    logger.info("─── Résumé appariement ────────────────────────────────────")
    logger.info("  Dossiers DICOM analyses       : %d", total_dicom)
    logger.info("  Entrees cliniques analysees   : %d", total_clinical)
    logger.info("  Apparies (matched)            : %d (%.1f%%)",
                len(matched),
                100 * len(matched) / total_dicom if total_dicom > 0 else 0)
    logger.info("  DICOM sans clinique           : %d", len(unmatched_dicom))
    logger.info("  Clinique sans DICOM           : %d", len(unmatched_clinical))

    if not unmatched_dicom.empty:
        logger.warning("Dossiers DICOM sans correspondance clinique :")
        for folder in unmatched_dicom["dicom_folder"].tolist():
            logger.warning("  → %s", folder)

    if not unmatched_clinical.empty:
        logger.warning("Entrees cliniques sans DICOM correspondant :")
        for code in unmatched_clinical[CLINICAL_KEY_COLUMN].tolist():
            logger.warning("  → %s", code)

    logger.info("───────────────────────────────────────────────────────────")


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(
    sorted_dir:   Path,
    clinical_xlsx: Path,
    output_dir:   Optional[Path] = None,
) -> dict:
    """
    Orchestre l'appariement complet DICOM ↔ données cliniques.

    Parameters
    ----------
    sorted_dir    : arborescence validée produite par validate_dataset.py
    clinical_xlsx : fichier BaseCarotideAnonymisée.xlsx du CHU
    output_dir    : dossier de sortie (défaut : sorted_dir)

    Returns
    -------
    dict : chemins des fichiers produits
    """
    out = output_dir or sorted_dir
    logger = setup_logging(out)
    t0     = time.time()

    logger.info("Démarrage de l'appariement DICOM ↔ clinique")
    logger.info("DICOM      : %s", sorted_dir)
    logger.info("Clinique   : %s", clinical_xlsx)
    logger.info("Sortie     : %s", out)

    # Étape 1 — Indexer les dossiers DICOM
    dicom_df = index_dicom_series(sorted_dir, logger)

    if dicom_df.empty:
        logger.error(
            "Aucun dossier patient trouvé dans %s. "
            "Vérifiez que validate_dataset.py a été exécuté.", sorted_dir
        )
        sys.exit(1)

    # Étape 2 — Charger les données cliniques
    clinical_df = load_clinical_data(clinical_xlsx, logger)

    # Étape 3 — Apparier
    matched, unmatched_dicom, unmatched_clinical = match(
        dicom_df, clinical_df, logger
    )

    # Étape 4 — Résumé et sorties
    print_summary(matched, unmatched_dicom, unmatched_clinical, logger)
    paths = write_outputs(matched, unmatched_dicom, unmatched_clinical, out, logger)

    logger.info("Durée totale : %.2f secondes", time.time() - t0)

    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Appariement DICOM ↔ données cliniques — DeepBridge / CHU Nice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Clé de jointure : colonne CODES du fichier Excel ↔ nom du dossier DICOM
Insensible à la casse. Suffixes _SR ignorés automatiquement.

Sorties produites :
  matched.csv            — séries DICOM avec données cliniques
  unmatched_dicom.csv    — séries DICOM sans données cliniques
  unmatched_clinical.csv — entrées cliniques sans DICOM correspondant
  match_report.json      — rapport de synthèse

Exemples :
  py dicom_csv_matcher.py
  py dicom_csv_matcher.py C:\\deepbridge\\output C:\\dt\\dataset_chu_nice_2020_2021\\BaseCarotideAnonymisee.xlsx
  py dicom_csv_matcher.py C:\\deepbridge\\output C:\\dt\\...\\BaseCarotideAnonymisee.xlsx --output-dir C:\\deepbridge\\output
        """,
    )
    parser.add_argument(
        "sorted_dir", nargs="?", type=Path,
        default=DEFAULT_SORTED_DIR,
        help=f"Dossier validé (défaut : {DEFAULT_SORTED_DIR})",
    )
    parser.add_argument(
        "clinical_xlsx", nargs="?", type=Path,
        default=DEFAULT_CLINICAL_XLSX,
        help="Fichier Excel clinique du CHU",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Dossier de sortie pour les CSV (défaut : sorted_dir)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    errors = []
    if not args.sorted_dir.exists():
        errors.append(f"Dossier DICOM introuvable : {args.sorted_dir}")
    if not args.clinical_xlsx.exists():
        errors.append(f"Fichier Excel introuvable : {args.clinical_xlsx}")

    if errors:
        for e in errors:
            print(f"Erreur : {e}", file=sys.stderr)
        sys.exit(1)

    run(
        sorted_dir=args.sorted_dir,
        clinical_xlsx=args.clinical_xlsx,
        output_dir=args.output_dir,
    )