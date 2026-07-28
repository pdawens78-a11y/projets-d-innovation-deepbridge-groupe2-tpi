# DeepBridge — Pipeline DICOM

Organisation et analyse de fichiers DICOM pour le CHU.

## Structure du projet

```
deepbridge/
│
├── data/                        # Fichiers DICOM bruts (entrée)
├── output/                      # Arborescence organisée (sortie)
│   ├── PAT_001/
│   │   └── 1.2.840.UID.XXX/
│   │       ├── slice_001.dcm
│   │       └── slice_002.dcm
│   └── pipeline_report.csv      # Rapport de traitement
├── logs/                        # Logs JSON rotatifs
├── quarantine/                  # Fichiers invalides / non-CT
│   ├── invalid_dicom/
│   ├── missing_tags/
│   └── modality_MR/
├── tests/
│   └── test_pipeline.py
│
├── config.py                    # Configuration centralisée
├── organize_dicom_files.py      # Pipeline principal
├── analyse_results.py           # Analyse de l'arborescence
├── requirements.txt
└── README.md
```

## Installation

```powershell
# 1. Cloner / créer le dossier
cd deepbridge

# 2. Créer l'environnement virtuel
py -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Installer les dépendances
pip install -r requirements.txt
```

## Utilisation

### Pipeline d'organisation

```powershell
# Utilise data/ → output/ (config.py)
py organize_dicom_files.py

# Chemins personnalisés
py organize_dicom_files.py "C:\data\chu_raw" "C:\data\chu_sorted"

# Simulation (aucun fichier déplacé)
py organize_dicom_files.py --dry-run

# Parallélisme accru
py organize_dicom_files.py --workers 8
```

### Analyse des résultats

```powershell
# Analyse du dossier output/ (config.py)
py analyse_results.py

# Comparaison avant/après + export JSON
py analyse_results.py "C:\data\chu_raw" "C:\data\chu_sorted" --export rapport.json
```

### Tests

```powershell
py -m pytest tests/ -v
py -m pytest tests/ -v --cov=. --cov-report=term-missing
```

## Configuration

Tous les paramètres sont dans `config.py` :

| Paramètre | Défaut | Description |
|---|---|---|
| `DATA_DIR` | `./data` | Dossier source |
| `OUTPUT_DIR` | `./output` | Dossier de sortie |
| `ACCEPTED_MODALITIES` | `{"CT"}` | Modalités conservées |
| `DEFAULT_WORKERS` | `4` | Threads parallèles |
| `LOG_LEVEL` | `INFO` | Niveau de log |

## Sorties produites

| Fichier | Description |
|---|---|
| `output/pipeline_report.csv` | Audit trail complet (un fichier = une ligne) |
| `logs/pipeline.log` | Logs JSON rotatifs (10 Mo × 5 fichiers) |
| `quarantine/` | Fichiers invalides classés par raison |
