# core_engine/prediction_history.py
# PHASE-3A+ - PREDICTION HISTORY WITH AUTO vs USER SPLIT (STABLE)

import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from uuid import uuid4


# ==================================================
# CONFIG
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "prediction_history.json")
_HISTORY_LOCK = threading.Lock()
_LAST_HISTORY_PATH = None


# ==================================================
# INTERNAL HELPERS
# ==================================================

def _history_candidates() -> List[str]:
    candidates: List[str] = []

    env_path = os.getenv("SEESTOX_PREDICTION_HISTORY_PATH")
    if env_path:
        candidates.append(env_path)

    candidates.append(os.path.join(os.getcwd(), "prediction_history.json"))
    candidates.append(HISTORY_FILE)
    candidates.append(os.path.join(BASE_DIR, "prediction_history.json"))
    candidates.append(os.path.join(BASE_DIR, "ml_engine", "prediction_history.json"))

    # de-dup while preserving order
    seen = set()
    ordered = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _select_history_file() -> Optional[str]:
    candidates = _history_candidates()
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _resolve_history_path() -> str:
    selected = _select_history_file()
    if selected:
        return selected
    return os.path.join(os.getcwd(), "prediction_history.json")


def _strip_internal_fields(record: dict) -> dict:
    cleaned = dict(record)
    cleaned.pop("_symbol_key", None)
    return cleaned


def _record_identity(record: dict) -> Tuple:
    if record.get("timestamp"):
        return ("timestamp", record.get("timestamp"))
    if record.get("date"):
        return ("date", record.get("date"))

    prediction = record.get("prediction", {}) if isinstance(record.get("prediction"), dict) else {}
    return (
        "prediction",
        prediction.get("low"),
        prediction.get("high"),
        record.get("price"),
    )


# ==================================================
# STORAGE
# ==================================================

def _load_history():
    with _HISTORY_LOCK:
        history_path = _resolve_history_path()
        if not os.path.exists(history_path):
            return []

        try:
            with open(history_path, "r") as f:
                return json.load(f)
        except Exception:
            return []


def _save_history(data):
    with _HISTORY_LOCK:
        history_path = _resolve_history_path()
        with open(history_path, "w") as f:
            json.dump(data, f, indent=2)


def load_history_any() -> Tuple[List[Dict], str, object]:
    """
    Loads prediction history from list or dict formats.
    Returns: (flat_records, container_type, container_data)
    """
    global _LAST_HISTORY_PATH
    history_path = _select_history_file()
    _LAST_HISTORY_PATH = history_path

    if not history_path or not os.path.exists(history_path):
        return [], "list", []

    try:
        with _HISTORY_LOCK:
            with open(history_path, "r") as f:
                data = json.load(f)
    except Exception:
        return [], "list", []

    flat_records: List[Dict] = []
    container_type = "list" if isinstance(data, list) else "dict" if isinstance(data, dict) else "list"

    if isinstance(data, list):
        flat_records = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        for symbol_key, records in data.items():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                if not record.get("symbol"):
                    record["_symbol_key"] = symbol_key
                flat_records.append(record)

    evaluated_true = sum(
        1 for r in flat_records
        if isinstance(r, dict) and r.get("evaluated") is True
    )
    return flat_records, container_type, data


def save_history_any(flat_records: List[Dict], container_type: str, container_data) -> None:
    """
    Saves prediction history back into original list/dict format.
    """
    history_path = _LAST_HISTORY_PATH or _select_history_file() or HISTORY_FILE

    if container_type == "list":
        cleaned = [_strip_internal_fields(r) for r in flat_records if isinstance(r, dict)]
        with _HISTORY_LOCK:
            with open(history_path, "w") as f:
                json.dump(cleaned, f, indent=2)
        return

    if not isinstance(container_data, dict):
        return

    # dict format: update records in-place by matching identity within symbol list
    for record in flat_records:
        if not isinstance(record, dict):
            continue
        symbol_key = record.get("_symbol_key") or record.get("symbol")
        if not symbol_key or symbol_key not in container_data:
            continue
        records_list = container_data.get(symbol_key)
        if not isinstance(records_list, list):
            continue
        identity = _record_identity(record)
        cleaned = _strip_internal_fields(record)

        updated = False
        for idx, existing in enumerate(records_list):
            if not isinstance(existing, dict):
                continue
            if _record_identity(existing) == identity:
                existing.update(cleaned)
                records_list[idx] = existing
                updated = True
                break

        if not updated:
            # Avoid creating new keys; append within existing symbol list only
            records_list.append(cleaned)

    with _HISTORY_LOCK:
        with open(history_path, "w") as f:
            json.dump(container_data, f, indent=2)


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

    history, container_type, container_data = load_history_any()
    tomorrow = prediction.get("tomorrow", {})

    # ----------------------------------
    # EXPECTED RANGE SAFETY FIX
    # ----------------------------------
    expected_range = tomorrow.get("expected_range")

    if not isinstance(expected_range, dict):
        expected_range = None
    else:
        if expected_range.get("low") is None or expected_range.get("high") is None:
            expected_range = None

    record = {
        # NEW (mandatory for ML tracking)
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

        # NEW (range ML support)
        "range_error": None,
        "evaluated_on": None,

        "created_on": datetime.now().isoformat(),
    }

    context = kwargs.get("context")
    if isinstance(context, dict):
        record["context"] = context

    history.append(record)
    save_history_any(history, container_type, container_data)


# ==================================================
# READ API - AUTO vs USER AWARE
# ==================================================

def get_stats_for_symbol(symbol: str, mode: Optional[str] = None) -> Dict:
    """
    Returns historical stats for a symbol.
    mode:
      - None  -> ALL
      - USER  -> user driven predictions
      - AUTO  -> system predictions
    """

    history = _load_history()

    success = failure = neutral = 0

    for record in history:
        if not isinstance(record, dict):
            continue
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
# RANGE ERROR TRACKER SUPPORT (NEW)
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
