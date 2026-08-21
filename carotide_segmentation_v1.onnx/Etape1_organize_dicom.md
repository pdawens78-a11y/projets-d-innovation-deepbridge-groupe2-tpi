# Etape 1 — Organisation des fichiers DICOM

## 1. Contexte

Le CHU fournit les fichiers DICOM dans une arborescence qui ne garantit pas un classement directement exploitable. Cette etape prepare le traitement en triant les fichiers par patient et par serie avant le pretraitement, la validation clinique et les etapes de modelisation.

## 2. Ce que fait le script

Pour chaque fichier detecte, le script applique successivement les traitements suivants :

1. Il parcourt recursivement le dossier source et ignore les fichiers caches.
2. Il filtre les extensions parasites, notamment les fichiers `.cab`, qui sont marques pour suppression dans un traitement reel.
3. Il lit le fichier comme objet DICOM et gere les fichiers invalides ou illisibles.
4. Il valide la presence et la valeur des tags requis : `PatientID`, `SeriesInstanceUID` et `Modality`.
5. Il filtre la modalite et n'accepte que les examens `CT`.
6. Il dirige les fichiers non conformes vers la quarantaine lorsque cela est applicable.
7. Il gere les collisions de noms avec une destination sure et un suffixe de hash si necessaire.
8. Il organise les fichiers acceptes dans l'arborescence finale `PatientID/SeriesInstanceUID/fichier.dcm`.
9. En mode dry-run, il simule les transferts et suppressions sans modifier les fichiers sources, tout en produisant le rapport CSV.

## 3. Resultats de cette execution

Dry-run execute le 21/08/2026 depuis la racine du projet DeepBridge, avec le dossier source configure vers :

`C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan`

Source de verite : `output/pipeline_report.csv` genere par cette execution.

| Indicateur | Nombre |
|---|---:|
| Fichiers detectes | 150 |
| Fichiers qui seraient organises | 0 |
| Fichiers qui iraient en quarantaine | 0 |
| Fichiers marques pour suppression simulee | 150 |
| Erreurs | 0 |

Detail des rejets et exclusions enregistres dans le CSV :

| Categorie | Nombre | Motif |
|---|---:|---|
| Extension parasite | 150 | `extension .cab` |

Aucun fichier n'a ete deplace ou supprime reellement : l'execution etait en mode `--dry-run`.

## 4. Interpretation

La part exploitable pour l'organisation DICOM est de 0/150, soit 0 % dans cette execution. Les 150 fichiers detectes portent l'extension `.cab` et sont donc arretes par le filtre d'extensions parasites avant la lecture et la validation DICOM.

La categorie de rejet est unique et represente 100 % des fichiers : `extension .cab`. Cela signifie que les controles ulterieurs, notamment les tags DICOM, la modalite et les collisions, n'ont pas ete atteints pour ces fichiers. Il faut donc disposer de fichiers DICOM extraits ou directement lisibles avant de pouvoir mesurer la qualite des series et leur classement par patient et par serie.

## 5. Prochaine etape

La prochaine etape est l'execution de `validate_dataset.py` sur l'arborescence DICOM organisee. Elle controlera notamment le nombre de coupes, la presence de `SliceLocation` et la resolution `PixelSpacing` avant le pretraitement.

## 6. Execution reelle du 21/08/2026

Commande executee en conditions reelles :

`py ingestion/organize_dicom_files.py "C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan" output --copy --workers 8`

Mesures relevees sur l'execution :

| Indicateur | Valeur |
|---|---:|
| Duree totale (mur) | 00:00:00.330 |
| Fichiers detectes | 150 |
| Fichiers reellement copies | 0 |
| Fichiers en quarantaine | 0 |
| Fichiers classes `deleted` par le pipeline | 150 |
| Erreurs | 0 |

Verification de coherence avec le dry-run :

- Les chiffres correspondent exactement au dry-run pour les volumes attendus : 0 fichier organise, 0 quarantaine, 150 fichiers traites comme extension parasite, 0 erreur.
- Aucun ecart n'a ete constate.
- Note d'interpretation : en mode `--copy`, les fichiers `.cab` ne sont pas copies et restent en source, mais le statut de rapport utilise la categorie `deleted` pour tracer ce rejet d'extension.
