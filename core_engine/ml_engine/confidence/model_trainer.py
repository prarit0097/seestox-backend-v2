# core_engine/ml_engine/confidence/model_trainer.py
# ER-7.2 — CONFIDENCE MODEL TRAINER

import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from core_engine.ml_engine.confidence.confidence_dataset_builder import (
    build_confidence_dataset
)


# --------------------------------------------------
# MAIN TRAIN FUNCTION
# --------------------------------------------------

def train_confidence_models(symbol: str | None = None):
    """
    Trains multiple confidence models.

    Returns:
      {
        status,
        samples,
        models,
        scores
      }
    """

    X, y = build_confidence_dataset(symbol)

    if len(X) < 15:
        return {
            "status": "INSUFFICIENT_DATA",
            "samples": len(X),
            "models": {},
            "scores": {},
        }

    X = np.array(X)
    y = np.array(y)

    # -------------------------------
    # Train / Validation split
    # -------------------------------
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    models = {
        "logistic": LogisticRegression(
            max_iter=500,
            class_weight="balanced",
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            random_state=42,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=150,
            learning_rate=0.05,
            max_depth=3,
            random_state=42,
        ),
    }

    trained_models = {}
    scores = {}

    # -------------------------------
    # Training loop
    # -------------------------------
    for name, model in models.items():
        model.fit(X_train, y_train)

        preds = model.predict(X_val)
        acc = round(float(accuracy_score(y_val, preds)), 3)

        trained_models[name] = model
        scores[name] = acc

    return {
        "status": "TRAINED",
        "samples": len(X),
        "models": trained_models,
        "scores": scores,
    }
