
# Deep Bridge - Modèles (Python)

Ce dépôt contient les scripts python liés à l'entraînement et à l'export d'un modèle Random Forest Classifier utilisé pour le projet "Deep Bridge - Dicom Viewer".

## Contenu important

- `clean_csv.py` : nettoyage / préparation des données CSV.
- `randomForest.py` : entraînement d'un modèle de Random Forest Classifier.
- `build_random_forest_model.py` : script utilisé pour exporter le modèle en format .ONNX.
- `requirements.txt` : liste modules Python

## Pré-requis

- Python 3.8+ installé.
- CMD.

## Installation

1. Créez et activez un environnement virtuel :

```
python -m venv .venv
.venv\Scripts\activate
```

3. Installez les modules via fichier `requirements.txt` :

```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Utilisation

- Nettoyage des données, modifier le chemin du dataset d'entrée si nécessaire :

```
python clean_csv.py
```

- Entraînement et tests :
```
python randomForest.py
```
> adaptez le chemin de `input.csv` et `deep-bridge-data-clean.csv` selon le cas, puis lancez le script qui charge et prédit via le modèle entrainé.

## Déploiement — export ONNX

Le script `build_random_forest_model.py` est utilisé pour créer et exporter le modèle au format `.ONNX`.

```
python build_random_forest_model.py
```

> Après exécution, un fichier `random_forest_model.onnx` sera être généré (ou modifier). 

> Ce fichier permet l'utilisation direct du modèle entrainé en dehors d'environement python *(ex: dans un projet .net)*. Comparable à un executable.

## Exemple de flux rapide

1. Nettoyer les données : `python clean_csv.py`
2. Entraîner et tester : `python randomForest.py`
3. Exporter ONNX : `python build_random_forest_model.py`
4. Vérifier l'existence de `random_forest_model.onnx`

## Remarques et bonnes pratiques

- Modifier le contenu de `requirements.txt` au fur et à mesure, rajoutter ou retirer des lignes.
> ou utiliser `pip freeze > requirements.txt`.

## Contributors

- 23, Raharison amboara Tiana Avotra
- 22, Rahajason Aroniaina Saotra
- 50, Ravelomahefa Serge
- 2, Andriamboavonjy Tafitasoa Tojohery Sambatra
- 57, Zahirhoussen Zoulfikar

Bonne utilisation.

