# core_engine/ml_engine/expected_range/champion_selector.py
# ER-5.1 — CHAMPION MODEL SELECTION (PHASE-1)

import os
import json
import logging
from datetime import datetime
from typing import Dict

from core_engine.ml_engine.range_error_aggregator import aggregate_range_errors
from core_engine.ml_engine.expected_range.model_registry import get_all_models

logger = logging.getLogger("core_engine.ml_engine.expected_range.champion_selector")

# ==================================================
# PATH
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAMPION_FILE = os.path.join(BASE_DIR, "champion.json")

MIN_SAMPLES = 20  # minimum samples required


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

    champion_low, champion_high = best_pair

    champion_data = {
        "champion_low": champion_low,
        "champion_high": champion_high,
        "hit_rate": round(best_hit, 4),
        "mae": round(best_mae, 4),
        "updated_on": datetime.now().isoformat(),
        "note": "GLOBAL_CHAMPION",
    }

    logger.info(
        "Expected range champion selected: %s/%s (score=%.2f hit_rate=%.4f mae=%.4f)",
        champion_low,
        champion_high,
        best_score,
        best_hit,
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
