import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.dummy import DummyClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, roc_curve, auc
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv("../deep-bridge-data-clean.csv")

features = ["age_calcul", "age_arrondi", "femme/homme", "s+",
            "patch_=_1,_eversion_=_2", "shunt", "arterio",
            "re_inter", "anomalie", "anomalie_comm"]
X = df[features]
y = df["complication"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y
)

strategies = ["most_frequent", "uniform", "stratified"]
roc_curves = {}

for strat in strategies:
    print(f"\n=== DummyClassifier avec stratégie: {strat} ===")

    dummy = DummyClassifier(strategy=strat, random_state=42)
    dummy.fit(X_train, y_train)

    y_pred = dummy.predict(X_test)
    y_prob = dummy.predict_proba(X_test)[:, 1]  

    cm = confusion_matrix(y_test, y_pred)
    print("Matrice de confusion:\n", cm)

    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
    plt.xlabel("Prédit")
    plt.ylabel("Réel")
    plt.title(f"Matrice de Confusion - Dummy ({strat})")
    plt.show()

    print("Rapport de classification:")
    print(classification_report(y_test, y_pred, zero_division=0))

    acc = accuracy_score(y_test, y_pred)
    print("Accuracy:", acc)

    fpr, tpr, _ = roc_curve(y_test, y_prob)
    roc_auc = auc(fpr, tpr)
    print("AUC:", roc_auc)

    roc_curves[strat] = (fpr, tpr, roc_auc)

plt.figure(figsize=(8, 6))
for strat, (fpr, tpr, roc_auc) in roc_curves.items():
    plt.plot(fpr, tpr, lw=2, label=f"{strat} (AUC = {roc_auc:.2f})")

plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
plt.xlabel("Taux de faux positifs (FPR)")
plt.ylabel("Taux de vrais positifs (TPR)")
plt.title("Courbes ROC comparatives - DummyClassifier")
plt.legend(loc="lower right")
plt.show()