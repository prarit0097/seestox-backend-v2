# core_engine/chat_orchestrator.py
# PHASE-4 FINAL — DATA-FIRST CHAT ORCHESTRATOR (NO HALLUCINATION)

from core_engine.analyzer import analyze_stock
from core_engine.symbol_resolver import resolve_symbol
from core_engine.llm_chat_engine import explain_with_llm


def chat_reply(user_message: str) -> str:
    """
    FINAL SAFE ENTRY POINT
    - Uses ONLY internal engine data
    - OpenAI is used ONLY for explanation
    """

    if not user_message or not user_message.strip():
        return "❓ Please ask a valid stock-related question."

    # 1️⃣ Resolve symbol (SAFE)
    resolved = resolve_symbol(user_message)

    if not resolved:
        return (
            "❓ Stock samajh nahi aaya.\n\n"
            "Example try karo:\n"
            "- JSLL ka kya hoga?\n"
            "- TCS trend batao"
        )

    symbol, company = resolved

    # 🚫 Index blocking (for now)
    if symbol.upper() in ["NIFTY", "NIFTY50", "SENSEX", "BANKNIFTY"]:
        return (
            "ℹ️ Index analysis abhi available nahi hai.\n\n"
            "Please kisi individual stock ke baare me poochiye "
            "(JSLL, TCS, HDFC Bank, etc.)"
        )

    # 2️⃣ Analyze stock (SINGLE SOURCE OF TRUTH)
    try:
        data = analyze_stock(symbol)
    except Exception as e:
        return (
            "⚠️ Is stock ka data abhi incomplete hai.\n\n"
            "Please thodi der baad try karein."
        )

    # 3️⃣ Ask LLM to EXPLAIN (NOT ANALYZE)
    try:
        return explain_with_llm(
            user_message=user_message,
            symbol=symbol,
            company=company,
            data=data
        )
    except Exception:
        return (
            "⚠️ Explanation service temporary unavailable hai.\n\n"
            "Please thodi der baad try karein."
        )
