"""
config.py — Configuration centralisée DeepBridge
Tous les chemins, seuils et constantes passent ici.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# Dossiers principaux
DATA_DIR       = Path(r"C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan_extracted")
OUTPUT_DIR     = PROJECT_ROOT / "output"
LOGS_DIR       = PROJECT_ROOT / "logs"
QUARANTINE_DIR = PROJECT_ROOT / "quarantine"

for _d in (DATA_DIR, OUTPUT_DIR, LOGS_DIR, QUARANTINE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Couche 1 : Ingestion ──────────────────────────────────────
REQUIRED_TAGS        = ("PatientID", "SeriesInstanceUID", "Modality")
ACCEPTED_MODALITIES  = {"CT"}
EXTENSIONS_TO_DELETE = {".cab"}
DEFAULT_WORKERS      = 4
REPORT_FILENAME      = "pipeline_report.csv"
REPORT_FIELDS        = [
    "timestamp", "source_path", "destination_path",
    "patient_id", "series_uid", "modality",
    "status", "reason", "file_size_bytes",
]

# ── Couche 2 : Prétraitement ──────────────────────────────────
# Unités Hounsfield — fenêtrage aortique par défaut
HU_MIN = -100
HU_MAX = 400

# Espacement cible pour le resampling (mm)
TARGET_SPACING = (1.0, 1.0, 1.0)   # isotropique 1 mm³

# Normalisation Z-score
NORM_MEAN = 0.0
NORM_STD  = 1.0

# Seuils de validation
MIN_SLICES         = 50     # nombre minimum de coupes par série
MAX_PIXEL_SPACING  = 1.5    # mm — au-delà, la série est rejetée

# Augmentation TorchIO
AUGMENTATION_FACTOR = 50    # nombre de volumes générés par volume original

# ── Couche 3 : Annotation & Dataset ──────────────────────────
NASCT_THRESHOLD = 0.7       # seuil de sténose significative (70%)
DATASET_SPLIT   = (0.70, 0.15, 0.15)   # train / val / test

# ── Couche 4 : Entraînement ──────────────────────────────────
ONNX_OPSET      = 17
MODEL_OUTPUT    = PROJECT_ROOT / "output" / "modele.onnx"

# ── Logging ───────────────────────────────────────────────────
LOG_LEVEL        = "INFO"
LOG_MAX_BYTES    = 10_485_760   # 10 Mo
LOG_BACKUP_COUNT = 5
