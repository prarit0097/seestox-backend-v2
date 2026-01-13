# core_engine/news_fetcher.py
# FAST SINGLE-SOURCE NEWS ENGINE (GOOGLE RSS)

import feedparser
import time
import threading
from datetime import datetime, timezone
from urllib.parse import quote_plus

NEWS_CACHE = {}
CACHE_TTL = 60  # 60 seconds
_CACHE_LOCK = threading.Lock()

def _to_iso_utc(entry):
    published = entry.get("published_parsed")
    if not published:
        return ""
    dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

def _extract_image_url(entry):
    thumb = entry.get("media_thumbnail") or []
    if thumb and isinstance(thumb, list) and "url" in thumb[0]:
        return thumb[0]["url"]
    media = entry.get("media_content") or []
    if media and isinstance(media, list) and "url" in media[0]:
        return media[0]["url"]
    return ""

def _fetch_google_news(query="MARKET"):
    safe_query = quote_plus(f"{query} stock")
    url = (
        "https://news.google.com/rss/search?"
        f"q={safe_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    feed = feedparser.parse(url)
    news = []

    for e in feed.entries[:20]:
        news.append({
            "symbol": query,
            "title": e.title,
            "source": "Google News",
            "timestamp": e.published if hasattr(e, "published") else "",
            "published_at": _to_iso_utc(e),
            "url": e.link if hasattr(e, "link") else "",
            "image_url": _extract_image_url(e),
            "sentiment": "NEUTRAL"
        })

    return news


def _background_refresh(query):
    data = _fetch_google_news(query)
    with _CACHE_LOCK:
        NEWS_CACHE[query] = {
            "time": time.time(),
            "data": data
        }


def get_market_news(query="MARKET", force_refresh=False):
    query = query.upper()
    now = time.time()

    if force_refresh:
        data = _fetch_google_news(query)
        with _CACHE_LOCK:
            NEWS_CACHE[query] = {
                "time": time.time(),
                "data": data
            }
        return data

    # ✅ If cache fresh → instant
    with _CACHE_LOCK:
        if query in NEWS_CACHE:
            cached = NEWS_CACHE[query]
            if now - cached["time"] < CACHE_TTL:
                return cached["data"]

    # 🔥 Cache stale / missing → return OLD if exists
    with _CACHE_LOCK:
        if query in NEWS_CACHE:
            threading.Thread(
                target=_background_refresh,
                args=(query,),
                daemon=True
            ).start()
            return NEWS_CACHE[query]["data"]

    # 🔥 First time only → fetch async + empty fallback
    threading.Thread(
        target=_background_refresh,
        args=(query,),
        daemon=True
    ).start()

    return []
