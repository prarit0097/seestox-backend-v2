    # core_engine/ml_engine/expected_range/model_persistence.py
# ER-4.1 — MODEL PERSISTENCE LAYER (STABLE)

import os
import json
from datetime import datetime
import joblib

# ==================================================
# PATH CONFIG
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
META_FILE = os.path.join(MODEL_DIR, "meta.json")

os.makedirs(MODEL_DIR, exist_ok=True)


# ==================================================
# SAVE MODELS
# ==================================================

def save_models(models: dict, samples: int, feature_count: int) -> dict:
    """
    Save trained Expected Range models to disk.
    models: dict of sklearn/xgb models
    """

    saved = []

    for name, model in models.items():
        file_path = os.path.join(MODEL_DIR, f"{name}.joblib")
        joblib.dump(model, file_path)
        saved.append(name)

    meta = {
        "trained_on": datetime.now().isoformat(),
        "samples": samples,
        "features": feature_count,
        "models": saved,
    }

    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

    return {
        "status": "SAVED",
        "count": len(saved),
        "models": saved,
    }


# ==================================================
# LOAD MODELS
# ==================================================

def load_all_models() -> dict:
    """
    Load all saved Expected Range models from disk.
    """

    if not os.path.exists(MODEL_DIR):
        return {}

    models = {}

    for file in os.listdir(MODEL_DIR):
        if file.endswith(".joblib"):
            name = file.replace(".joblib", "")
            path = os.path.join(MODEL_DIR, file)
            try:
                models[name] = joblib.load(path)
            except Exception:
                continue

    return models


# ==================================================
# LOAD META
# ==================================================

def load_model_meta() -> dict:
    if not os.path.exists(META_FILE):
        return {}

    try:
        with open(META_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}
