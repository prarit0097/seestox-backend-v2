# core_engine/ml_engine/expected_range_ml_adjuster.py
# PHASE-3D — EXPECTED RANGE ML ADJUSTER (SAFE MODE)

from typing import Dict
from core_engine.ml_engine.range_bias_learner import learn_range_bias


# -------------------------------
# CONFIG (SAFE CAPS)
# -------------------------------

MAX_EXPANSION_PCT = 0.35   # max 35% of base range width
MAX_TIGHTEN_PCT = 0.25    # max 25% tightening
MIN_SAMPLES_REQUIRED = 5


def adjust_expected_range(
    symbol: str,
    base_range: Dict[str, float],
) -> Dict[str, float]:
    """
    Applies ML bias adjustment on top of RULE-based expected range.

    base_range = {
        "low": float,
        "high": float
    }

    Returns adjusted range + metadata (safe, capped).
    """

    low = float(base_range.get("low"))
    high = float(base_range.get("high"))

    if low >= high:
        return {
            "low": low,
            "high": high,
            "ml_applied": False,
            "note": "Invalid base range",
        }

    base_width = high - low

    # -------------------------------
    # FETCH ML BIAS SIGNAL
    # -------------------------------
    bias = learn_range_bias(symbol)

    # Default: no ML applied
    adjusted_low = low
    adjusted_high = high
    ml_applied = False
    reason = "RULE_ONLY"

    if bias.get("status") == "READY" and bias.get("samples", 0) >= MIN_SAMPLES_REQUIRED:
        direction = bias.get("direction")
        suggested = float(bias.get("suggested_adjustment", 0))

        # Safety caps
        max_expand = base_width * MAX_EXPANSION_PCT
        max_tighten = base_width * MAX_TIGHTEN_PCT

        if direction == "EXPAND_UP":
            delta = min(abs(suggested), max_expand)
            adjusted_high = high + delta
            ml_applied = True
            reason = "ML_EXPAND_UP"

        elif direction == "EXPAND_DOWN":
            delta = min(abs(suggested), max_expand)
            adjusted_low = max(low - delta, 0)  # price can't be negative
            ml_applied = True
            reason = "ML_EXPAND_DOWN"

        elif direction == "TIGHTEN":
            delta = min(abs(suggested), max_tighten)
            adjusted_low = low + delta
            adjusted_high = high - delta
            ml_applied = True
            reason = "ML_TIGHTEN"

        else:
            reason = "ML_NEUTRAL"

    return {
        "low": round(adjusted_low, 2),
        "high": round(adjusted_high, 2),
        "ml_applied": ml_applied,
        "reason": reason,
    }
