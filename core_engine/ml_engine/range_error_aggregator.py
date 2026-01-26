# core_engine/ml_engine/range_error_aggregator.py
# PHASE-3C — RANGE ERROR AGGREGATION (SYMBOL WISE)

from collections import defaultdict
from core_engine.prediction_history import _load_history


def aggregate_range_errors(symbol: str | None = None):
    """
    Aggregates historical range errors.
    If symbol is None → aggregates ALL symbols.
    """

    history = _load_history()

    stats = defaultdict(lambda: {
        "count": 0,
        "total_error": 0.0,
        "upper_breaks": 0,
        "lower_breaks": 0,
        "inside_hits": 0,
    })

    for record in history:
        if not isinstance(record, dict):
            continue
        if record.get("evaluated") is not True:
            continue

        if record.get("range_error") is None:
            continue

        sym = record.get("symbol")
        if not sym:
            continue

        if symbol and sym != symbol:
            continue

        result = record.get("result")
        error = float(record.get("range_error", 0))

        stats[sym]["count"] += 1
        stats[sym]["total_error"] += error

        if result == "UPPER_BREAK":
            stats[sym]["upper_breaks"] += 1
        elif result == "LOWER_BREAK":
            stats[sym]["lower_breaks"] += 1
        else:
            stats[sym]["inside_hits"] += 1

    # -------- Final metrics --------
    final = {}

    for sym, s in stats.items():
        count = s["count"]
        if count == 0:
            continue

        final[sym] = {
            "samples": count,
            "avg_error": round(s["total_error"] / count, 2),
            "upper_bias": round(s["upper_breaks"] / count, 2),
            "lower_bias": round(s["lower_breaks"] / count, 2),
            "hit_rate": round(s["inside_hits"] / count, 2),
        }

    return final
