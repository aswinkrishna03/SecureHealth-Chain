"""Dataset-trained educational heart-risk model for the demo dashboard.

This model is not clinically validated and must not be used for diagnosis or
treatment. It is trained from the bundled sample dataset for demonstration.
"""

import csv
import os
from functools import lru_cache

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset", "heart_disease.csv")


def _scaled(age, resting_bp, cholesterol, max_hr, angina):
    return [age / 100.0, resting_bp / 200.0, cholesterol / 400.0, max_hr / 220.0, angina]


@lru_cache(maxsize=1)
def _load_model():
    features, labels = [], []
    with open(DATASET_PATH, newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            features.append(_scaled(
                float(row["age"]), float(row["trestbps"]), float(row["chol"]),
                float(row["thalach"]), float(row["exang"]),
            ))
            labels.append(int(row["target"]))
    if len(set(labels)) < 2:
        raise ValueError("The bundled heart disease dataset must contain both target classes")

    x = np.asarray(features, dtype=float)
    y = np.asarray(labels, dtype=int)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42, stratify=y
    )
    evaluation_model = LogisticRegression(max_iter=500, random_state=42)
    evaluation_model.fit(x_train, y_train)
    held_out_accuracy = round(float(accuracy_score(y_test, evaluation_model.predict(x_test))) * 100, 1)

    final_model = LogisticRegression(max_iter=500, random_state=42)
    final_model.fit(x, y)
    return final_model, held_out_accuracy


def predict_risk(age, resting_bp, cholesterol, max_hr, angina):
    values = [float(age), float(resting_bp), float(cholesterol), float(max_hr), int(angina)]
    age, bp, chol, max_hr, angina = values
    bounds = ((18, 120), (60, 260), (50, 700), (30, 250), (0, 1))
    if any(value < low or value > high for value, (low, high) in zip(values, bounds)):
        raise ValueError("One or more clinical values are outside the supported demo range")
    if angina not in (0, 1):
        raise ValueError("angina must be 0 or 1")

    model, held_out_accuracy = _load_model()
    probability = float(model.predict_proba([_scaled(age, bp, chol, max_hr, angina)])[0][1])
    risk_pct = round(probability * 100, 1)
    level = "High Risk" if risk_pct >= 65 else "Moderate Risk" if risk_pct >= 40 else "Low Risk"
    return {
        "risk_probability": risk_pct,
        "risk_level": level,
        "model": "Logistic regression trained on the bundled sample heart-disease dataset",
        "held_out_accuracy": held_out_accuracy,
        "warning": "Educational demonstration only; not clinically validated and not for diagnosis or treatment.",
        "recommendations": ["Discuss health concerns and measurements with a qualified clinician."],
    }
