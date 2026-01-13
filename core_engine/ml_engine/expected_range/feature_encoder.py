# core_engine/ml_engine/expected_range/feature_encoder.py
# ER-3.2 — FEATURE ENCODER (MODEL AGNOSTIC)

from typing import List, Dict, Tuple
import numpy as np


# ===============================
# ENCODING MAPS (RULE BASED)
# ===============================

TREND_MAP = {
    "UPTREND": 1,
    "SIDEWAYS": 0,
    "DOWNTREND": -1,
}

SENTIMENT_MAP = {
    "POSITIVE": 2,
    "POSITIVE_WEAK": 1,
    "NEUTRAL": 0,
    "NEGATIVE": -1,
    "NEGATIVE_STRONG": -2,
}

RISK_MAP = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
}

VOLATILITY_MAP = {
    "LOW": 0,
    "NORMAL": 1,
    "HIGH": 2,
}


# ===============================
# CORE ENCODER
# ===============================

def encode_features(records: List[Dict]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Converts prediction_history records into ML-ready arrays

    Returns:
        X       -> feature matrix
        y_low   -> target low error
        y_high  -> target high error
    """

    X = []
    y_low = []
    y_high = []

    for r in records:
        try:
            context = r.get("context", {})
            expected = r.get("expected_range", {})

            price = float(context.get("price", 0))
            atr = float(context.get("atr", 0))

            low = float(expected.get("low", 0))
            high = float(expected.get("high", 0))
            actual = float(r.get("actual_close", 0))

            if price <= 0 or atr <= 0 or actual <= 0:
                continue

            # ---------------------------
            # FEATURE ENGINEERING
            # ---------------------------
            range_width = high - low

            trend_enc = TREND_MAP.get(context.get("trend"), 0)
            sentiment_enc = SENTIMENT_MAP.get(context.get("sentiment"), 0)
            risk_enc = RISK_MAP.get(context.get("risk"), 1)
            vol_enc = VOLATILITY_MAP.get(context.get("volatility_regime"), 1)

            features = [
                price,
                atr,
                range_width,
                trend_enc,
                sentiment_enc,
                risk_enc,
                vol_enc,
            ]

            # ---------------------------
            # TARGETS (ERRORS)
            # ---------------------------
            low_error = actual - low
            high_error = actual - high

            X.append(features)
            y_low.append(low_error)
            y_high.append(high_error)

        except Exception:
            # Hard safety — skip bad record
            continue

    return (
        np.array(X, dtype=float).reshape(-1, 7),
        np.array(y_low, dtype=float),
        np.array(y_high, dtype=float),
    )

# --------------------------------------
# ER-5.2 — SINGLE STOCK FEATURE ENCODER
# (MANDATORY for Analyzer wiring)
# --------------------------------------

def encode_single_features(df, trend, sentiment, risk, base_range):
    """
    Convert live stock state into feature vector
    Order MUST match training dataset
    """

    close_value = df["Close"].iloc[-1]
    close_price = float(close_value.iloc[0]) if hasattr(close_value, "iloc") else float(close_value)

    trend_enc = TREND_MAP.get(trend.get("trend"), 0)
    sentiment_enc = SENTIMENT_MAP.get(sentiment.get("overall"), 0)
    risk_enc = RISK_MAP.get(risk.get("risk_level"), 1)
    vol_enc = VOLATILITY_MAP.get(base_range.get("volatility_regime"), 1)

    return [
        close_price,                          # price
        float(base_range.get("atr", 0.0)),    # atr
        float(base_range["high"] - base_range["low"]),  # range width
        trend_enc,                            # trend
        sentiment_enc,                        # sentiment
        risk_enc,                             # risk
        vol_enc,                              # volatility
    ]
