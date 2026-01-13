# core_engine/analyzer.py
# PHASE-2E.6 — RULE + ML-WIRED ANALYZER (SAFE MODE)

from core_engine.data_fetch import fetch_stock_data
from core_engine.trend_engine import analyze_trend
from core_engine.sentiment_engine import analyze_sentiment
from core_engine.risk_engine import analyze_risk
from core_engine.prediction_engine import predict_next_day
from core_engine.confidence_engine import calculate_confidence
from core_engine.prediction_history import store_prediction
from core_engine.symbol_resolver import resolve_symbol
from core_engine.ml_engine.confidence import (
    load_confidence_champion,
    predict_confidence_with_champion,
)


# RULE ENGINE
from core_engine.range_engine import calculate_base_range

# ML ENGINE (SAFE MODE)
from core_engine.ml_engine.er_ml_adjuster import adjust_expected_range

# 🔥 ER-5.2 CHAMPION PREDICTOR (MANDATORY ADDITION)
from core_engine.ml_engine.expected_range.champion_predictor import (
    predict_expected_range_with_champion
)

# 🔥 FEATURE ENCODER (MANDATORY ADDITION)
from core_engine.ml_engine.expected_range.feature_encoder import encode_single_features


def analyze_stock(symbol: str) -> dict:
    resolved = resolve_symbol(symbol)
    if not resolved:
        raise ValueError("Unknown symbol")
    resolved_symbol, company_name = resolved

    # -----------------------------
    # 1. Fetch Historical Data
    # -----------------------------
    df = fetch_stock_data(resolved_symbol)
    df.attrs["symbol"] = resolved_symbol

    if df is None or len(df) == 0 or "Close" not in df.columns:
        raise ValueError("Invalid historical data")

    close_val = df["Close"].iloc[-1]
    current_price = float(close_val.values[0]) if hasattr(close_val, "values") else float(close_val)

    # -----------------------------
    # 2. Trend Analysis
    # -----------------------------
    trend_raw = analyze_trend(df)
    trend_block = {
        "trend": trend_raw.get("trend", "SIDEWAYS"),
        "strength": round(float(trend_raw.get("strength", 0.0)), 2),
        "volume_trend": trend_raw.get("volume_trend", "STABLE"),
        "support": round(float(trend_raw.get("support", current_price * 0.95)), 2),
        "resistance": round(float(trend_raw.get("resistance", current_price * 1.05)), 2),
    }

    # -----------------------------
    # 3. Sentiment
    # -----------------------------
    sentiment_raw = analyze_sentiment(symbol)

    sentiment_overall = sentiment_raw.get("overall", "NEUTRAL")
    sentiment_confidence = int(sentiment_raw.get("confidence", 0))
    sentiment_score = sentiment_raw.get("score", 0.0)

    if trend_block["trend"] == "DOWNTREND":
        if sentiment_overall == "POSITIVE":
            sentiment_overall = "POSITIVE_WEAK"
            sentiment_confidence = min(sentiment_confidence, 40)
        elif sentiment_overall == "POSITIVE_WEAK":
            sentiment_overall = "NEUTRAL"
            sentiment_confidence = min(sentiment_confidence, 25)

    sentiment_block = {
        "overall": sentiment_overall,
        "confidence": sentiment_confidence,
        "score": sentiment_score,
        "why": sentiment_raw.get("why", ""),
        "trend_7d": sentiment_raw.get("trend_7d", 0.0),
        "headlines": sentiment_raw.get("headlines", []),
    }

    # -----------------------------
    # 4. Risk
    # -----------------------------
    risk_raw = analyze_risk(df, trend_block)
    risk_block = {
        "risk_level": risk_raw.get("risk_level", "LOW"),
        "risk_score": int(risk_raw.get("risk_score", 0)),
    }

    # -----------------------------
    # 5. Direction
    # -----------------------------
    prediction_raw = predict_next_day(df)
    up = int(prediction_raw.get("up_probability", 33))
    down = int(prediction_raw.get("down_probability", 33))
    sideways = max(0, 100 - (up + down))

    # -----------------------------
    # 6. Expected Range (RULE → ML → CHAMPION)
    # -----------------------------
    range_data = calculate_base_range(df, current_price)

    adjusted_range = adjust_expected_range(
        symbol=resolved_symbol,
        base_range={
            "low": range_data["base_low"],
            "high": range_data["base_high"],
        },
    )

    # 🔥 FEATURE VECTOR (MANDATORY)
    features = encode_single_features(
        df=df,
        trend=trend_block,
        sentiment=sentiment_block,
        risk=risk_block,
        base_range=adjusted_range,
    )

    # 🔥 CHAMPION PREDICTION (SAFE)
    champion_range = predict_expected_range_with_champion(
        symbol=resolved_symbol,
        features=features,
        fallback_range=adjusted_range,
    )

    final_low = champion_range["low"]
    final_high = champion_range["high"]

    ml_applied = champion_range.get("ml_applied", False)
    ml_reason = champion_range.get("reason", "RULE_ONLY")

    # -----------------------------
    # 7. Context (PERSISTENCE TRUTH)
    # -----------------------------
    context = {
        "price": current_price,
        "trend": trend_block["trend"],
        "sentiment": sentiment_block["overall"],
        "risk": risk_block["risk_level"],
        "volatility_regime": range_data.get("volatility_regime"),
        "atr": range_data.get("atr"),
        "ml_applied": ml_applied,
        "ml_reason": ml_reason,
    }

    # -----------------------------
    # 8. Store Prediction
    # -----------------------------
    store_prediction(
        symbol=resolved_symbol,
        prediction={
            "tomorrow": {
                "up_probability": up,
                "down_probability": down,
                "sideways_probability": sideways,
                "expected_range": {
                    "low": final_low,
                    "high": final_high,
                },
            }
        },
        context=context,
    )

    # -----------------------------
    # 9. Prediction Block (UI TRUTH)
    # -----------------------------
    prediction_block = {
        "tomorrow": {
            "up_probability": up,
            "sideways_probability": sideways,
            "down_probability": down,
            "expected_range": f"Rs {final_low} - Rs {final_high}",
            "ml_applied": ml_applied,
            "ml_reason": ml_reason,
        }
    }

    # -----------------------------
    # 10. Confidence
    # -----------------------------
    confidence_raw = calculate_confidence(df)
    confidence_block = {
        "success_rate": confidence_raw["success_rate"],
        "failure_rate": confidence_raw["failure_rate"],
        "neutral_rate": confidence_raw["neutral_rate"],
        "sample_size": confidence_raw["sample_size"],
        "verdict": confidence_raw["verdict"],
    }

    # ---- CONFIDENCE ML (SAFE MODE) ----
    champion = load_confidence_champion(resolved_symbol)

    if champion.get("status") == "ACTIVE":
        try:
            ml_pred = predict_confidence_with_champion(
                symbol=resolved_symbol,
                context={
                    "trend": trend_block["trend"],
                    "sentiment": sentiment_block["overall"],
                    "risk": risk_block["risk_score"],
                    "volatility": range_data.get("volatility_regime"),
                },
            )

            confidence_block.update({
                "success_rate": ml_pred["success_rate"],
                "failure_rate": ml_pred["failure_rate"],
                "neutral_rate": 100 - (
                    ml_pred["success_rate"] + ml_pred["failure_rate"]
                ),
                "verdict": ml_pred["verdict"],
                "source": "ML_CHAMPION",
            })

        except Exception:
            # Absolute safety fallback
            confidence_block["source"] = "RULE_FALLBACK"

    # -----------------------------
    # 11. Final Signal
    # -----------------------------
    if (
        trend_block["trend"] == "UPTREND"
        and sentiment_block["overall"] == "POSITIVE"
        and risk_block["risk_score"] <= 30
    ):
        final_signal = "BUY"
    elif trend_block["trend"] == "DOWNTREND" and risk_block["risk_score"] >= 60:
        final_signal = "SELL"
    else:
        final_signal = "WAIT"

    # -----------------------------
    # FINAL RESPONSE
    # -----------------------------
    return {
        "symbol": resolved_symbol,
        "company": f"{company_name} ",
        "current_price": round(current_price, 2),
        "signal": final_signal,
        "trend": trend_block,
        "sentiment": sentiment_block,
        "risk": risk_block,
        "prediction": prediction_block,
        "confidence": confidence_block,
        "context": context,
    }
