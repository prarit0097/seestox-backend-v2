# core_engine/ml_engine/expected_range/model_trainer.py
# ER-3.3 — EXPECTED RANGE MODEL TRAINER (STABLE PYTHON 3.13)

import numpy as np
from sklearn.model_selection import train_test_split
from typing import Dict

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except Exception:
    XGBOOST_AVAILABLE = False


def train_expected_range_models(
    X: np.ndarray,
    y_low: np.ndarray,
    y_high: np.ndarray,
) -> Dict:
    """
    Trains multiple models for Expected Range prediction.
    """

    X = np.array(X)
    y_low = np.array(y_low)
    y_high = np.array(y_high)

    if X.size == 0 or y_low.size == 0 or y_high.size == 0:
        return {
            "status": "INSUFFICIENT_DATA",
            "models": {}
        }

    models = {}

    # Linear
    models["linear_low"] = LinearRegression().fit(X, y_low)
    models["linear_high"] = LinearRegression().fit(X, y_high)

    # Random Forest
    models["rf_low"] = RandomForestRegressor(n_estimators=50, random_state=42).fit(X, y_low)
    models["rf_high"] = RandomForestRegressor(n_estimators=50, random_state=42).fit(X, y_high)

    # Gradient Boosting
    models["gb_low"] = GradientBoostingRegressor(random_state=42).fit(X, y_low)
    models["gb_high"] = GradientBoostingRegressor(random_state=42).fit(X, y_high)

    # XGBoost (optional)
    if XGBOOST_AVAILABLE:
        models["xgb_low"] = XGBRegressor(n_estimators=50, random_state=42).fit(X, y_low)
        models["xgb_high"] = XGBRegressor(n_estimators=50, random_state=42).fit(X, y_high)

    return {
        "status": "TRAINED",
        "models": models,
    }



def evaluate_expected_range_models(
    models: dict,
    X: np.ndarray,
    y_low: np.ndarray,
    y_high: np.ndarray,
    expected_lows: np.ndarray,
    expected_highs: np.ndarray,
    actual_closes: np.ndarray,
) -> dict:
    """
    Compute hit-rate (primary) and MAE (tie-breaker)
    for each model using a validation split.
    """
    X = np.array(X)
    y_low = np.array(y_low)
    y_high = np.array(y_high)
    expected_lows = np.array(expected_lows)
    expected_highs = np.array(expected_highs)
    actual_closes = np.array(actual_closes)

    if (
        X.size == 0
        or y_low.size == 0
        or y_high.size == 0
        or expected_lows.size == 0
        or expected_highs.size == 0
        or actual_closes.size == 0
    ):
        return {}

    (
        X_train,
        X_val,
        y_low_train,
        y_low_val,
        y_high_train,
        y_high_val,
        exp_low_train,
        exp_low_val,
        exp_high_train,
        exp_high_val,
        actual_train,
        actual_val,
    ) = train_test_split(
        X,
        y_low,
        y_high,
        expected_lows,
        expected_highs,
        actual_closes,
        test_size=0.3,
        random_state=42,
    )

    scores = {}

    for name, model in models.items():
        if name.endswith("_low"):
            model.fit(X_train, y_low_train)
            low_pred = model.predict(X_val)
            mae = float(mean_absolute_error(y_low_val, low_pred))
            scores[name] = {"mae": mae}

        elif name.endswith("_high"):
            model.fit(X_train, y_high_train)
            high_pred = model.predict(X_val)
            mae = float(mean_absolute_error(y_high_val, high_pred))
            scores[name] = {"mae": mae}

    # Compute hit-rate using paired low/high where available
    pair_scores = {}
    lows = {k: v for k, v in scores.items() if k.endswith("_low")}
    highs = {k: v for k, v in scores.items() if k.endswith("_high")}

    for low_name in lows:
        high_name = low_name.replace("_low", "_high")
        if high_name not in highs:
            continue

        low_model = models[low_name]
        high_model = models[high_name]
        low_pred = low_model.predict(X_val)
        high_pred = high_model.predict(X_val)

        hits = 0
        for i in range(len(X_val)):
            low = float(exp_low_val[i] + low_pred[i])
            high = float(exp_high_val[i] + high_pred[i])
            actual = float(actual_val[i])
            if low <= actual <= high:
                hits += 1
        hit_rate = hits / len(X_val) if len(X_val) else 0.0

        avg_mae = (scores[low_name]["mae"] + scores[high_name]["mae"]) / 2
        pair_name = low_name.replace("_low", "")
        pair_scores[pair_name] = {
            "hit_rate": round(hit_rate, 4),
            "mae_low": scores[low_name]["mae"],
            "mae_high": scores[high_name]["mae"],
            "mae": round(avg_mae, 4),
        }

    return pair_scores
