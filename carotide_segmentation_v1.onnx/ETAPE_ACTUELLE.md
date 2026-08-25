# État actuel du pipeline

Ce document résume, à la date de rédaction, ce qui a réellement tourné sur la
base CHU Nice 2020-2021, ce qui est en cours, et ce qui a été abandonné suite
au remplacement de l'entraînement nnU-Net par TotalSegmentator.

## Couche 1 — Ingestion : terminée sur la base réelle

`organize_dicom_files.py` (`ingestion/`) et `validate_dataset.py` ont tourné
sur la base réelle du CHU de Nice. Résultats détaillés dans
`Etape1_organize_dicom.md` et `Etape2_validate_dataset.md`.

## Couche 2 — Prétraitement : en cours de ré-exécution

`hu_converter.py` et `resampler.py` sont en cours de ré-exécution sur la base
réelle. Les résultats d'une exécution précédente ont été perdus suite à un
reformatage de machine.

## Couche 2/3 — Désactivées (pipeline nnU-Net abandonné)

`normalizer.py` et `augmentor.py` sont désactivés : ils avaient été pensés
pour préparer l'entraînement d'un modèle nnU-Net, abandonné au profit de
TotalSegmentator. Conservés pour référence, couverts par les tests unitaires.

## Segmentation — en cours d'intégration

Le pipeline de segmentation TotalSegmentator (dossier `segmentation/`) est en
cours d'intégration.
