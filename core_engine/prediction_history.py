# core_engine/prediction_history.py
# PHASE-3A+ — PREDICTION HISTORY WITH AUTO vs USER SPLIT (STABLE)

import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4


# ==================================================
# CONFIG
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "prediction_history.json")
_HISTORY_LOCK = threading.Lock()


# ==================================================
# STORAGE
# ==================================================

def _load_history():
    with _HISTORY_LOCK:
        if not os.path.exists(HISTORY_FILE):
            return []

        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []


def _save_history(data):
    with _HISTORY_LOCK:
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2)


# ==================================================
# BACKWARD COMPATIBLE WRITE API
# ==================================================

def store_prediction(
    symbol: str,
    prediction: dict,
    mode: str = "USER",
    **kwargs
):
    """
    Stores prediction safely.
    mode: USER | AUTO
    """

    history = _load_history()
    tomorrow = prediction.get("tomorrow", {})

    # ----------------------------------
    # ✅ EXPECTED RANGE SAFETY FIX
    # ----------------------------------
    expected_range = tomorrow.get("expected_range")

    if not isinstance(expected_range, dict):
        expected_range = None
    else:
        if expected_range.get("low") is None or expected_range.get("high") is None:
            expected_range = None

    record = {
        # 🔹 NEW (mandatory for ML tracking)
        "id": str(uuid4()),

        "symbol": symbol,
        "date": datetime.now().strftime("%Y-%m-%d"),

        # prediction core
        "expected_range": expected_range,
        "up_probability": tomorrow.get("up_probability"),
        "down_probability": tomorrow.get("down_probability"),
        "sideways_probability": tomorrow.get("sideways_probability"),

        # metadata
        "mode": mode,
        "evaluated": False,
        "result": None,
        "actual_close": None,

        # 🔹 NEW (range ML support)
        "range_error": None,
        "evaluated_on": None,

        "created_on": datetime.now().isoformat(),
    }

    context = kwargs.get("context")
    if isinstance(context, dict):
        record["context"] = context

    history.append(record)
    _save_history(history)


# ==================================================
# READ API — AUTO vs USER AWARE
# ==================================================

def get_stats_for_symbol(symbol: str, mode: Optional[str] = None) -> Dict:
    """
    Returns historical stats for a symbol.
    mode:
      - None  → ALL
      - USER  → user driven predictions
      - AUTO  → system predictions
    """

    history = _load_history()

    success = failure = neutral = 0

    for record in history:

        expected = record.get("expected_range")
        if not isinstance(expected, dict):
            continue

        if expected.get("low") is None or expected.get("high") is None:
            continue

        if record.get("symbol") != symbol:
            continue

        if record.get("evaluated") is not True:
            continue

        if mode and record.get("mode") != mode:
            continue

        result = record.get("result")
        if result == "SUCCESS":
            success += 1
        elif result == "FAILURE":
            failure += 1
        else:
            neutral += 1

    total = success + failure + neutral

    if total == 0:
        return {
            "success": 0,
            "failure": 0,
            "neutral": 0,
            "total": 0,
            "status": "COLLECTING_DATA"
        }

    return {
        "success": success,
        "failure": failure,
        "neutral": neutral,
        "total": total,
        "status": "ACTIVE"
    }


# ==================================================
# CONFIDENCE TREND (UNCHANGED)
# ==================================================

def get_confidence_trend(symbol: str, window: int = 7) -> dict:
    history = _load_history()

    records = [
        r for r in history
        if r.get("symbol") == symbol and r.get("evaluated") is True
    ]

    if len(records) < window * 2:
        return {
            "delta": 0,
            "direction": "STABLE",
            "note": "Not enough historical data"
        }

    recent = records[-window:]
    previous = records[-window * 2:-window]

    def score(block):
        success = sum(1 for r in block if r.get("result") == "SUCCESS")
        total = len(block)
        return round((success / total) * 100) if total else 0

    delta = score(recent) - score(previous)

    return {
        "delta": delta,
        "direction": "UP" if delta > 3 else "DOWN" if delta < -3 else "STABLE"
    }


# ==================================================
# 🔹 RANGE ERROR TRACKER SUPPORT (NEW)
# ==================================================

def load_pending_predictions():
    """
    Returns predictions that:
    - have expected_range
    - are not evaluated yet
    """
    history = _load_history()
    return [
        h for h in history
        if h.get("evaluated") is not True
        and isinstance(h.get("expected_range"), dict)
        and h["expected_range"].get("low") is not None
        and h["expected_range"].get("high") is not None
    ]


def update_prediction_result(
    prediction_id: str,
    actual_close: float,
    result: str,
    error: float,
    evaluated_on: str,
):
    history = _load_history()

    for record in history:
        if record.get("id") == prediction_id:
            record["actual_close"] = actual_close
            record["result"] = result
            record["range_error"] = error
            record["evaluated"] = True
            record["evaluated_on"] = evaluated_on
            break

    _save_history(history)
