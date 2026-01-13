# core_engine/ml_engine/range_bias_learner.py
# PHASE-3C — RANGE BIAS LEARNER (SAFE ML HEURISTIC)

from core_engine.ml_engine.range_error_aggregator import aggregate_range_errors


def learn_range_bias(symbol: str):
    """
    Learns bias from historical range errors.
    Output is SAFE adjustment hints (not applied directly).
    """

    agg = aggregate_range_errors(symbol)
    data = agg.get(symbol)

    if not data or data["samples"] < 5:
        return {
            "status": "INSUFFICIENT_DATA",
            "adjustment": 0.0,
            "direction": "NONE",
            "note": "Waiting for more samples",
        }

    avg_error = data["avg_error"]
    upper_bias = data["upper_bias"]
    lower_bias = data["lower_bias"]
    hit_rate = data["hit_rate"]

    # -------- Bias logic --------
    if upper_bias > 0.6:
        direction = "EXPAND_UP"
        adjustment = avg_error * 0.6

    elif lower_bias > 0.6:
        direction = "EXPAND_DOWN"
        adjustment = avg_error * 0.6

    elif hit_rate > 0.7:
        direction = "TIGHTEN"
        adjustment = avg_error * -0.3

    else:
        direction = "NEUTRAL"
        adjustment = avg_error * 0.1

    return {
        "status": "READY",
        "samples": data["samples"],
        "avg_error": avg_error,
        "direction": direction,
        "suggested_adjustment": round(adjustment, 2),
    }
