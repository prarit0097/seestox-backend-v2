from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
import json
import time
from api.models import Watchlist
from core_engine.price_engine import (
    get_price,
    get_change_percent,
    register_symbol,
    PRICE_CACHE,
    CHANGE_CACHE,
    LOCK,
)
from core_engine.symbol_resolver import DF


# =========================================================
# WATCHLIST PAGE
# =========================================================
@login_required
@ensure_csrf_cookie
def watchlist_page(request):
    items = Watchlist.objects.filter(user=request.user)
    symbols = [item.symbol for item in items]

    # 🔥 ensure all symbols are registered in cache
    for s in symbols:
        register_symbol(s)

    return render(request, "watchlist/watchlist.html", {
        "symbols": symbols
    })


# =========================================================
# WATCHLIST PRICE DATA
# =========================================================
@login_required
def watchlist_data(request):
    items = Watchlist.objects.filter(user=request.user)

    data = []
    for item in items:
        data.append({
            "symbol": item.symbol,
            "current_price": get_price(item.symbol),
            "updated_at": int(time.time())
        })

    return JsonResponse({"watchlist": data})

def _company_for_symbol(symbol):
    try:
        row = DF[DF["symbol"] == symbol]
        if not row.empty:
            return str(row.iloc[0]["company"]).strip()
    except Exception:
        pass
    return symbol


def _is_known_symbol(symbol: str) -> bool:
    try:
        row = DF[DF["symbol"] == symbol]
        return not row.empty
    except Exception:
        return False


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def watchlist_api(request):
    items = Watchlist.objects.filter(user=request.user)
    data = []
    for item in items:
        if not _is_known_symbol(item.symbol):
            continue
        register_symbol(item.symbol)
        data.append({
            "symbol": item.symbol,
            "company": _company_for_symbol(item.symbol),
            "current_price": get_price(item.symbol),
            "change_percent": get_change_percent(item.symbol),
        })
    return Response({"watchlist": data})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def watchlist_add_api(request):
    symbol = (request.data.get("symbol") or "").upper().strip()
    if not symbol:
        return Response({"error": "Symbol required"}, status=400)
    if not _is_known_symbol(symbol):
        return Response({"error": "Unknown symbol"}, status=404)

    Watchlist.objects.get_or_create(
        user=request.user,
        symbol=symbol
    )

    register_symbol(symbol)

    return Response({
        "status": "ok",
        "symbol": symbol,
        "company": _company_for_symbol(symbol),
    })


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def watchlist_remove_api(request):
    symbol = (request.data.get("symbol") or "").upper().strip()
    if not symbol:
        return Response({"error": "Symbol required"}, status=400)

    Watchlist.objects.filter(
        user=request.user,
        symbol=symbol
    ).delete()

    with LOCK:
        PRICE_CACHE.pop(symbol, None)
        CHANGE_CACHE.pop(symbol, None)

    return Response({"status": "ok", "symbol": symbol})

# =========================================================
# ADD STOCK
# =========================================================
@require_POST
@login_required
def add_to_watchlist(request):
    symbol = request.POST.get("symbol", "").upper()

    if not symbol:
        return JsonResponse({"error": "Symbol required"}, status=400)
    if not _is_known_symbol(symbol):
        return JsonResponse({"error": "Unknown symbol"}, status=404)

    Watchlist.objects.get_or_create(
        user=request.user,
        symbol=symbol
    )

    # 🔥 register once (Yahoo hit happens here)
    register_symbol(symbol)

    return JsonResponse({"status": "ok", "symbol": symbol})


# =========================================================
# REMOVE STOCK
# =========================================================
@require_POST
@login_required
def remove_from_watchlist(request):
    symbol = ""

    if request.content_type == "application/json":
        try:
            body = json.loads(request.body)
            symbol = body.get("symbol", "").upper()
        except Exception:
            pass

    if not symbol:
        symbol = request.POST.get("symbol", "").upper()

    if not symbol:
        return JsonResponse({"error": "Symbol required"}, status=400)

    Watchlist.objects.filter(
        user=request.user,
        symbol=symbol
    ).delete()

    with LOCK:
        PRICE_CACHE.pop(symbol, None)

    return JsonResponse({"status": "ok", "symbol": symbol})
