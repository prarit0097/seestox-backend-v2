# core_engine/ml_engine/confidence/confidence_dataset_builder.py
# ER-7.1 — CONFIDENCE DATASET BUILDER

import json
import os

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
HISTORY_FILE = os.path.join(BASE_DIR, "prediction_history.json")


# --------------------------------------------------
# ENCODERS (RULE BASED)
# --------------------------------------------------

TREND_MAP = {
    "UPTREND": 1,
    "SIDEWAYS": 0,
    "DOWNTREND": -1,
}

SENTIMENT_MAP = {
    "POSITIVE": 1,
    "POSITIVE_WEAK": 0.5,
    "NEUTRAL": 0,
    "NEGATIVE": -1,
}

RISK_MAP = {
    "LOW": 0,
    "MEDIUM": 0.5,
    "HIGH": 1,
}


# --------------------------------------------------
# LOAD HISTORY
# --------------------------------------------------

def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


# --------------------------------------------------
# MAIN DATASET BUILDER
# --------------------------------------------------

def build_confidence_dataset(symbol: str | None = None):
    """
    Returns ML-ready confidence dataset.

    Output:
      X → list of feature vectors
      y → list of labels (1=correct, 0=wrong)
    """

    history = _load_history()

    X = []
    y = []

    for record in history:

        # -------------------------------
        # FILTERS
        # -------------------------------
        if record.get("evaluated") is not True:
            continue

        if symbol and record.get("symbol") != symbol:
            continue

        context = record.get("context", {})
        expected = record.get("expected_range")

        if not isinstance(expected, dict):
            continue

        result = record.get("result")
        if result not in ("INSIDE_RANGE", "UPPER_BREAK", "LOWER_BREAK"):
            continue

        # -------------------------------
        # LABEL
        # -------------------------------
        hit = 1 if result == "INSIDE_RANGE" else 0

        # -------------------------------
        # FEATURES
        # -------------------------------
        trend = TREND_MAP.get(context.get("trend"), 0)
        sentiment = SENTIMENT_MAP.get(context.get("sentiment"), 0)
        risk = RISK_MAP.get(context.get("risk"), 0)

        avg_error = float(record.get("range_error") or 0.0)
        ml_used = 1 if context.get("ml_applied") else 0

        X.append([
            avg_error,
            trend,
            sentiment,
            risk,
            ml_used,
        ])

        y.append(hit)

    return X, y
