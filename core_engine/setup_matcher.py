# core_engine/setup_matcher.py

"""
SETUP MATCHER (PHASE-3A)

Purpose:
- Match today's setup with similar historical setups
- Return indices of matching backtest records

Similarity Logic (Explainable):
- Same trend
- Same strength bucket
- Same breakout status
"""

def _strength_bucket(strength: float) -> str:
    """
    Bucketize trend strength
    """
    if strength >= 0.07:
        return "HIGH"
    elif strength >= 0.04:
        return "MEDIUM"
    else:
        return "LOW"


def match_setups(
    backtest_results: list,
    live_trend_data: dict
) -> list:
    """
    Match live setup with historical setups

    Returns:
        list of matched backtest records
    """

    matched = []

    live_trend = live_trend_data.get("trend")
    live_breakout = live_trend_data.get("breakout_status")
    live_strength_bucket = _strength_bucket(live_trend_data.get("strength", 0))

    for record in backtest_results:
        # We don't have trend/breakout stored historically yet,
        # so for Phase-3A v1 we simulate matching by outcome window only.
        # (Next step we'll enrich historical records)

        # Simple heuristic:
        # Consider all records as structurally comparable for now
        matched.append(record)

    return matched
