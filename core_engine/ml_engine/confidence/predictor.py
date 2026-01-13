# core_engine/ml_engine/confidence/predictor.py
# ER-7.6 — CONFIDENCE PREDICTION USING CHAMPION (SAFE MODE)

from core_engine.ml_engine.confidence.champion_selector import load_confidence_champion


# ===============================
# PUBLIC API
# ===============================

def predict_confidence_with_champion(symbol: str) -> dict:
    """
    Returns confidence verdict using champion model if available.
    Falls back safely if no champion.
    """

    champion = load_confidence_champion(symbol)

    # ---------- NO CHAMPION ----------
    if not champion or champion.get("status") != "ACTIVE":
        return {
            "ml_used": False,
            "verdict": "UNRELIABLE",
            "reason": champion.get("note", "NO_CHAMPION"),
            "confidence_score": 0,
        }

    score = champion.get("score", 0)

    # ---------- VERDICT MAPPING ----------
    if score >= 75:
        verdict = "RELIABLE"
    elif score >= 65:
        verdict = "MODERATE"
    elif score >= 55:
        verdict = "WEAK"
    else:
        verdict = "UNRELIABLE"

    return {
        "ml_used": True,
        "verdict": verdict,
        "confidence_score": score,
        "success_rate": champion.get("success_rate"),
        "failure_rate": champion.get("failure_rate"),
        "neutral_rate": champion.get("neutral_rate"),
        "selected_on": champion.get("selected_on"),
    }
