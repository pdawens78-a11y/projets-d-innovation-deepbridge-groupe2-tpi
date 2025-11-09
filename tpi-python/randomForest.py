from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)
import pandas as pd


def prepare_features_targets(df: pd.DataFrame):
    """
    Prépare les variables explicatives (X) et la variable cible (y)
    à partir d'un DataFrame nettoyé.
    """
    drop_cols = [col for col in ["complication", "numero", "numéro"] if col in df.columns]
    X = df.drop(columns=drop_cols)
    y = df["complication"]
    return X, y


def train_random_forest(X, y):
    """
    Entraîne un modèle Random Forest et retourne le modèle,
    les prédictions, les probabilités et les métriques.
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    rf = RandomForestClassifier(
        n_estimators=200, max_depth=None, random_state=42, class_weight="balanced"
    )
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    y_proba = rf.predict_proba(X_test)[:, 1]

    metrics = {
        "Accuracy": accuracy_score(y_test, y_pred) * 100,
        "Precision": precision_score(y_test, y_pred) * 100,
        "Recall": recall_score(y_test, y_pred) * 100,
        "F1-score": f1_score(y_test, y_pred) * 100,
        "ROC-AUC": roc_auc_score(y_test, y_proba) * 100,
    }

    cm = confusion_matrix(y_test, y_pred)

    return {
        "model": rf,
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "y_proba": y_proba,
        "metrics": metrics,
        "confusion_matrix": cm,
    }


if __name__ == "__main__":
    file_path = "deep-bridge-data-clean.csv"
    df = pd.read_csv(file_path)
    X, y = prepare_features_targets(df)
    result = train_random_forest(X, y)

    print("\n=== Résultats Random Forest ===")
    for k, v in result["metrics"].items():
        print(f"{k}: {v:.2f}%")

    print("\n=== Matrice de confusion ===")
    cm = result["confusion_matrix"]
    tn, fp, fn, tp = cm.ravel()
    print(f"                 Prédit 0   Prédit 1")
    print(f"Réel 0 (pas de complication)   {tn:3d}       {fp:3d}")
    print(f"Réel 1 (complication)          {fn:3d}       {tp:3d}")
