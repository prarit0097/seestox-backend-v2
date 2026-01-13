def analyze_risk(df, trend, sentiment="neutral"):
    score = 0

    # Trend impact
    if trend.get("trend") == "UPTREND":
        score += 20
    elif trend.get("trend") == "DOWNTREND":
        score += 50

    # Volume impact
    if trend.get("volume_trend") == "DECREASING":
        score += 20

    # Sentiment impact
    if sentiment == "negative":
        score += 30
    elif sentiment == "positive":
        score -= 10

    # Clamp score
    score = max(0, min(score, 100))

    if score >= 70:
        level = "HIGH"
    elif score >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "risk_level": level,
        "risk_score": score
    }
