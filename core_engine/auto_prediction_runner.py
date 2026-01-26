# core_engine/auto_prediction_runner.py

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("core_engine.auto_prediction_runner")
REPORT_PATH = (
    Path(__file__).resolve().parents[2] / "backend" / "logs" / "auto_prediction_report.jsonl"
)


def run_auto_predictions():
    # IMPORT INSIDE FUNCTION (CRITICAL FIX)
    from core_engine.universe import TOP_100_STOCKS
    from core_engine.analyzer import analyze_stock

    started_at = datetime.now()
    report = {
        "started_at": started_at.isoformat(),
        "status": "DONE",
        "success": 0,
        "failed": 0,
        "total": len(TOP_100_STOCKS),
    }

    logger.info("Auto Prediction Runner Started")
    logger.info("Total stocks: %d", len(TOP_100_STOCKS))

    try:
        for symbol in TOP_100_STOCKS:
            logger.info("Processing %s", symbol)
            try:
                analyze_stock(symbol)
                report["success"] += 1
            except Exception:
                report["failed"] += 1
                logger.warning(
                    "Auto prediction failed for %s", symbol, exc_info=True
                )
    except Exception:
        report["status"] = "FAILED"
        logger.error("Auto Prediction Runner failed", exc_info=True)

    report["completed_at"] = datetime.now().isoformat()
    _persist_report(report)
    logger.info(
        "Auto Prediction Runner Completed (success=%d, failed=%d)",
        report["success"],
        report["failed"],
    )


def _persist_report(report: dict) -> None:
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=True) + "\n")
    except Exception:
        logger.warning("Failed to persist auto prediction report", exc_info=True)
