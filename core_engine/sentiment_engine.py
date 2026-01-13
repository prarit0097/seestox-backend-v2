# core_engine/sentiment_engine.py
# PHASE-2E.4 — EXPLAINABLE, FRESH & TREND-AWARE SENTIMENT

from typing import List, Dict
import feedparser
from datetime import datetime, timezone, timedelta
import os
import json


# ==================================================
# CONFIG
# ==================================================

MAX_HEADLINES = 6
MAX_NEWS_AGE_DAYS = 45
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TREND_STORE = os.path.join(BASE_DIR, "sentiment_trend.json")

SOURCE_TRUST = {
    "bloomberg": 1.0,
    "reuters": 0.95,
    "economic times": 0.9,
    "moneycontrol": 0.9,
    "yahoo finance": 0.8,
    "simplywall.st": 0.6,
    "tipranks": 0.6,
    "default": 0.5
}

POSITIVE_KEYWORDS = [
    "profit", "growth", "expands", "beats",
    "approval", "launch", "acquires",
    "order", "contract", "record", "surge",
    "increase", "holding"
]

NEGATIVE_KEYWORDS = [
    "loss", "decline", "downgrade", "fraud",
    "penalty", "risk", "concern", "slowdown",
    "misses", "falls"
]


# ==================================================
# MAIN ENGINE
# ==================================================

def analyze_sentiment(symbol: str) -> Dict:
    news_items = get_news_items(symbol)

    if not news_items:
        return _neutral_block("No relevant recent news found")

    weighted_score = 0.0
    weight_sum = 0.0
    fresh_news_present = False

    for item in news_items:
        if item["sentiment"] == 0:
            continue

        weight = item["freshness_weight"] * item["source_trust"]
        weighted_score += item["sentiment"] * weight
        weight_sum += weight

        if item["is_fresh"]:
            fresh_news_present = True

    score = round(weighted_score / weight_sum, 2) if weight_sum else 0.0
    score = max(-1.0, min(1.0, score))

    # -----------------------------
    # LABEL
    # -----------------------------
    if score >= 0.4:
        overall = "POSITIVE"
    elif score >= 0.15:
        overall = "POSITIVE_WEAK"
    elif score <= -0.4:
        overall = "NEGATIVE"
    elif score <= -0.15:
        overall = "NEGATIVE_WEAK"
    else:
        overall = "NEUTRAL"

    confidence = int(abs(score) * 100)
    confidence = max(5, min(70, confidence))

    # -----------------------------
    # WHY EXPLANATION
    # -----------------------------
    if overall == "POSITIVE_WEAK":
        reason = "Positive news narrative exists, but price trend is weak."
    elif overall == "POSITIVE":
        reason = "Strong positive news and momentum alignment."
    elif overall == "NEGATIVE_WEAK":
        reason = "Negative news present, but not strongly confirmed."
    elif overall == "NEGATIVE":
        reason = "Consistent negative news flow impacting sentiment."
    else:
        reason = "Mixed or neutral news flow."

    # -----------------------------
    # SENTIMENT TREND (7-DAY)
    # -----------------------------
    trend_delta = update_and_get_trend(symbol, score)

    return {
        "overall": overall,
        "confidence": confidence,
        "score": score,
        "why": reason,
        "trend_7d": trend_delta,
        "headlines": [
            f"{i['badge']} {i['title']} ({i['time_ago']})"
            for i in news_items
        ]
    }


# ==================================================
# NEWS FETCH
# ==================================================

def get_news_items(symbol: str) -> List[Dict]:
    symbol = symbol.upper()
    items = []

    url = (
        f"https://news.google.com/rss/search?"
        f"q={symbol}+stock&hl=en-IN&gl=IN&ceid=IN:en"
    )

    feed = feedparser.parse(url)

    for entry in feed.entries:
        title = entry.title.strip()
        if symbol.lower() not in title.lower():
            continue

        published = parse_date(entry)
        age_days = get_age_days(published)

        if age_days is None or age_days > MAX_NEWS_AGE_DAYS:
            continue

        sentiment = classify_sentiment(title)
        freshness_weight = get_freshness_weight(age_days)
        source_trust = get_source_trust(title)
        time_ago = format_time_ago(published)

        is_fresh = age_days <= 1
        badge = "🔥" if is_fresh else "•"

        items.append({
            "title": title,
            "sentiment": sentiment,
            "freshness_weight": freshness_weight,
            "source_trust": source_trust,
            "time_ago": time_ago,
            "is_fresh": is_fresh,
            "badge": badge
        })

        if len(items) >= MAX_HEADLINES:
            break

    return items


# ==================================================
# SENTIMENT TREND STORAGE (LIGHTWEIGHT)
# ==================================================

def update_and_get_trend(symbol: str, current_score: float) -> float:
    today = datetime.now().date().isoformat()

    data = {}
    if os.path.exists(TREND_STORE):
        with open(TREND_STORE, "r") as f:
            data = json.load(f)

    history = data.get(symbol, [])
    history.append({"date": today, "score": current_score})

    cutoff = datetime.now().date() - timedelta(days=7)
    history = [
        h for h in history
        if datetime.fromisoformat(h["date"]).date() >= cutoff
    ]

    data[symbol] = history
    with open(TREND_STORE, "w") as f:
        json.dump(data, f)

    if len(history) < 2:
        return 0.0

    return round(history[-1]["score"] - history[0]["score"], 2)


# ==================================================
# HELPERS
# ==================================================

def classify_sentiment(title: str) -> int:
    t = title.lower()
    if any(k in t for k in POSITIVE_KEYWORDS):
        return 1
    if any(k in t for k in NEGATIVE_KEYWORDS):
        return -1
    return 0


def parse_date(entry):
    try:
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def get_age_days(dt):
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).days


def get_freshness_weight(days):
    if days <= 1:
        return 1.0
    if days <= 3:
        return 0.7
    if days <= 7:
        return 0.5
    return 0.3


def get_source_trust(title):
    t = title.lower()
    for src, trust in SOURCE_TRUST.items():
        if src in t:
            return trust
    return SOURCE_TRUST["default"]


def format_time_ago(dt):
    if not dt:
        return "time unknown"
    delta = datetime.now(timezone.utc) - dt
    if delta.days == 0:
        return f"{delta.seconds // 3600}h ago"
    if delta.days == 1:
        return "1 day ago"
    return f"{delta.days} days ago"


def _neutral_block(reason):
    return {
        "overall": "NEUTRAL",
        "confidence": 0,
        "score": 0.0,
        "why": reason,
        "trend_7d": 0.0,
        "headlines": []
    }
