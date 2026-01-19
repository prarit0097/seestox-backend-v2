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

_LAST_EVAL_RESULT = None


def _dedupe_symbols(symbols: list) -> list[str]:
    cleaned = []
    seen = set()
    for sym in symbols or []:
        if sym is None:
            continue
        if not isinstance(sym, str):
            sym = str(sym)
        sym = sym.strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        cleaned.append(sym)
    return cleaned


def _get_symbols_for_global_cycle() -> list[str]:
    eval_result = _LAST_EVAL_RESULT if isinstance(_LAST_EVAL_RESULT, dict) else {}
    if eval_result:
        for key in ("symbols", "symbol_list", "evaluated_symbols"):
            candidate = eval_result.get(key)
            if isinstance(candidate, list) and candidate:
                symbols = _dedupe_symbols(candidate)
                if symbols:
                    return symbols

    try:
        from core_engine.ml_engine.expected_range.dataset_builder import _load_history as _load_expected_range_history
        history = _load_expected_range_history()
        symbols = _dedupe_symbols([r.get("symbol") for r in history if r.get("symbol")])
        if symbols:
            return symbols
    except Exception:
        logger.debug("Failed to load symbols from expected range history", exc_info=True)

    try:
        from core_engine.universe import TOP_100_STOCKS
        symbols = _dedupe_symbols(TOP_100_STOCKS)
        if symbols:
            return symbols
    except Exception:
        logger.debug("Failed to load symbols from universe list", exc_info=True)

    return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC"]


def _run_global_aggregation_and_bias(symbols: list[str]) -> dict:
    aggregation_report = {
        "status": "GLOBAL_DONE",
        "processed": len(symbols),
        "success": 0,
        "failed": 0,
        "errors": {},
    }
    bias_report = {
        "status": "GLOBAL_DONE",
        "processed": len(symbols),
        "success": 0,
        "failed": 0,
        "errors": {},
    }

    for sym in symbols:
        try:
            aggregate_range_errors(sym)
            aggregation_report["success"] += 1
        except Exception as exc:
            aggregation_report["failed"] += 1
            aggregation_report["errors"][sym] = str(exc)
            logger.warning("Aggregation failed for %s", sym, exc_info=True)

        try:
            learn_range_bias(sym)
            bias_report["success"] += 1
        except Exception as exc:
            bias_report["failed"] += 1
            bias_report["errors"][sym] = str(exc)
            logger.warning("Bias learning failed for %s", sym, exc_info=True)

    return {
        "aggregation": aggregation_report,
        "bias_learning": bias_report,
    }


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
    global _LAST_EVAL_RESULT
    _LAST_EVAL_RESULT = eval_result
    logger.info("Evaluation status: %s", eval_result.get("status"))
    try:
        from core_engine.ml_engine.expected_range.dataset_builder import _load_history as _load_expected_range_history
        history = _load_expected_range_history()
        logger.info("Expected range history size: %s", len(history))
    except Exception:
        logger.debug("Failed to read expected range history size", exc_info=True)

    # --------------------------------------------------
    # 2. Aggregate Range Errors
    # --------------------------------------------------
    global_results = None
    if symbol:
        try:
            agg_result = aggregate_range_errors(symbol)
        except Exception as exc:
            logger.warning("Aggregation failed for %s", symbol, exc_info=True)
            agg_result = {"status": "ERROR", "note": str(exc)}
    else:
        symbols = _get_symbols_for_global_cycle()
        global_results = _run_global_aggregation_and_bias(symbols)
        agg_result = global_results.get("aggregation", {"status": "ERROR", "note": "Aggregation failed"})

    report["steps"]["aggregation"] = agg_result

    # --------------------------------------------------
    # 3. Learn Bias
    # --------------------------------------------------
    if symbol:
        try:
            bias_result = learn_range_bias(symbol)
        except Exception as exc:
            logger.warning("Bias learning failed for %s", symbol, exc_info=True)
            bias_result = {"status": "ERROR", "note": str(exc)}
    else:
        if global_results is None:
            symbols = _get_symbols_for_global_cycle()
            global_results = _run_global_aggregation_and_bias(symbols)
        bias_result = global_results.get("bias_learning", {"status": "ERROR", "note": "Bias learning failed"})

    report["steps"]["bias_learning"] = bias_result

    # --------------------------------------------------
    # 4. Build Dataset
    # --------------------------------------------------
    X, y_low, y_high, expected_lows, expected_highs, actual_closes = (
        build_expected_range_dataset()
    )
    logger.info("Expected range dataset size: %s", len(X))

    if len(X) == 0:
        report["steps"]["training"] = {
            "status": "NO_DATA",
            "note": "Dataset empty"
        }
        report["steps"]["scoring"] = {
            "status": "SKIPPED",
            "note": "Dataset empty"
        }
        report["steps"]["champion"] = {
            "status": "SKIPPED",
            "note": "Dataset empty"
        }
        _persist_report(report)
        return report

    # --------------------------------------------------
    # 5. Train Models
    # --------------------------------------------------
    train_result = train_expected_range_models(X, y_low, y_high)
    report["steps"]["training"] = train_result["status"]

    models = train_result.get("models", {})
    if models:
        logger.info("Trained expected range models: %s", len(models))
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
