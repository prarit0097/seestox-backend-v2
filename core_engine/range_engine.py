# core_engine/range_engine.py
# PHASE-3A — RULE BASED EXPECTED RANGE ENGINE (BULLETPROOF)

import numpy as np
import pandas as pd


def _to_1d_array(data) -> np.ndarray:
    """
    Converts Series / DataFrame / list to clean 1D numpy array
    """
    if isinstance(data, pd.DataFrame):
        data = data.iloc[:, 0]
    if isinstance(data, pd.Series):
        data = data.values
    return np.asarray(data, dtype=float)


def _calculate_atr(high, low, close, period: int = 14) -> float:
    """
    ATR using pure numpy (no pandas ambiguity)
    """
    high = _to_1d_array(high)
    low = _to_1d_array(low)
    close = _to_1d_array(close)

    if len(close) < period + 1:
        return 0.0

    prev_close = close[:-1]
    high = high[1:]
    low = low[1:]
    close = close[1:]

    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)

    true_range = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = np.mean(true_range[-period:])

    return float(atr)


def _detect_volatility_regime(close: np.ndarray) -> str:
    """
    Volatility regime detection using numpy only
    """
    if len(close) < 60:
        return "NORMAL"

    returns = np.diff(close) / close[:-1]

    recent_vol = float(np.std(returns[-10:]))
    long_vol = float(np.std(returns[-60:]))

    if long_vol == 0:
        return "NORMAL"

    if recent_vol > long_vol * 1.3:
        return "HIGH"
    elif recent_vol < long_vol * 0.8:
        return "LOW"
    else:
        return "NORMAL"


def calculate_base_range(df: pd.DataFrame, current_price: float) -> dict:
    """
    MAIN RULE-BASED EXPECTED RANGE CALCULATOR
    (Zero pandas ambiguity)
    """

    if df is None or len(df) == 0:
        raise ValueError("Invalid price data for range calculation")

    # Convert everything to numpy
    high = _to_1d_array(df["High"])
    low = _to_1d_array(df["Low"])
    close = _to_1d_array(df["Close"])

    # ATR
    atr = _calculate_atr(high, low, close)

    if atr <= 0 or np.isnan(atr):
        atr = current_price * 0.02  # 2% fallback

    # Volatility regime
    regime = _detect_volatility_regime(close)

    # Factor (RULES)
    factor = 1.0
    if regime == "LOW":
        factor = 0.8
    elif regime == "HIGH":
        factor = 1.2

    base_low = round(current_price - atr * factor, 2)
    base_high = round(current_price + atr * factor, 2)

    if base_low <= 0:
        base_low = round(current_price * 0.95, 2)

    return {
        "base_low": base_low,
        "base_high": base_high,
        "atr": round(float(atr), 2),
        "factor": factor,
        "volatility_regime": regime,
    }
