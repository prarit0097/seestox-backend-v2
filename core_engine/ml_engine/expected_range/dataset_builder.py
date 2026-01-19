import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple


logger = logging.getLogger("core_engine.ml_engine.expected_range.dataset_builder")


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "manage.py").exists():
            return parent
    return None


def _candidate_paths() -> List[Path]:
    candidates: List[Path] = []

    env_path = os.getenv("SEESTOX_PREDICTION_HISTORY_PATH")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(Path.cwd() / "prediction_history.json")

    repo_root = _find_repo_root()
    if repo_root:
        candidates.append(repo_root / "prediction_history.json")
        candidates.append(repo_root / "core_engine" / "prediction_history.json")
        candidates.append(repo_root / "core_engine" / "ml_engine" / "prediction_history.json")

    return candidates


def _parse_history_file(history_file: Path) -> List[Dict]:
    try:
        with history_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("Failed to load prediction history as JSON: %s", history_file)
        return []

    records: List[Dict] = []
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        records.append(item)
    else:
        logger.warning("Prediction history file has unexpected structure: %s", history_file)
        records = []

    return records


def _load_history() -> List[Dict]:
    candidates = _candidate_paths()
    first_existing_records = None
    first_existing_path = None

    for candidate in candidates:
        if not candidate.exists():
            logger.debug("Prediction history candidate missing: %s", candidate)
            continue

        records = _parse_history_file(candidate)
        evaluated_true = sum(
            1 for record in records
            if isinstance(record, dict) and record.get("evaluated") is True
        )

        if first_existing_records is None:
            first_existing_records = records
            first_existing_path = candidate

        if evaluated_true > 0:
            logger.info(
                "Prediction history selected: %s (records=%s evaluated_true=%s)",
                candidate,
                len(records),
                evaluated_true,
            )
            return records

        logger.debug(
            "Prediction history rejected (no evaluated records): %s",
            candidate,
        )

    if first_existing_records is not None and first_existing_path is not None:
        logger.warning(
            "No evaluated records found; using first existing history file: %s",
            first_existing_path,
        )
        return first_existing_records

    logger.warning("Prediction history file missing: %s", candidates)
    return []


def _resolve_expected_range(record: Dict) -> Dict | None:
    expected = record.get("expected_range")
    if isinstance(expected, dict) and expected.get("low") is not None and expected.get("high") is not None:
        return expected

    prediction = record.get("prediction")
    if isinstance(prediction, dict) and prediction.get("low") is not None and prediction.get("high") is not None:
        return prediction

    nested = None
    if isinstance(prediction, dict):
        nested = prediction.get("expected_range")
    if isinstance(nested, dict) and nested.get("low") is not None and nested.get("high") is not None:
        return nested

    return None


def _resolve_actual_close(record: Dict):
    actual_close = record.get("actual_close")
    if actual_close is None:
        actual_close = record.get("close")
    if actual_close is None:
        actual_close = record.get("actual")
    return actual_close


def _resolve_context(record: Dict) -> Dict:
    context = record.get("context", {})
    if not isinstance(context, dict):
        context = {}
    if context.get("price") is None and record.get("price") is not None:
        context["price"] = record.get("price")
    if context.get("atr") is None and record.get("atr") is not None:
        context["atr"] = record.get("atr")
    if context.get("trend") is None and record.get("trend") is not None:
        context["trend"] = record.get("trend")
    if context.get("sentiment") is None and record.get("sentiment") is not None:
        context["sentiment"] = record.get("sentiment")
    if context.get("risk") is None and record.get("risk") is not None:
        context["risk"] = record.get("risk")
    if context.get("risk_score") is None and record.get("risk_score") is not None:
        context["risk_score"] = record.get("risk_score")
    if context.get("volatility_regime") is None and record.get("volatility_regime") is not None:
        context["volatility_regime"] = record.get("volatility_regime")
    return context


def build_expected_range_dataset(
    min_records: int = 5
) -> Tuple[List[List[float]], List[float], List[float], List[float], List[float], List[float]]:
    """
    Builds dataset for Expected Range ML.

    Returns:
        X       ?+ feature matrix
        y_low   ?+ deviation from expected_low
        y_high  ?+ deviation from expected_high
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
    evaluated_true_count = 0

    X: List[List[float]] = []
    y_low: List[float] = []
    y_high: List[float] = []
    expected_lows: List[float] = []
    expected_highs: List[float] = []
    actual_closes: List[float] = []

    for record in history:
        if not isinstance(record, dict):
            skip_counts["missing_expected_range"] += 1
            continue

        # ---------------------------
        # FILTER CONDITIONS (STRICT)
        # ---------------------------
        if record.get("evaluated") is not True:
            skip_counts["missing_evaluated"] += 1
            continue

        evaluated_true_count += 1

        expected = _resolve_expected_range(record)
        if not isinstance(expected, dict):
            skip_counts["missing_expected_range"] += 1
            continue

        actual_close = _resolve_actual_close(record)
        if actual_close is None:
            skip_counts["missing_actual_close"] += 1
            continue

        context = _resolve_context(record)

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

    logger.debug(
        "Expected range dataset summary: total=%s used=%s evaluated_true=%s min_records=%s skipped=%s",
        total_records,
        len(X),
        evaluated_true_count,
        min_records,
        skip_counts,
    )

    if len(X) < min_records:
        return [], [], [], [], [], []

    return X, y_low, y_high, expected_lows, expected_highs, actual_closes
