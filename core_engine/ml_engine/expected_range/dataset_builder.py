

import os
import json
import logging
from typing import List, Dict, Tuple


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(BASE_DIR)),
    "prediction_history.json"
)

logger = logging.getLogger("core_engine.ml_engine.expected_range.dataset_builder")


def _load_history() -> List[Dict]:
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def build_expected_range_dataset(
    min_records: int = 5
) -> Tuple[List[List[float]], List[float], List[float], List[float], List[float], List[float]]:
    """
    Builds dataset for Expected Range ML.

    Returns:
        X       → feature matrix
        y_low   → deviation from expected_low
        y_high  → deviation from expected_high
    """

    history = _load_history()
    total_records = len(history)
    skip_counts = {
        "missing_evaluated": 0,
        "missing_expected_range": 0,
        "missing_actual_close": 0,
        "missing_context_price": 0,
        "invalid_low_high": 0,
        "range_width_non_positive": 0,
    }

    X: List[List[float]] = []
    y_low: List[float] = []
    y_high: List[float] = []
    expected_lows: List[float] = []
    expected_highs: List[float] = []
    actual_closes: List[float] = []

    for record in history:

        # ---------------------------
        # FILTER CONDITIONS (STRICT)
        # ---------------------------
        if record.get("evaluated") is not True:
            skip_counts["missing_evaluated"] += 1
            continue

        expected = record.get("expected_range")
        actual_close = record.get("actual_close")
        context = record.get("context", {})

        if not isinstance(expected, dict):
            skip_counts["missing_expected_range"] += 1
            continue

        if actual_close is None:
            skip_counts["missing_actual_close"] += 1
            continue

        try:
            expected_low_raw = expected.get("low")
            expected_high_raw = expected.get("high")
            if expected_low_raw is None or expected_high_raw is None:
                skip_counts["invalid_low_high"] += 1
                continue
            expected_low = float(expected_low_raw)
            expected_high = float(expected_high_raw)
            actual_close = float(actual_close)
        except Exception:
            skip_counts["invalid_low_high"] += 1
            continue

        # ---------------------------
        # FEATURE EXTRACTION
        # ---------------------------
        try:
            current_price_raw = context.get("price")
            if current_price_raw is None:
                skip_counts["missing_context_price"] += 1
                continue
            current_price = float(current_price_raw)
            atr = float(context.get("atr", 0.0))
        except Exception:
            skip_counts["missing_context_price"] += 1
            continue

        risk_score_raw = context.get("risk_score", None)
        if risk_score_raw is None:
            risk_score = {
                "LOW": 0,
                "MEDIUM": 1,
                "HIGH": 2,
            }.get(context.get("risk", "LOW"), 0)
        else:
            try:
                risk_score = float(risk_score_raw)
            except Exception:
                risk_score = 0
        if risk_score < 0:
            risk_score = 0
        elif risk_score > 2:
            risk_score = 2

        # Categorical encodings (simple & safe)
        trend = context.get("trend", "SIDEWAYS")
        sentiment = context.get("sentiment", "NEUTRAL")
        volatility = context.get("volatility_regime", "NORMAL")

        trend_code = {
            "UPTREND": 1,
            "DOWNTREND": -1,
            "SIDEWAYS": 0
        }.get(trend, 0)

        sentiment_code = {
            "POSITIVE": 2,
            "POSITIVE_WEAK": 1,
            "NEUTRAL": 0,
            "NEGATIVE": -1,
            "NEGATIVE_STRONG": -2,
        }.get(sentiment, 0)

        volatility_code = {
            "LOW": 0,
            "NORMAL": 1,
            "HIGH": 2
        }.get(volatility, 0)

        range_width = expected_high - expected_low
        if range_width <= 0:
            skip_counts["range_width_non_positive"] += 1
            continue

        # ---------------------------
        # FEATURE VECTOR
        # ---------------------------
        features = [
            current_price,
            atr,
            range_width,
            trend_code,
            risk_score,
            sentiment_code,
            volatility_code,
        ]

        # ---------------------------
        # TARGETS (REGRESSION)
        # ---------------------------
        low_error = actual_close - expected_low
        high_error = actual_close - expected_high

        X.append(features)
        y_low.append(round(low_error, 4))
        y_high.append(round(high_error, 4))
        expected_lows.append(expected_low)
        expected_highs.append(expected_high)
        actual_closes.append(actual_close)

    if len(X) < min_records:
        logger.debug(
            "Expected range dataset summary: total=%s used=%s min_records=%s skipped=%s",
            total_records,
            len(X),
            min_records,
            skip_counts,
        )
        return [], [], [], [], [], []

    logger.debug(
        "Expected range dataset summary: total=%s used=%s min_records=%s skipped=%s",
        total_records,
        len(X),
        min_records,
        skip_counts,
    )
    return X, y_low, y_high, expected_lows, expected_highs, actual_closes
