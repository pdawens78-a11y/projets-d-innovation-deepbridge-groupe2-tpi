# Etape 2 — Validation clinique et technique des series DICOM

## 1. Contexte

Une fois les fichiers DICOM organises par patient et par serie (Etape 1), chaque serie doit etre validee selon trois criteres medicalement fondes avant d'entrer dans le pretraitement (couche 2) : nombre de coupes suffisant, presence du tag `SliceLocation`, et resolution spatiale (`PixelSpacing`) suffisante. Le script `ingestion/validate_dataset.py` applique ces controles et produit un rapport CSV faisant foi.

## 2. Execution reelle du 21/08/2026

Commande executee, sur la base reellement organisee par l'ingestion `--copy --workers 8` (voir `Etape1_organize_dicom.md`, section 9) :

`py ingestion/validate_dataset.py "output" --workers 8`

Seuils appliques (`config.py`) :

| Parametre | Valeur |
|---|---:|
| `MIN_SLICES` | 50 |
| `MAX_PIXEL_SPACING` | 1.5 mm |

Source de verite : `output/validation_report.csv` genere par cette execution (193 lignes + en-tete).

## 3. Resultats globaux

| Indicateur | Nombre | Part |
|---|---:|---:|
| Series analysees | 193 | 100 % |
| Series valides | 156 | 80,8 % |
| Series rejetees | 37 | 19,2 % |
| Duree totale | 4,51 s | — |

Patients distincts couverts : 148 (coherent avec les 148 dossiers patients produits par l'ingestion reelle).

## 4. Detail des rejets par critere

| Critere | Nombre de series rejetees |
|---|---:|
| Nombre de coupes insuffisant (`< 50`) | 36 |
| `SliceLocation` absente | 0 |
| `PixelSpacing` hors seuil (`> 1.5 mm`) | 0 |
| Autres (dossier sans fichier `.dcm`) | 1 |

Aucun rejet n'est du a l'absence de `SliceLocation` ou a une resolution spatiale insuffisante : sur cette base, les deux seuls points de defaillance observes sont la couverture anatomique (nombre de coupes) et un artefact de test.

Repartition du nombre de coupes parmi les 36 series rejetees pour coupes insuffisantes :

| Nombre de coupes | Nombre de series |
|---:|---:|
| 1 | 26 |
| 2 | 2 |
| 5 | 1 |
| 6 | 1 |
| 9 | 1 |
| 24 | 2 |
| 29 | 2 |
| 34 | 1 |

La tres forte concentration a 1 coupe (26 series sur 36) suggere des series secondaires (scout/localizer, captures d'ecran, reconstructions 2D) classees `CT` par le DICOM mais ne representant pas un volume anatomique exploitable pour la segmentation — plutot qu'un probleme d'acquisition sur des volumes par ailleurs valides.

## 5. Artefact de test detecte

Une entree `temp_cab_extract_test` apparait dans le rapport (1 serie, 0 coupe, rejetee pour "Aucun fichier .dcm dans le dossier") :

```
temp_cab_extract_test,SF103E8_10.241.3.232_20210118173228207,...,rejected,Aucun fichier .dcm dans le dossier
```

Ce dossier est un residu d'un test manuel anterieur de `extract_cab_files.py`, present dans `output/` avant l'ingestion reelle. Il n'appartient pas au dataset patient et fausse legerement le total (193 series incluent ce residu, soit 192 series patient reelles). A nettoyer avant la prochaine execution pour eviter de polluer les futurs rapports.

## 6. Verification de coherence

- Parmi les 156 series valides, `has_slice_location=True` et `pixel_spacing_ok=True` pour 100 % des lignes (aucune incoherence entre `status=valid` et les criteres individuels).
- Le resume affiche par le script (`output/logs/validate.log`) correspond exactement aux comptages recalcules depuis `validation_report.csv`.
- Une premiere tentative de validation avait ete executee le 21/08/2026 a 12:58 UTC, avant l'ingestion reelle : elle avait trouve "0 serie(s) a valider" car `output/` etait encore vide a ce moment (voir `Etape1_organize_dicom.md`, section 9). Le present rapport est le premier a s'appuyer sur des donnees reellement organisees.

## 7. Prochaine etape

Les 156 series valides (192 - 36 rejets reels, artefact de test exclu) constituent la base d'entree pour la couche 2 — pretraitement : `hu_converter.py` (conversion Hounsfield), puis `resampler.py` (espacement isotropique) et `normalizer.py` (Z-score + CLAHE). Aucun de ces trois scripts n'a encore ete execute sur cette base a la date de ce document.
