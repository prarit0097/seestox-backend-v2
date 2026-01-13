# core_engine/ml_engine/scheduler/daily_scheduler.py
# ER-6 — DAILY ML SCHEDULER (AUTO EVALUATE + LEARN)

import json
import logging
from pathlib import Path
from datetime import datetime

from core_engine.ml_engine.range_error_tracker import evaluate_expected_ranges
from core_engine.ml_engine.range_error_aggregator import aggregate_range_errors
from core_engine.ml_engine.range_bias_learner import learn_range_bias

from core_engine.ml_engine.expected_range.dataset_builder import build_expected_range_dataset
from core_engine.ml_engine.expected_range.feature_encoder import encode_features
from core_engine.ml_engine.expected_range.model_trainer import (
    train_expected_range_models,
    evaluate_expected_range_models,
)
from core_engine.ml_engine.expected_range.model_persistence import save_models
from core_engine.ml_engine.expected_range.model_registry import refresh_registry
from core_engine.ml_engine.expected_range.champion_selector import select_champion

logger = logging.getLogger("core_engine.ml_engine.daily_scheduler")
REPORT_PATH = (
    Path(__file__).resolve().parents[3] / "backend" / "logs" / "ml_cycle_report.jsonl"
)


def run_daily_ml_cycle(symbol: str = None) -> dict:
    """
    Runs full ML learning cycle after market close
    Safe to call once per day
    """

    started_at = datetime.now()
    report = {
        "started_at": started_at.isoformat(),
        "steps": {}
    }
    logger.info("Daily ML cycle started")

    # --------------------------------------------------
    # 1. Evaluate Expected Ranges
    # --------------------------------------------------
    eval_result = evaluate_expected_ranges()
    report["steps"]["evaluation"] = eval_result

    # --------------------------------------------------
    # 2. Aggregate Range Errors
    # --------------------------------------------------
    if symbol:
        agg_result = aggregate_range_errors(symbol)
    else:
        agg_result = {"status": "SKIPPED", "note": "No symbol provided"}

    report["steps"]["aggregation"] = agg_result

    # --------------------------------------------------
    # 3. Learn Bias
    # --------------------------------------------------
    if symbol:
        bias_result = learn_range_bias(symbol)
    else:
        bias_result = {"status": "SKIPPED", "note": "No symbol provided"}

    report["steps"]["bias_learning"] = bias_result

    # --------------------------------------------------
    # 4. Build Dataset
    # --------------------------------------------------
    X, y_low, y_high, expected_lows, expected_highs, actual_closes = (
        build_expected_range_dataset()
    )

    if len(X) == 0:
        report["steps"]["training"] = {
            "status": "NO_DATA",
            "note": "Dataset empty"
        }
        return report

    # --------------------------------------------------
    # 5. Train Models
    # --------------------------------------------------
    train_result = train_expected_range_models(X, y_low, y_high)
    report["steps"]["training"] = train_result["status"]

    models = train_result.get("models", {})
    if models:
        save_models(models, samples=len(X), feature_count=len(X[0]))
        refresh_registry()

    scorecard = evaluate_expected_range_models(
        models,
        X,
        y_low,
        y_high,
        expected_lows,
        expected_highs,
        actual_closes,
    )
    report["steps"]["scoring"] = scorecard

    # --------------------------------------------------
    # 6. Select Champion
    # --------------------------------------------------
    champ_result = select_champion(scorecard)
    report["steps"]["champion"] = champ_result

    completed_at = datetime.now()
    report["completed_at"] = completed_at.isoformat()
    duration_sec = (completed_at - started_at).total_seconds()
    logger.info("Daily ML cycle completed in %.2fs", duration_sec)
    _persist_report(report)
    return report


def _persist_report(report: dict) -> None:
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=True) + "\n")
    except Exception:
        logger.warning("Failed to persist ML cycle report", exc_info=True)
