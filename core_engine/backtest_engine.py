# core_engine/backtest_engine.py

def evaluate_historical_confidence(df):
    """
    Historical confidence calculator
    Logic:
    - Close price increase = SUCCESS
    - Close price decrease = FAILURE
    - No change = NEUTRAL
    """

    # Safety checks
    if df is None or df.empty or len(df) < 10:
        return {
            "success_rate": 0,
            "failure_rate": 0,
            "neutral_rate": 0,
            "sample_size": 0,
            "verdict": "INSUFFICIENT_DATA"
        }

    closes = df["Close"].values

    success = 0
    failure = 0
    neutral = 0

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]

        if diff > 0:
            success += 1
        elif diff < 0:
            failure += 1
        else:
            neutral += 1

    total = success + failure + neutral

    # Avoid division errors
    if total == 0:
        return {
            "success_rate": 0,
            "failure_rate": 0,
            "neutral_rate": 0,
            "sample_size": 0,
            "verdict": "INSUFFICIENT_DATA"
        }

    success_rate = round((success / total) * 100)
    failure_rate = round((failure / total) * 100)
    neutral_rate = round((neutral / total) * 100)

    # Verdict logic
    if success_rate >= 65:
        verdict = "STRONG_SETUP"
    elif success_rate >= 50:
        verdict = "AVERAGE_SETUP"
    else:
        verdict = "WEAK_SETUP"

    return {
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "neutral_rate": neutral_rate,
        "sample_size": total,
        "verdict": verdict
    }
