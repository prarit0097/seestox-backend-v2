# core_engine/ml_engine/expected_range/champion_predictor.py
# ER-5.2 — CHAMPION BASED EXPECTED RANGE PREDICTOR (SAFE MODE)

from typing import Dict

from core_engine.ml_engine.expected_range.model_registry import get_model
from core_engine.ml_engine.expected_range.champion_selector import load_champion


def predict_expected_range_with_champion(
    symbol: str,
    features: list,
    fallback_range: Dict[str, float],
) -> Dict:
    """
    Predict Expected Range using Champion models.
    Safe fallback to RULE based range.
    """

    champion = load_champion()

    # -----------------------------
    # 1. No champion yet → fallback
    # -----------------------------
    if champion.get("status") != "READY":
        return {
            "low": fallback_range["low"],
            "high": fallback_range["high"],
            "ml_applied": False,
            "reason": "NO_CHAMPION",
        }


    try:
        low_model_name = champion["champion_low"]
        high_model_name = champion["champion_high"]

        low_model = get_model(low_model_name)
        high_model = get_model(high_model_name)

        if low_model is None or high_model is None:
            raise ValueError("Champion models not found")

        # sklearn/xgb expects 2D input
        X = [features]

        low_pred = float(low_model.predict(X)[0])
        high_pred = float(high_model.predict(X)[0])

        # Safety clamp
        if low_pred >= high_pred:
            raise ValueError("Invalid predicted range")

        return {
            "low": round(low_pred, 2),
            "high": round(high_pred, 2),
            "ml_applied": True,
            "reason": "CHAMPION_MODEL",
            "champion_low": low_model_name,
            "champion_high": high_model_name,
        }

    except Exception:
        # Absolute safety fallback
        return {
            "low": fallback_range["low"],
            "high": fallback_range["high"],
            "ml_applied": False,
            "reason": "CHAMPION_FAILED",
        }
