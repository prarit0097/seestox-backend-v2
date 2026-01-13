# core_engine/ml_engine/range_error_tracker.py
# PHASE-3B — RANGE ERROR TRACKING (LIVE WIRING | BACKWARD SAFE)

from datetime import datetime
from core_engine.data_fetch import fetch_stock_data
from core_engine.prediction_history import (
    load_pending_predictions,
    update_prediction_result,
)


def evaluate_expected_ranges():
    """
    Evaluate all pending Expected Range predictions
    against actual market close.

    Backward-safe:
    - Legacy records without `id` are skipped silently
    """

    pending_predictions = load_pending_predictions()

    if not pending_predictions:
        return {
            "status": "NO_PENDING_PREDICTIONS",
            "evaluated": 0,
        }

    evaluated = 0

    for pred in pending_predictions:
        try:
            # -------------------------------
            # 🔒 LEGACY SAFETY CHECK
            # -------------------------------
            prediction_id = pred.get("id")
            if not prediction_id:
                # Old record (created before ID system)
                continue

            symbol = pred.get("symbol")
            expected_range = pred.get("expected_range")

            if not symbol or not isinstance(expected_range, dict):
                continue

            expected_low = expected_range.get("low")
            expected_high = expected_range.get("high")

            if expected_low is None or expected_high is None:
                continue

            expected_low = float(expected_low)
            expected_high = float(expected_high)

            # -------------------------------
            # FETCH ACTUAL CLOSE
            # -------------------------------
            df = fetch_stock_data(symbol)
            close_val = df["Close"].iloc[-1]
            actual_close = (
                float(close_val.values[0])
                if hasattr(close_val, "values")
                else float(close_val)
            )

            # -------------------------------
            # RANGE EVALUATION
            # -------------------------------
            if expected_low <= actual_close <= expected_high:
                result = "INSIDE_RANGE"
                error = 0.0

            elif actual_close > expected_high:
                result = "UPPER_BREAK"
                error = round(actual_close - expected_high, 2)

            else:
                result = "LOWER_BREAK"
                error = round(expected_low - actual_close, 2)

            # -------------------------------
            # UPDATE HISTORY (SAFE)
            # -------------------------------
            update_prediction_result(
                prediction_id=prediction_id,
                actual_close=actual_close,
                result=result,
                error=error,
                evaluated_on=datetime.now().isoformat(),
            )

            evaluated += 1

        except Exception as e:
            # Absolute fail-safe: never break pipeline
            print(f"[RangeErrorTracker] Failed for {pred.get('symbol')}: {e}")

    return {
        "status": "EVALUATION_COMPLETE",
        "evaluated": evaluated,
    }


