# core_engine/auto_prediction_runner.py

import logging

logger = logging.getLogger("core_engine.auto_prediction_runner")


def run_auto_predictions():
    # IMPORT INSIDE FUNCTION (CRITICAL FIX)
    from core_engine.universe import TOP_100_STOCKS
    from core_engine.analyzer import analyze_stock

    logger.info("Auto Prediction Runner Started")
    logger.info("Total stocks: %d", len(TOP_100_STOCKS))

    success = 0
    failed = 0
    for symbol in TOP_100_STOCKS:
        logger.info("Processing %s", symbol)
        try:
            analyze_stock(symbol)
            success += 1
        except Exception:
            failed += 1
            logger.warning(
                "Auto prediction failed for %s", symbol, exc_info=True
            )
    logger.info(
        "Auto Prediction Runner Completed (success=%d, failed=%d)",
        success,
        failed,
    )
