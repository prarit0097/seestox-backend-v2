# core_engine/prediction_evaluator.py
# PHASE-3 — T+1 PREDICTION EVALUATION ENGINE (STABLE)

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
import yfinance as yf


# ==================================================
# CONFIG
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "prediction_history.json")
REPORT_PATH = (
    Path(__file__).resolve().parents[2] / "backend" / "logs" / "prediction_evaluator_report.jsonl"
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
# STORAGE UTILITIES
# ==================================================

def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ==================================================
# MARKET DATA
# ==================================================

def _get_next_trading_close(symbol: str, prediction_date: str):
    """
    Fetch next available close price after prediction date (India NSE)
    """

    start = datetime.strptime(prediction_date, "%Y-%m-%d") + timedelta(days=1)
    end = start + timedelta(days=6)

    yf_symbol = f"{symbol}.NS"
    try:
        df = yf.download(
            yf_symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False
        )
    except Exception:
        logger.warning("Price fetch failed for %s", yf_symbol, exc_info=True)
        return None

    if df.empty:
        return None

    return float(df["Close"].iloc[0])


# ==================================================
# CORE EVALUATION LOGIC
# ==================================================

def evaluate_predictions():
    """
    Evaluates all unevaluated predictions in history (T+1 logic).
    Safely ignores broken / legacy records.
    """

    history = _load_history()
    evaluated_count = 0
    updated = False

    for record in history:

        # -----------------------------
        # SKIP ALREADY EVALUATED
        # -----------------------------
        if record.get("evaluated") is True:
            continue

        symbol = record.get("symbol")
        prediction_date = record.get("date")
        expected_range = record.get("expected_range")

        # -----------------------------
        # HARD SAFETY CHECKS
        # -----------------------------
        if not symbol or not prediction_date:
            continue

        # -----------------------------
        # AUTO-FILTER BROKEN RECORDS
        # -----------------------------
        if not isinstance(expected_range, dict):
            continue

        low = expected_range.get("low")
        high = expected_range.get("high")

        if low is None or high is None:
            continue

        # -----------------------------
        # FETCH ACTUAL CLOSE (T+1)
        # -----------------------------
        actual_close = _get_next_trading_close(symbol, prediction_date)

        if actual_close is None:
            result = "NEUTRAL"
        elif low <= actual_close <= high:
            result = "SUCCESS"
        else:
            result = "FAILURE"

        # -----------------------------
        # UPDATE RECORD
        # -----------------------------
        record.update({
            "actual_close": round(actual_close, 2) if actual_close else None,
            "result": result,
            "evaluated": True,
            "evaluated_on": datetime.now().strftime("%Y-%m-%d")
        })

        evaluated_count += 1
        updated = True

    if updated:
        _save_history(history)

    return {
        "evaluated_records": evaluated_count,
        "total_records": len(history)
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
