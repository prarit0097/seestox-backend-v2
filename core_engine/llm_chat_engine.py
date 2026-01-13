# core_engine/llm_chat_engine.py
# FINAL — AUTO LANGUAGE DETECTION + TRADER TONE

from openai import OpenAI
from django.conf import settings
import json

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# =====================================================
# 🔍 AUTO LANGUAGE DETECTION
# =====================================================

def detect_language(user_message: str) -> str:
    """
    Detect reply language from user message.
    Returns: 'HINDI' or 'ENGLISH'
    """

    if not user_message:
        return "HINDI"

    msg = user_message.lower()

    # Devanagari (Hindi script)
    for ch in msg:
        if '\u0900' <= ch <= '\u097F':
            return "HINDI"

    # Hinglish indicators
    hindi_words = [
        "kya", "ka", "ki", "krna", "karna", "kaise",
        "kyu", "kyon", "kab", "ab", "hai", "nahi",
        "lene", "bechna", "bechu", "khareed",
        "rakhna", "kro", "hoga", "hogi"
    ]

    for w in hindi_words:
        if w in msg:
            return "HINDI"

    return "ENGLISH"


# =====================================================
# 🧠 SYSTEM PROMPTS
# =====================================================

BASE_PROMPT = """
You are an Indian stock market AI assistant for traders.

STRICT RULES:
- You DO NOT analyze stocks yourself.
- You ONLY explain the data provided.
- You MUST use ALL important data fields if present.
- NEVER create prices, targets, or probabilities.
- Your reply must sound natural and human-like.

RESPONSE LENGTH RULE (VERY IMPORTANT):
- Your full reply MUST be between 10–13 lines only.
- Be concise, no long paragraphs.

CONTENT RULE:
- Briefly cover in 1–2 lines each:
  Trend & volume,
  Support/Resistance,
  Sentiment & confidence,
  Risk level,
  Prediction bias & expected range,
  Historical confidence & reliability,
  News impact (only if meaningful).

ENDING RULE:
- End with exactly ONE clear takeaway:
  Avoid / Cautious / Neutral / Opportunity
"""


LANGUAGE_PROMPTS = {
    "HINDI": """
LANGUAGE STYLE:
- Use clean Hinglish (Hindi + English mix)
- Indian trader tone
- Confident but practical

Example:
"JSLL abhi downtrend me hai.
Support ₹660 ke paas hai.
Risk medium hai, isliye aggressive buying avoid karo."
""",
    "ENGLISH": """
LANGUAGE STYLE:
- Use professional, simple English
- Trading desk style tone

Example:
"JSLL is currently in a downtrend.
Support is near ₹660.
Risk remains medium, so aggressive buying should be avoided."
"""
}

# =====================================================
# 🤖 MAIN EXPLAIN FUNCTION
# =====================================================

def explain_with_llm(
    user_message: str,
    symbol: str,
    company: str,
    data: dict
) -> str:
    """
    Explains ONLY engine data.
    Language is auto-detected.
    """

    # ✅ Detect language
    language = detect_language(user_message)

    # ✅ THIS LINE NOW EXISTS (NO CONFUSION)
    lang_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["HINDI"])

    system_prompt = BASE_PROMPT + "\n" + lang_prompt

    payload = {
        "symbol": symbol,
        "company": company,
        "price": data.get("price"),
        "trend": data.get("trend"),
        "sentiment": data.get("sentiment"),
        "risk": data.get("risk"),
        "prediction": data.get("prediction"),
        "confidence": data.get("confidence"),
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"User Question:\n{user_message}\n\n"
                f"Stock Data (ONLY SOURCE OF TRUTH):\n"
                f"{json.dumps(payload, indent=2)}\n\n"
                "Explain this clearly for a trader."
            )
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.15,
        max_tokens=250
    )

    return response.choices[0].message.content.strip()
