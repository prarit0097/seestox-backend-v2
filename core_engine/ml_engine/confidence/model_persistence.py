# core_engine/ml_engine/confidence/model_persistence.py
# ER-7.3A — CONFIDENCE MODEL PERSISTENCE

import os
import joblib

BASE_DIR = os.path.dirname(__file__)
MODEL_DIR = os.path.join(BASE_DIR, "saved_models")

os.makedirs(MODEL_DIR, exist_ok=True)


def save_confidence_model(symbol: str, model_name: str, model):
    path = os.path.join(
        MODEL_DIR, f"{symbol.lower()}_confidence_{model_name}.pkl"
    )
    joblib.dump(model, path)
    return path


def load_confidence_model(symbol: str, model_name: str):
    path = os.path.join(
        MODEL_DIR, f"{symbol.lower()}_confidence_{model_name}.pkl"
    )
    if not os.path.exists(path):
        return None
    return joblib.load(path)
