# core_engine/prediction_evaluator.py
# PHASE-3 - T+1 PREDICTION EVALUATION ENGINE (STABLE)

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

from core_engine.data_fetch import fetch_stock_data
from core_engine.prediction_history import load_history_any, save_history_any


# ==================================================
# CONFIG
# ==================================================

REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "backend" / "logs" / "prediction_evaluator_report.jsonl"
)
logger = logging.getLogger("core_engine.prediction_evaluator")


# ==================================================
# PUBLIC ENTRY (REQUIRED BY SCHEDULER)
# ==================================================

def run_prediction_evaluator():
    """
    Scheduler entry point (MANDATORY).
    """
    started_at = datetime.now()
    logger.info("Prediction Evaluator Started")
    try:
        report = evaluate_predictions()
    except Exception:
        logger.error("Prediction Evaluator failed", exc_info=True)
        report = {"status": "FAILED"}
    report["started_at"] = started_at.isoformat()
    report["completed_at"] = datetime.now().isoformat()
    _persist_report(report)
    logger.info("Evaluation Report: %s", report)
    return report


# ==================================================
# MARKET DATA
# ==================================================

def _get_next_trading_close(symbol: str, prediction_date: str):
    if not prediction_date:
        return None

    try:
        target_date = datetime.strptime(prediction_date, "%Y-%m-%d").date()
    except Exception:
        return None

    try:
        df = fetch_stock_data(symbol, period="6mo")
    except Exception:
        logger.warning("Price fetch failed for %s", symbol, exc_info=True)
        return None

    if df is None or df.empty:
        return None

    date_col = None
    for candidate in ("Date", "date"):
        if candidate in df.columns:
            date_col = candidate
            break

    try:
        if date_col:
            dates = df[date_col]
            dates = dates.dt.date if hasattr(dates, "dt") else dates
            df = df.assign(_date=dates)
            df = df[df["_date"] > target_date]
            if df.empty:
                return None
            df = df.sort_values("_date")
            close_val = df["Close"].iloc[0]
        else:
            close_val = df["Close"].iloc[-1]
        return float(close_val.iloc[0] if hasattr(close_val, "iloc") else close_val)
    except Exception:
        return None


def _parse_prediction_date(record: dict) -> str | None:
    date_val = record.get("date")
    if isinstance(date_val, str) and len(date_val) >= 10:
        return date_val[:10]

    ts = record.get("timestamp")
    if isinstance(ts, str) and len(ts) >= 10:
        return ts[:10]

    return None


def _resolve_expected_range(record: dict) -> dict | None:
    expected = record.get("expected_range")
    if isinstance(expected, dict) and expected.get("low") is not None and expected.get("high") is not None:
        return expected

    prediction = record.get("prediction")
    if isinstance(prediction, dict) and prediction.get("low") is not None and prediction.get("high") is not None:
        return prediction

    nested = None
    if isinstance(prediction, dict):
        nested = prediction.get("expected_range")
    if isinstance(nested, dict) and nested.get("low") is not None and nested.get("high") is not None:
        return nested

    return None


def _ensure_context(record: dict) -> dict:
    context = record.get("context", {})
    if not isinstance(context, dict):
        context = {}

    if context.get("price") is None and record.get("price") is not None:
        context["price"] = record.get("price")
    if context.get("atr") is None and record.get("atr") is not None:
        context["atr"] = record.get("atr")
    if context.get("trend") is None and record.get("trend") is not None:
        context["trend"] = record.get("trend")
    if context.get("sentiment") is None and record.get("sentiment") is not None:
        context["sentiment"] = record.get("sentiment")
    if context.get("risk") is None and record.get("risk") is not None:
        context["risk"] = record.get("risk")
    if context.get("risk_score") is None and record.get("risk_score") is not None:
        context["risk_score"] = record.get("risk_score")
    if context.get("volatility_regime") is None and record.get("volatility_regime") is not None:
        context["volatility_regime"] = record.get("volatility_regime")

    return context


# ==================================================
# CORE EVALUATION LOGIC
# ==================================================

def evaluate_predictions():
    """
    Evaluates all unevaluated predictions in history (T+1 logic).
    Safely ignores broken / legacy records.
    """

    history, container_type, container_data = load_history_any()
    evaluated_now = 0
    skipped = 0
    errors = {}

    for record in history:
        try:
            if not isinstance(record, dict):
                skipped += 1
                continue

            if record.get("evaluated") is True:
                continue

            expected_range = _resolve_expected_range(record)
            if not isinstance(expected_range, dict):
                skipped += 1
                continue

            low = expected_range.get("low")
            high = expected_range.get("high")
            if low is None or high is None:
                skipped += 1
                continue

            symbol = record.get("symbol") or record.get("_symbol_key")
            prediction_date = _parse_prediction_date(record)
            if not symbol:
                skipped += 1
                continue

            actual_close = record.get("actual_close")
            if actual_close is None:
                actual_close = record.get("close")
            if actual_close is None:
                actual_close = record.get("actual")
            if actual_close is None:
                actual_close = _get_next_trading_close(symbol, prediction_date)
            if actual_close is None:
                skipped += 1
                continue

            try:
                low_val = float(low)
                high_val = float(high)
                actual_close_val = float(actual_close)
            except Exception:
                skipped += 1
                continue

            if low_val <= actual_close_val <= high_val:
                result = "INSIDE_RANGE"
                range_error = 0.0
            elif actual_close_val > high_val:
                result = "ABOVE_RANGE"
                range_error = abs(actual_close_val - high_val)
            else:
                result = "BELOW_RANGE"
                range_error = abs(actual_close_val - low_val)

            record["expected_range"] = {
                "low": low_val,
                "high": high_val,
            }
            record["actual_close"] = round(actual_close_val, 2)
            record["range_error"] = round(range_error, 2)
            record["evaluated"] = True
            record["evaluated_on"] = datetime.now().isoformat()
            record["result"] = result

            if record.get("outcome") != result:
                record["outcome"] = result

            context = _ensure_context(record)
            record["context"] = context

            evaluated_now += 1

        except Exception as exc:
            key = record.get("symbol") or record.get("_symbol_key") or "UNKNOWN"
            errors[key] = str(exc)
            skipped += 1

    save_history_any(history, container_type, container_data)

    return {
        "status": "OK",
        "total": len(history),
        "evaluated_now": evaluated_now,
        "skipped": skipped,
        "errors": errors,
    }


def _persist_report(report: dict) -> None:
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=True) + "\n")
    except Exception:
        logger.warning("Failed to persist evaluation report", exc_info=True)


# ==================================================
# MANUAL RUN SUPPORT
# ==================================================

if __name__ == "__main__":
    run_prediction_evaluator()
