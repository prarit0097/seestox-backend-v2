# core_engine/prediction_engine.py
# PHASE-2P.2 — FUTURE-SAFE, WARNING-FREE PREDICTION ENGINE

import numpy as np
import pandas as pd


def predict_next_day(df: pd.DataFrame) -> dict:
    """
    Lightweight next-day prediction based on:
    - Recent momentum
    - Recent volatility
    - No ML (safe & deterministic)

    Returns EXACT structure expected by analyzer.
    """

    if df is None or df.empty or "Close" not in df.columns:
        return _neutral_prediction(df)

    close_series = df["Close"]

    if len(close_series) < 6:
        return _neutral_prediction(df)

    # ✅ SAFE scalar extraction
    current_price = close_series.iloc[-1].item()

    # -----------------------------
    # MOMENTUM (LAST 5 CANDLES)
    # -----------------------------
    returns = close_series.pct_change().dropna()

    if returns.empty:
        return _neutral_prediction(df)

    recent_returns = returns.tail(5)
    momentum_score = recent_returns.mean().item()

    # -----------------------------
    # VOLATILITY (LAST 10 CANDLES)
    # -----------------------------
    recent_slice = returns.tail(10)

    if recent_slice.empty:
        recent_volatility = 0.01
    else:
        recent_volatility = recent_slice.std().item()

    if np.isnan(recent_volatility) or recent_volatility <= 0:
        recent_volatility = 0.01

    # -----------------------------
    # DIRECTIONAL BIAS
    # -----------------------------
    if momentum_score > 0.002:
        up_prob = 45
        down_prob = 25
    elif momentum_score < -0.002:
        up_prob = 25
        down_prob = 45
    else:
        up_prob = 33
        down_prob = 33

    # -----------------------------
    # EXPECTED RANGE
    # -----------------------------
    range_pct = max(0.005, min(0.03, recent_volatility * 2))

    low = round(current_price * (1 - range_pct), 2)
    high = round(current_price * (1 + range_pct), 2)

    return {
        "up_probability": int(up_prob),
        "down_probability": int(down_prob),
        "low": low,
        "high": high
    }


# ==================================================
# FALLBACK
# ==================================================

def _neutral_prediction(df: pd.DataFrame) -> dict:
    try:
        price = df["Close"].iloc[-1].item()
    except Exception:
        price = 0.0

    return {
        "up_probability": 33,
        "down_probability": 33,
        "low": round(price * 0.97, 2),
        "high": round(price * 1.03, 2)
    }
