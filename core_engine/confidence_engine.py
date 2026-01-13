# core_engine/confidence_engine.py
# PHASE-5C — BACKWARD COMPATIBLE + AUTO vs USER SPLIT (STABLE)

from typing import Dict, Union
import pandas as pd

from core_engine.prediction_history import (
    get_stats_for_symbol,
    get_confidence_trend
)

# ==================================================
# INTERNAL CALC
# ==================================================

def _build_confidence(stats: Dict, symbol: str) -> Dict:
    if stats.get("status") == "COLLECTING_DATA":
        return {
            "success_rate": 0,
            "failure_rate": 0,
            "neutral_rate": 100,
            "sample_size": 0,
            "confidence_score": 10,
            "verdict": "COLLECTING_DATA",
            "trend_7d": get_confidence_trend(symbol),
        }

    success = stats.get("success", 0)
    failure = stats.get("failure", 0)
    neutral = stats.get("neutral", 0)

    total = success + failure + neutral
    if total <= 0:
        return _neutral_confidence()

    success_rate = round((success / total) * 100)
    failure_rate = round((failure / total) * 100)
    neutral_rate = max(0, 100 - (success_rate + failure_rate))

    # sample size weighting
    if total < 10:
        weight = 0.5
    elif total < 25:
        weight = 0.65
    elif total < 50:
        weight = 0.8
    elif total < 100:
        weight = 0.9
    else:
        weight = 1.0

    confidence_score = max(10, min(90, int(success_rate * weight)))

    if confidence_score >= 70 and success_rate > failure_rate:
        verdict = "STRONG_SETUP"
    elif confidence_score >= 45:
        verdict = "AVERAGE_SETUP"
    elif confidence_score >= 25:
        verdict = "WEAK_SETUP"
    else:
        verdict = "UNRELIABLE"

    return {
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "neutral_rate": neutral_rate,
        "sample_size": total,
        "confidence_score": confidence_score,
        "verdict": verdict,
        "trend_7d": get_confidence_trend(symbol),
    }


# ==================================================
# PUBLIC API (ANALYZER SAFE)
# ==================================================

def calculate_confidence(input_data: Union[str, pd.DataFrame]) -> Dict:
    """
    🔐 Backward compatible:
    - analyzer.py expects flat keys → provided
    - AUTO / USER split available under `split`
    """

    # -----------------------------
    # EXTRACT SYMBOL
    # -----------------------------
    if isinstance(input_data, str):
        symbol = input_data
    elif isinstance(input_data, pd.DataFrame):
        symbol = input_data.attrs.get("symbol")
        if not symbol:
            return _neutral_confidence(note="Symbol missing in dataframe.")
    else:
        return _neutral_confidence(note="Invalid confidence input.")

    # -----------------------------
    # BUILD CONFIDENCE BLOCKS
    # -----------------------------
    overall = _build_confidence(
        get_stats_for_symbol(symbol),
        symbol
    )

    auto = _build_confidence(
        get_stats_for_symbol(symbol, mode="AUTO"),
        symbol
    )

    user = _build_confidence(
        get_stats_for_symbol(symbol, mode="USER"),
        symbol
    )

    # -----------------------------
    # 🔥 RETURN STRUCTURE
    # -----------------------------
    # Flat keys for analyzer
    result = dict(overall)

    # Extra data for future UI
    result["split"] = {
        "AUTO": auto,
        "USER": user
    }

    return result


# ==================================================
# FALLBACK
# ==================================================

def _neutral_confidence(note: str = None) -> Dict:
    data = {
        "success_rate": 0,
        "failure_rate": 0,
        "neutral_rate": 100,
        "sample_size": 0,
        "confidence_score": 10,
        "verdict": "INSUFFICIENT_DATA",
        "trend_7d": {"delta": 0, "direction": "STABLE"},
    }
    if note:
        data["note"] = note
    return data
