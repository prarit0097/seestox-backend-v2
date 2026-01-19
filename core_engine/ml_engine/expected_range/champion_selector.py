# core_engine/ml_engine/expected_range/champion_selector.py
# ER-5.1 - CHAMPION MODEL SELECTION (PHASE-1)

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple

from core_engine.ml_engine.range_error_aggregator import aggregate_range_errors
from core_engine.ml_engine.expected_range.model_registry import get_all_models
from core_engine.prediction_history import load_history_any

logger = logging.getLogger("core_engine.ml_engine.expected_range.champion_selector")

# ==================================================
# PATH
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAMPION_FILE = os.path.join(BASE_DIR, "champion.json")

MIN_SAMPLES = 20  # minimum samples required
MIN_SAMPLES_FOR_CHAMPION = 50
CHAMPION_LOCK_DAYS = 7


# ==================================================
# SCORING LOGIC
# ==================================================

def _calculate_score(stats: dict) -> float:
    """
    Champion scoring formula (Phase-1)
    Higher score = better model
    """

    hit_rate = stats.get("hit_rate", 0)
    avg_error = stats.get("avg_error", 0)
    upper_bias = abs(stats.get("upper_bias", 0))
    lower_bias = abs(stats.get("lower_bias", 0))

    score = (
        (hit_rate * 0.6)
        - (avg_error * 0.3)
        - (abs(upper_bias - lower_bias) * 0.1)
    )

    return round(score, 4)


def _compute_hit_rate() -> Tuple[float, int, int]:
    history, _, _ = load_history_any()
    evaluated_total = 0
    inside_range = 0

    for record in history:
        if not isinstance(record, dict):
            continue

        expected = record.get("expected_range")
        actual_close = record.get("actual_close")
        if not isinstance(expected, dict):
            continue
        if expected.get("low") is None or expected.get("high") is None:
            continue
        if actual_close is None:
            continue

        try:
            low = float(expected.get("low"))
            high = float(expected.get("high"))
            actual = float(actual_close)
        except Exception:
            continue

        evaluated_total += 1
        if low <= actual <= high:
            inside_range += 1

    hit_rate = (inside_range / evaluated_total) if evaluated_total else 0.0
    return hit_rate, evaluated_total, inside_range


def _read_existing_champion() -> Dict | None:
    if not os.path.exists(CHAMPION_FILE):
        return None
    try:
        with open(CHAMPION_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _lock_active(updated_on: str) -> bool:
    if not updated_on:
        return False
    try:
        updated_at = datetime.fromisoformat(updated_on)
    except Exception:
        return False
    return datetime.now() < (updated_at + timedelta(days=CHAMPION_LOCK_DAYS))


# ==================================================
# CHAMPION SELECTION
# ==================================================

def select_champion(scorecard: Dict) -> Dict:
    """
    Select best Expected Range models (LOW & HIGH)
    based on historical accuracy.
    """

    available_models = get_all_models()

    if not scorecard or not available_models:
        return {
            "status": "NO_DATA",
            "note": "Insufficient data or models not loaded",
        }

    best_pair = None
    best_score = float("-inf")
    best_hit = -1.0
    best_mae = float("inf")

    for pair, stats in scorecard.items():
        low_name = f"{pair}_low"
        high_name = f"{pair}_high"
        if low_name not in available_models or high_name not in available_models:
            continue

        hit_rate = float(stats.get("hit_rate", 0))
        mae = float(stats.get("mae", float("inf")))

        # Composite score: scale hit_rate (0-1) to 0-100 so MAE can influence selection.
        score = (hit_rate * 100.0) - (mae * 1.0)

        if (
            score > best_score
            or (
                score == best_score
                and (hit_rate > best_hit or (hit_rate == best_hit and mae < best_mae))
            )
        ):
            best_pair = (low_name, high_name)
            best_score = score
            best_hit = hit_rate
            best_mae = mae

    if not best_pair:
        return {
            "status": "NO_MODELS",
            "note": "Expected range models not found",
        }

    hit_rate, evaluated_total, inside_range = _compute_hit_rate()

    existing = _read_existing_champion()
    if existing and _lock_active(existing.get("updated_on")):
        existing_mae = existing.get("mae")
        try:
            existing_mae = float(existing_mae)
        except Exception:
            existing_mae = float("inf")

        improved = (
            evaluated_total >= MIN_SAMPLES_FOR_CHAMPION
            and best_mae <= (existing_mae * 0.9)
        )
        if not improved:
            logger.info(
                "Champion lock active; kept existing champion. evaluated_total=%s hit_rate=%.4f mae=%.4f",
                evaluated_total,
                hit_rate,
                best_mae,
            )
            return {
                "status": "CHAMPION_LOCKED",
                **existing,
            }

    if evaluated_total < MIN_SAMPLES_FOR_CHAMPION and existing:
        logger.info(
            "Insufficient samples for champion switch. evaluated_total=%s hit_rate=%.4f mae=%.4f",
            evaluated_total,
            hit_rate,
            best_mae,
        )
        return {
            "status": "CHAMPION_LOCKED",
            **existing,
        }

    champion_low, champion_high = best_pair

    champion_data = {
        "champion_low": champion_low,
        "champion_high": champion_high,
        "hit_rate": round(hit_rate, 4),
        "mae": round(best_mae, 4),
        "updated_on": datetime.now().isoformat(),
        "note": "GLOBAL_CHAMPION",
    }

    logger.info(
        "Expected range champion selected: %s/%s (evaluated=%s inside=%s hit_rate=%.4f mae=%.4f)",
        champion_low,
        champion_high,
        evaluated_total,
        inside_range,
        hit_rate,
        best_mae,
    )

    with open(CHAMPION_FILE, "w") as f:
        json.dump(champion_data, f, indent=2)

    return {
        "status": "CHAMPION_SELECTED",
        **champion_data,
    }


# ==================================================
# LOAD CHAMPION
# ==================================================

def load_champion() -> Dict:
    if not os.path.exists(CHAMPION_FILE):
        return {
            "status": "NO_CHAMPION",
            "note": "Champion not selected yet",
        }

    try:
        with open(CHAMPION_FILE, "r") as f:
            data = json.load(f)
            return {
                "status": "READY",
                **data,
            }
    except Exception:
        return {
            "status": "ERROR",
            "note": "Failed to load champion file",
        }
