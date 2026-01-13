# core_engine/trend_engine.py

import pandas as pd


def analyze_trend(df: pd.DataFrame):
    df = df.copy()

    # Calculate EMAs
    df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()

    # Latest row (Series)
    latest = df.iloc[-1]

    # ✅ EXPLICIT SCALARS (NO Series ANYWHERE)
    ema_20 = latest["EMA_20"].item()
    ema_50 = latest["EMA_50"].item()
    volume = latest["Volume"].item()

    # Trend
    if ema_20 > ema_50:
        trend = "UPTREND"
        strength = round((ema_20 - ema_50) / ema_50, 2)
    elif ema_20 < ema_50:
        trend = "DOWNTREND"
        strength = round((ema_50 - ema_20) / ema_50, 2)
    else:
        trend = "SIDEWAYS"
        strength = 0.0

    # Volume trend
    avg_volume = df["Volume"].tail(5).mean().item()

    if volume > avg_volume:
        volume_trend = "INCREASING"
    elif volume < avg_volume:
        volume_trend = "DECREASING"
    else:
        volume_trend = "FLAT"

    # Support / Resistance
    support = round(df["Low"].tail(20).min().item(), 2)
    resistance = round(df["High"].tail(20).max().item(), 2)

    return {
        "trend": trend,
        "strength": strength,
        "volume_trend": volume_trend,
        "support": support,
        "resistance": resistance,
    }
