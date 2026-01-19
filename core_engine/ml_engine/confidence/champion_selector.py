# core_engine/ml_engine/confidence/champion_selector.py
# ER-7.5 - CONFIDENCE CHAMPION SELECTION RULES (PRODUCTION SAFE)

import logging
from datetime import datetime, timedelta
from core_engine.prediction_history import _load_history, _save_history


# ===============================
# CONFIG (ER-7.5 RULES)
# ===============================

MIN_TOTAL_SAMPLES = 30
MIN_MODEL_SAMPLES = 20
MIN_CHAMPION_SCORE = 55
MIN_SAMPLES_FOR_CHAMPION = 50
CHAMPION_LOCK_DAYS = 7
FAILURE_KILL_SWITCH = 0.60  # 60%

SUCCESS_TAGS = {"SUCCESS", "INSIDE_RANGE"}
FAILURE_TAGS = {"FAILURE", "UPPER_BREAK", "LOWER_BREAK"}

logger = logging.getLogger("core_engine.ml_engine.confidence.champion_selector")


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


def _normalize_result_tag(result) -> str:
    if not isinstance(result, str):
        return ""
    return result.strip().upper()


def _is_success_result(result) -> bool:
    return _normalize_result_tag(result) in SUCCESS_TAGS


def _is_failure_result(result) -> bool:
    return _normalize_result_tag(result) in FAILURE_TAGS


def _get_recent_failure_rate(records, window=5):
    recent = records[-window:]
    if not recent:
        return 0.0

    failures = sum(1 for r in recent if _is_failure_result(r.get("result")))
    return failures / len(recent)


def _lock_active(updated_on: str) -> bool:
    if not updated_on:
        return False
    try:
        updated_at = datetime.fromisoformat(updated_on)
    except Exception:
        return False
    return datetime.now() < (updated_at + timedelta(days=CHAMPION_LOCK_DAYS))


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

    existing_champion = None
    existing_index = None
    for idx in range(len(history) - 1, -1, -1):
        champ = history[idx].get("confidence_champion")
        if champ and champ.get("symbol") == symbol:
            existing_champion = champ
            existing_index = idx
            break

    records = [
        r for r in history
        if r.get("symbol") == symbol and r.get("evaluated") is True
    ]

    if existing_champion and _lock_active(existing_champion.get("selected_on")):
        if len(records) < MIN_SAMPLES_FOR_CHAMPION:
            logger.info(
                "Confidence champion lock active; kept existing. samples=%s",
                len(records),
            )
            return existing_champion

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
            "note": "High recent failure rate - champion disabled"
        }

    # ---------- AGGREGATE STATS ----------
    success = 0
    failure = 0
    neutral = 0
    for record in records:
        tag = _normalize_result_tag(record.get("result"))
        if tag in SUCCESS_TAGS:
            success += 1
        elif tag in FAILURE_TAGS:
            failure += 1
        else:
            neutral += 1

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

    if existing_champion and _lock_active(existing_champion.get("selected_on")):
        existing_score = existing_champion.get("score")
        try:
            existing_score = float(existing_score)
        except Exception:
            existing_score = None

        improved = (
            len(records) >= MIN_SAMPLES_FOR_CHAMPION
            and existing_score is not None
            and score >= (existing_score * 1.1)
        )
        if not improved:
            logger.info(
                "Confidence champion lock prevented switching. samples=%s score=%.2f",
                len(records),
                score,
            )
            return existing_champion

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

    logger.info(
        "Confidence champion selected: %s samples=%s success=%s failure=%s neutral=%s score=%.2f",
        symbol,
        total,
        success,
        failure,
        neutral,
        score,
    )

    # ---------- STORE (LOCKED) ----------
    if existing_index is not None:
        history[existing_index]["confidence_champion"] = champion
    else:
        history.append({
            "confidence_champion": champion
        })
    _save_history(history)

    return champion
