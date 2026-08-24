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

## 7. Extraction des archives .cab — 21/08/2026

Procedure executee avant relance du tri DICOM :

- Script utilise : `ingestion/extract_cab_files.py`.
- Source : `C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan`.
- Destination : `C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan_extracted`.
- Strategie anti-collision : un sous-dossier dedie par archive (`scan_extracted/<nom_cab_sans_extension>/`) afin d'eviter tout ecrasement entre fichiers homonymes de CAB differents.

Resume d'execution complete :

| Indicateur | Valeur |
|---|---:|
| Archives `.cab` traitees | 150 |
| Erreurs d'extraction | 0 |
| Fichiers extraits | 138 398 |
| Fichiers `.dcm` extraits | 138 008 |
| Duree totale | 851 s |

Observation de coherence avec les donnees CHU Nice 2020-2021 deja documentees :

- Les ordres de grandeur sont pratiquement identiques (`138 398` fichiers et `138 007-138 008` DICOM selon la source).
- Cette correspondance est tres forte et suggere qu'il s'agit tres probablement de la meme base de donnees, livree ici sous forme d'archives `.cab`.

## 8. Dry-run apres extraction — 21/08/2026

Commande executee :

`py ingestion/organize_dicom_files.py "C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan_extracted" output --dry-run`

Source de verite : `output/pipeline_report.csv` genere par ce dry-run.

| Indicateur | Nombre |
|---|---:|
| Fichiers detectes | 138 399 |
| Fichiers qui seraient organises | 138 007 |
| Fichiers qui iraient en quarantaine | 391 |
| Fichiers classes `deleted` | 0 |
| Fichiers `skipped` | 1 |
| Erreurs | 0 |

Detail par categorie de rejet (CSV) :

| Categorie | Nombre | Motif |
|---|---:|---|
| Quarantaine (DICOM invalide) | 391 | `InvalidDicomError: File is missing DICOM File Meta Information header or the 'DICM' prefix is missing from the header. Use force=True to force reading.` |
| Modalite non acceptee | 1 | `Modalité non acceptée : SR` |

Comparaison avec la premiere tentative sur `.cab` non extraits :

- Avant extraction : `150` detectes, `0` organisables (0 % exploitable), rejet unique `extension .cab`.
- Apres extraction : `138 399` detectes, `138 007` organisables (~99,72 %), `391` quarantaine et `1` modalite non CT.
- Conclusion : l'extraction des `.cab` a bien resolu le blocage initial et rendu la base massivement exploitable pour l'organisation DICOM.

## 9. Note sur la deduplication — execution reelle du 21/08/2026

Commande executee (execution reelle, sans `--dry-run`) :

`py ingestion/organize_dicom_files.py "C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan_extracted" output --copy --workers 8`

Le rapport `output/pipeline_report.csv` de cette execution comptabilise `138 007` lignes avec `status=copied`. Cependant, le nombre reel de fichiers `.dcm` presents sur disque dans `output/` (dossiers `PatientID/SeriesUID`) est de `135 572`, soit un ecart de `2 435` fichiers.

**Cause de l'ecart : deduplication de doublons exacts entre archives `.cab`.**

`safe_destination()` (dans `ingestion/organize_dicom_files.py`) considere un fichier comme un doublon exact lorsque le nom de fichier **et** la taille en octets sont identiques a un fichier deja present a la meme destination (`PatientID/SeriesUID/nom_fichier`). Dans ce cas, la copie physique est sautee (le fichier de destination existe deja et est identique), mais la ligne du CSV enregistre tout de meme `status=copied` pour ce fichier source.

Concretement, `138 007` mesure le nombre de fichiers sources **traites avec succes** (copie physique effectuee ou doublon exact confirme), pas le nombre d'ecritures physiques distinctes sur disque. Le nombre de fichiers reellement ecrits correspond au nombre de `destination_path` uniques parmi les lignes `copied`, soit `135 572` — exactement `138 007 - 2 435`.

Ces `2 435` doublons s'expliquent par la presence de la meme instance DICOM (meme patient, meme serie, meme nom de fichier, meme taille) dans plusieurs archives `.cab` differentes du jeu de donnees CHU Nice 2020-2021. Il ne s'agit pas d'une perte de donnees : chaque instance unique est bien presente une fois dans l'arborescence organisee.

Point d'attention pour l'interpretation future des rapports CSV de ce script : la colonne `status` reflete une tentative de transfert reussie, pas une ecriture physique distincte. Pour compter les fichiers reellement organises, deduplique par `destination_path` plutot que de compter les lignes `status=copied`.
