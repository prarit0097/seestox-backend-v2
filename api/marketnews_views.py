# backend/api/marketnews_views.py

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core_engine.news_fetcher import get_market_news

@require_GET
def market_news_api(request):
    filter_param = request.GET.get("filter", "ALL").strip().upper()
    query = request.GET.get("q", "").strip()
    refresh = request.GET.get("refresh", "0").strip() == "1"
    if not query:
        query = filter_param if filter_param and filter_param != "ALL" else "MARKET"
    query = query.upper()
    try:
        news = get_market_news(query, force_refresh=refresh)
        return JsonResponse({
            "news": news,
            "sentiment": {
                "bullish": 0,
                "bearish": 0,
                "neutral": 100
            }
        })
    except Exception:
        news = get_market_news(query, force_refresh=False)
        return JsonResponse({
            "news": news or [],
            "sentiment": {
                "bullish": 0,
                "bearish": 0,
                "neutral": 100
            },
            "status": "ERROR"
        })
