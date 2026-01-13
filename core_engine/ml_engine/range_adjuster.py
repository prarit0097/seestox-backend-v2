# core_engine/ml_engine/range_adjuster.py
# PHASE-3B.1 — EXPECTED RANGE ML ADJUSTMENT (SAFE MODE)

def adjust_range_with_ml(
    base_low: float,
    base_high: float,
    ml_signal: dict | None = None,
) -> dict:
    """
    ML-assisted adjustment layer (SAFE MODE).

    ml_signal example (future):
    {
        "bias": "UPPER" / "LOWER" / "NONE",
        "strength": 0.0 → 1.0
    }
    """

    base_width = base_high - base_low

    # Hard safety cap (15%)
    max_adjust = base_width * 0.15

    # Default = no adjustment
    adj_low = base_low
    adj_high = base_high

    if not ml_signal:
        return {
            "final_low": round(adj_low, 2),
            "final_high": round(adj_high, 2),
            "ml_applied": False,
        }

    bias = ml_signal.get("bias", "NONE")
    strength = float(ml_signal.get("strength", 0.0))

    strength = max(0.0, min(strength, 1.0))
    delta = min(max_adjust, base_width * strength)

    if bias == "UPPER":
        adj_high += delta
    elif bias == "LOWER":
        adj_low -= delta

    return {
        "final_low": round(adj_low, 2),
        "final_high": round(adj_high, 2),
        "ml_applied": True,
    }
