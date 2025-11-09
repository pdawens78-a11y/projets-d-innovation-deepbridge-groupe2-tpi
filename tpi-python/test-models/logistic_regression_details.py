import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score

# Charger les données nettoyées
df = pd.read_csv("../deep-bridge-data-clean.csv")  

# Définir les features (X) et la cible (y)
X = df.drop(columns=["Numéro", "complication"], errors="ignore")  # variables explicatives
y = df["complication"]  # cible = complication oui/non

# Séparer en train/test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Entraîner la régression logistique
model = LogisticRegression(max_iter=1000)
model.fit(X_train, y_train)

# Évaluation du modèle
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

#en %
accuracy = accuracy_score(y_test, y_pred) * 100   
auc = roc_auc_score(y_test, y_prob) * 100         

print(" Évaluation du modèle:")
print(f"Précision (Accuracy): {accuracy:.2f}%")
print(f"Qualité de probabilité (ROC AUC): {auc:.2f}%")

#print("Colonnes du fichier :", df.columns.tolist())

# Calcul du risque pour tous les patients
df["Risque (%)"] = (model.predict_proba(X)[:, 1] * 100).round(2).astype(str) + "%"

df_affichage = df.rename(columns={
    "numéro": "N° du patient",
    "complication": "Complication",
    "Risque (%)": "Risque"
})

# Afficher les 10 premiers patients avec prédiction
print("\n Exemple de prédictions sur 10 patients :")
print(df_affichage[["N° du patient", "Complication", "Risque"]].head(10).to_string(index=False))

# Sauvegarder le fichier avec les résultats
df.to_csv("patients_predictions.csv", index=False)
print("\nRésultats sauvegardés dans 'patients_predictions.csv'")

# Prédiction pour un patient précis (ex: patient Numéro = 25)
patient_id = 25
if patient_id in df["numéro"].values:
    patient = df.loc[df["numéro"] == patient_id, X.columns]  # on récupère uniquement ses variables
    proba = model.predict_proba(patient)[:,1][0] * 100
    print(f"\n Patient n°{patient_id} → Risque de complication estimé à {proba:.2f}%")
else:
    print(f"\n Patient n°{patient_id} introuvable dans le dataset.")

# Visualisation de la distribution des risques
plt.figure(figsize=(8,5))
sns.histplot(model.predict_proba(X)[:,1]*100, bins=20, kde=True, color="skyblue")
plt.title("Distribution des risques prédits (%)", fontsize=14)
plt.xlabel("Risque de complication (%)", fontsize=12)
plt.ylabel("Nombre de patients", fontsize=12)
plt.grid(axis="y", linestyle="--", alpha=0.7)
plt.show()


