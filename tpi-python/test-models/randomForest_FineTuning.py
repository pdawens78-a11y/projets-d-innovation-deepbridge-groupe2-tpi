import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split, GridSearchCV, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score, roc_curve
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE
import warnings
warnings.filterwarnings('ignore')

# Chargement des données
data = pd.read_csv('../deep-bridge-data-clean.csv')

# Exploration initiale
print("Dimensions des données:", data.shape)
print("\nInformations sur les colonnes:")
print(data.info())
print("\nValeurs manquantes:")
print(data.isnull().sum())
print("\nDistribution de la variable cible (complication):")
print(data['complication'].value_counts())
print("\nPourcentage de complications:", data['complication'].mean() * 100)


# Nettoyage et préparation des données
# Supprimer la colonne numéro si elle n'est pas utile
if 'numéro' in data.columns:
    data = data.drop('numéro', axis=1)

# Vérifier les doublons
print("Nombre de doublons:", data.duplicated().sum())

# Séparation des caractéristiques et de la cible
X = data.drop('complication', axis=1)
y = data['complication']

# Analyse des corrélations
plt.figure(figsize=(10, 8))
correlation_matrix = data.corr()
sns.heatmap(correlation_matrix, annot=True, cmap='coolwarm', center=0)
plt.title('Matrice de corrélation')
plt.tight_layout()
plt.show()

# Distribution des variables
data.hist(figsize=(15, 10))
plt.tight_layout()
plt.show()


# Application de SMOTE pour équilibrer les classes
smote = SMOTE(random_state=42)
X_res, y_res = smote.fit_resample(X, y)

print("Distribution avant SMOTE:", np.bincount(y))
print("Distribution après SMOTE:", np.bincount(y_res))

# Division en ensembles d'entraînement et de test
X_train, X_test, y_train, y_test = train_test_split(
    X_res, y_res, test_size=0.2, random_state=42, stratify=y_res
)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
# Définition des hyperparamètres à optimiser
param_grid_rf = {
    'n_estimators': [100, 200, 300],
    'max_depth': [None, 10, 20, 30],
    'min_samples_split': [2, 5, 10],
    'min_samples_leaf': [1, 2, 4],
    'bootstrap': [True, False]
}

# Recherche par grille
rf = RandomForestClassifier(random_state=42)
grid_search_rf = GridSearchCV(
    estimator=rf,
    param_grid=param_grid_rf,
    cv=5,
    scoring='roc_auc',
    n_jobs=-1,
    verbose=1
)

grid_search_rf.fit(X_train, y_train)

# Meilleurs paramètres
print("Meilleurs paramètres pour Random Forest:")
print(grid_search_rf.best_params_)
print("Meilleur score:", grid_search_rf.best_score_)

# Évaluation du modèle
best_rf = grid_search_rf.best_estimator_
y_pred_rf = best_rf.predict(X_test)
y_pred_proba_rf = best_rf.predict_proba(X_test)[:, 1]


print("\nRapport de classification - Random Forest:")
print(classification_report(y_test, y_pred_rf))


# Calcul de l'accuracy pour Random Forest
metrics = {
    "Accuracy": accuracy_score(y_test, y_pred_rf) * 100,
    "Precision": precision_score(y_test, y_pred_rf) * 100,
    "Recall": recall_score(y_test, y_pred_rf) * 100,
    "F1-score": f1_score(y_test, y_pred_rf) * 100,
    "ROC-AUC": roc_auc_score(y_test, y_pred_proba_rf) * 100,
}

cm = confusion_matrix(y_test, y_pred_rf)
tn, fp, fn, tp = cm.ravel()

print("\n=== Résultats Random Forest avec fine tuning ===")
for k, v in metrics.items():
    print(f"{k}: {v:.2f}%")

print("\n=== Matrice de confusion ===")
print(f"                 Prédit 0   Prédit 1")
print(f"Réel 0 (pas de complication)   {tn:3d}       {fp:3d}")
print(f"Réel 1 (complication)          {fn:3d}       {tp:3d}")

print("\n=== Détails ===")
print(f"Vrai Négatif (TN) : {tn}")
print(f"Faux Positif (FP) : {fp}")
print(f"Faux Négatif (FN) : {fn}")
print(f"Vrai Positif (TP) : {tp}")


# Matrice de confusion
cm_rf = confusion_matrix(y_test, y_pred_rf)
plt.figure(figsize=(8, 6))
sns.heatmap(cm_rf, annot=True, fmt='d', cmap='Blues')
plt.title('Matrice de confusion - Random Forest')
plt.ylabel('Vraie étiquette')
plt.xlabel('Étiquette prédite')
plt.show()