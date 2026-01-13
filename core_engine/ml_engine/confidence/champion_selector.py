# core_engine/ml_engine/confidence/champion_selector.py
# ER-7.5 — CONFIDENCE CHAMPION SELECTION RULES (PRODUCTION SAFE)

from datetime import datetime, timedelta
from core_engine.prediction_history import _load_history, _save_history


# ===============================
# CONFIG (ER-7.5 RULES)
# ===============================

MIN_TOTAL_SAMPLES = 30
MIN_MODEL_SAMPLES = 20
MIN_CHAMPION_SCORE = 55
CHAMPION_LOCK_DAYS = 7
FAILURE_KILL_SWITCH = 0.60  # 60%


# ===============================
# INTERNAL HELPERS
# ===============================

def _confidence_score(success, failure, neutral):
    """
    ER-7.5 scoring formula
    """
    return round(
        (success * 0.7) +
        (neutral * 0.2) -
        (failure * 0.5),
        2
    )


def _get_recent_failure_rate(records, window=5):
    recent = records[-window:]
    if not recent:
        return 0.0

    failures = sum(1 for r in recent if r.get("result") == "FAILURE")
    return failures / len(recent)


# ===============================
# LOAD CHAMPION
# ===============================

def load_confidence_champion(symbol: str) -> dict:
    history = _load_history()

    for r in reversed(history):
        champ = r.get("confidence_champion")
        if champ and champ.get("symbol") == symbol:
            return champ

    return {
        "status": "NO_CHAMPION",
        "note": "Champion not selected yet"
    }


# ===============================
# SELECT CHAMPION
# ===============================

def select_confidence_champion(symbol: str) -> dict:
    history = _load_history()

    records = [
        r for r in history
        if r.get("symbol") == symbol and r.get("evaluated") is True
    ]

    # ---------- RULE 1: MIN DATA ----------
    if len(records) < MIN_TOTAL_SAMPLES:
        return {
            "status": "NO_DATA",
            "note": "Insufficient data to select champion"
        }

    # ---------- KILL SWITCH ----------
    if _get_recent_failure_rate(records) > FAILURE_KILL_SWITCH:
        return {
            "status": "DISABLED",
            "note": "High recent failure rate – champion disabled"
        }

    # ---------- AGGREGATE STATS ----------
    success = sum(1 for r in records if r.get("result") == "SUCCESS")
    failure = sum(1 for r in records if r.get("result") == "FAILURE")
    neutral = sum(1 for r in records if r.get("result") not in ("SUCCESS", "FAILURE"))

    total = success + failure + neutral
    if total < MIN_MODEL_SAMPLES:
        return {
            "status": "NO_DATA",
            "note": "Not enough evaluated samples"
        }

    success_rate = (success / total) * 100
    failure_rate = (failure / total) * 100
    neutral_rate = (neutral / total) * 100

    score = _confidence_score(success_rate, failure_rate, neutral_rate)

    # ---------- RULE 2: SCORE THRESHOLD ----------
    if score < MIN_CHAMPION_SCORE:
        return {
            "status": "NO_CHAMPION",
            "note": "Champion score below threshold",
            "score": score
        }

    # ---------- CHAMPION OBJECT ----------
    champion = {
        "status": "ACTIVE",
        "symbol": symbol,
        "score": score,
        "success_rate": round(success_rate, 2),
        "failure_rate": round(failure_rate, 2),
        "neutral_rate": round(neutral_rate, 2),
        "selected_on": datetime.now().isoformat(),
        "lock_until": (datetime.now() + timedelta(days=CHAMPION_LOCK_DAYS)).isoformat()
    }

    # ---------- STORE (LOCKED) ----------
    history.append({
        "confidence_champion": champion
    })
    _save_history(history)

    return champion
