from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix
import pandas as pd

# === 1. Charger les données ===
file_path = "../deep-bridge-data-clean.csv"
df = pd.read_csv(file_path)

# === 2. Préparation des données ===
X = df.drop(columns=["complication", "numéro"])  # variables explicatives
y = df["complication"]  # variable cible

# Division train/test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# === 3. Modèle Random Forest ===
rf = RandomForestClassifier(
    n_estimators=200, max_depth=None, random_state=42, class_weight="balanced"
)
rf.fit(X_train, y_train)

# === 4. Prédictions ===
y_pred = rf.predict(X_test)
y_proba = rf.predict_proba(X_test)[:, 1]

# === 5. Évaluation ===
metrics = {
    "Accuracy": accuracy_score(y_test, y_pred) * 100,
    "Precision": precision_score(y_test, y_pred) * 100,
    "Recall": recall_score(y_test, y_pred) * 100,
    "F1-score": f1_score(y_test, y_pred) * 100,
    "ROC-AUC": roc_auc_score(y_test, y_proba) * 100,
}

# === 6. Matrice de confusion ===
cm = confusion_matrix(y_test, y_pred)
tn, fp, fn, tp = cm.ravel()

# === 7. Importance des variables ===
importances = pd.DataFrame({
    "Feature": X.columns,
    "Importance": rf.feature_importances_
}).sort_values(by="Importance", ascending=False)

# === 8. Résultats dans le terminal ===
print("\n=== Résultats Random Forest ===")
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

print("\n=== Importance des variables ===")
print(importances.to_string(index=False))

# === 9. Prédictions par patient ===
results = X_test.copy()
results["y_true (complication réelle)"] = y_test.values
results["y_pred (complication prédite)"] = y_pred
results["proba_complication (%)"] = (y_proba * 100).round(2)

print("\n=== 10 premiers patients du jeu de test ===")
print(results.head(10))

# print("\n=== les patients du jeu de test ===")
# pd.set_option("display.max_rows", None)   # affiche toutes les lignes
# pd.set_option("display.max_columns", None)  # affiche toutes les colonnes
# pd.set_option("display.width", None)  # pas de coupure
# print(results)

