from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
import time
import json
from datetime import datetime, timedelta
import razorpay
import yfinance as yf
from core_engine.symbol_resolver import resolve_symbol
from core_engine.llm_chat_engine import explain_with_llm
from core_engine.analyzer import analyze_stock
from core_engine.sentiment_engine import analyze_sentiment
from core_engine.trend_engine import analyze_trend
from django.utils import timezone
from api.models import Watchlist
from accounts.models import UserSubscription
from accounts.models import UserProfile
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
import os

MARKET_SNAPSHOT_TTL = int(os.getenv("MARKET_SNAPSHOT_TTL", "5"))
_MARKET_SNAPSHOT_CACHE = {"ts": 0.0, "data": None}
PLAN_AMOUNTS = {
    "MONTHLY": 29900,
    "YEARLY": 300000,
}


# =========================================================
# 🔥 FORCE LANDING
# =========================================================
def force_landing(request):
    return redirect("/")


# =========================================================
# ENTRY POINT
# =========================================================

def landing(request):
    return render(request, "landing/landing.html")


def entry_point(request):
    # 🔹 Not logged in → landing
    if not request.user.is_authenticated:
        return render(request, "landing/landing.html")

    # 🔹 Logged in → subscription
    sub, _ = UserSubscription.objects.get_or_create(
        user=request.user,
        defaults={"plan": "FREE", "is_active": False},
    )

    # 🔹 Onboarding first
    if not sub.onboarding_completed:
        return redirect("/onboarding/")

    # 🔹 App start
    return redirect("/dashboard/")

# =========================================================
# ONBOARDING
# =========================================================
@login_required
def onboarding(request):
    sub, _ = UserSubscription.objects.get_or_create(user=request.user)

    # 🔹 Agar onboarding already complete hai → dashboard
    if sub.onboarding_completed:
        return redirect("/dashboard/")

    # 🔹 FORM SUBMIT
    if request.method == "POST":
        sub.onboarding_completed = True
        sub.onboarding_completed_at = timezone.now() 

        # 🔥 START TRIAL (ONLY ONCE)
        if not sub.trial_start:
            now = timezone.now()
            sub.trial_start = now
            sub.trial_end = now + timedelta(days=7)

        sub.save()
        return redirect("/dashboard/")

    # 🔹 GET REQUEST → show onboarding page
    return render(request, "onboarding/onboarding.html")       


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def onboarding_complete_api(request):
    sub, _ = UserSubscription.objects.get_or_create(
        user=request.user,
        defaults={"plan": "FREE", "is_active": False},
    )
    sub.complete_onboarding()
    sub.ensure_trial_started()
    return Response({
        "status": "ok",
        "onboarding_completed": True,
        "onboarding_completed_at": sub.onboarding_completed_at,
    })

# =========================================================
# DASHBOARD
# =========================================================
@login_required
@ensure_csrf_cookie
def dashboard(request):
    return render(request, "dashboard/dashboard.html")


# =========================================================
# MARKET SNAPSHOT
# =========================================================

def market_snapshot_api(request):
    now_ts = time.time()
    if (
        _MARKET_SNAPSHOT_CACHE["data"] is not None
        and now_ts - _MARKET_SNAPSHOT_CACHE["ts"] < MARKET_SNAPSHOT_TTL
    ):
        return JsonResponse(_MARKET_SNAPSHOT_CACHE["data"])

    try:
        nifty = yf.Ticker("^NSEI")
        sensex = yf.Ticker("^BSESN")
        vix = yf.Ticker("^INDIAVIX")
        banknifty = yf.Ticker("^NSEBANK")

        market_time = nifty.info.get("regularMarketTime")
        is_open = None
        if market_time:
            market_dt = datetime.fromtimestamp(
                market_time,
                tz=timezone.get_current_timezone(),
            )
            now_local = timezone.localtime()
            if market_dt.date() == now_local.date():
                minutes = market_dt.hour * 60 + market_dt.minute
                is_open = 9 * 60 + 15 <= minutes <= 15 * 60 + 30
            else:
                is_open = False

        data = {
            "nifty": round(nifty.info.get("regularMarketChangePercent", 0), 2),
            "sensex": round(sensex.info.get("regularMarketChangePercent", 0), 2),
            "vix": round(vix.info.get("regularMarketChangePercent", 0), 2),
            "banknifty": round(banknifty.info.get("regularMarketChangePercent", 0), 2),
            "nifty_price": round(nifty.info.get("regularMarketPrice", 0), 2),
            "sensex_price": round(sensex.info.get("regularMarketPrice", 0), 2),
            "vix_price": round(vix.info.get("regularMarketPrice", 0), 2),
            "banknifty_price": round(banknifty.info.get("regularMarketPrice", 0), 2),
            "status": "OK",
            "is_open": is_open,
        }
        _MARKET_SNAPSHOT_CACHE["data"] = data
        _MARKET_SNAPSHOT_CACHE["ts"] = now_ts
    except Exception as e:
        print("❌ Market snapshot error:", e)
        if _MARKET_SNAPSHOT_CACHE["data"] is not None:
            data = dict(_MARKET_SNAPSHOT_CACHE["data"])
            data["status"] = "STALE"
        else:
            data = {"nifty": 0, "sensex": 0, "vix": 0, "status": "ERROR"}

    return JsonResponse(data)


# =========================================================
# ANALYZE STOCK
# =========================================================z
@login_required
def analyze_stock_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    sub, _ = UserSubscription.objects.get_or_create(user=request.user)
    if not sub.is_valid():
        return JsonResponse({"error": "Upgrade required"}, status=403)

    data = json.loads(request.body.decode("utf-8"))
    company = data.get("company")

    if not company:
        return JsonResponse({"error": "Company name required"}, status=400)

    try:
        result = analyze_stock(company)
        return JsonResponse(result, safe=False)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        print("❌ Analyze error:", e)
        return JsonResponse({"error": "Internal error"}, status=500)


# =========================================================
# CHAT API
# =========================================================
@csrf_exempt
def chat_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        body = json.loads(request.body)
        user_message = body.get("message", "").strip()

        if not user_message:
            return JsonResponse({"reply": "Please ask a valid question."})

        resolved = resolve_symbol(user_message)
        if not resolved:
            return JsonResponse({
                "reply": "❓ Stock samajh nahi aaya. Please mention stock name like JSLL, TCS."
            })

        symbol, company = resolved
        data = analyze_stock(symbol)

        reply = explain_with_llm(
            user_message=user_message,
            symbol=symbol,
            company=company,
            data=data,
        )

        return JsonResponse({"reply": reply})

    except Exception as e:
        print("CHAT API ERROR:", str(e))
        return JsonResponse({"reply": "⚠️ Internal analysis error."}, status=500)


# =========================================================
# RAZORPAY
# =========================================================
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


@require_POST
@login_required
def create_order(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    plan = payload.get("plan")

    # ✅ Allow only valid plans
    if plan not in PLAN_AMOUNTS:
        return JsonResponse({"error": "Invalid plan"}, status=400)

    amount = PLAN_AMOUNTS[plan]

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1,
    })

    return JsonResponse({
        "order_id": order["id"],
        "key": settings.RAZORPAY_KEY_ID,
        "plan": plan,
        "amount": amount,
    })


@require_POST
@login_required
def verify_payment(request):
    data = request.POST

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": data.get("razorpay_order_id"),
            "razorpay_payment_id": data.get("razorpay_payment_id"),
            "razorpay_signature": data.get("razorpay_signature"),
        })

        plan = data.get("plan")
        if plan not in PLAN_AMOUNTS:
            return JsonResponse({"status": "invalid_plan"}, status=400)

        order_id = data.get("razorpay_order_id")
        order = razorpay_client.order.fetch(order_id)
        order_amount = int(order.get("amount", 0))
        expected_amount = PLAN_AMOUNTS[plan]
        if order_amount != expected_amount:
            return JsonResponse({"status": "amount_mismatch"}, status=400)

        sub, _ = UserSubscription.objects.get_or_create(user=request.user)

        sub.is_active = True
        sub.plan = plan
        sub.paid_start = now()
        sub.paid_end = now() + timedelta(days=365 if plan == "YEARLY" else 30)

        # Optional clarity
        # sub.trial_end = None

        sub.save()

        return JsonResponse({"status": "success"})

    except Exception as e:
        print("? Payment verify failed:", e)
        return JsonResponse({"status": "failed"}, status=400)


# =========================================================
# PROFILE (🔥 FINAL FIXED VERSION)
# =========================================================
@login_required
def profile(request):

    user = request.user
    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={"plan": "FREE", "is_active": False},
    )

    # ✅ SAFE: auto-create profile if missing
    profile, created = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":

        # ---- Full name update ----
        full_name = request.POST.get("full_name", "").strip()
        if full_name:
            parts = full_name.split(" ", 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ""
            user.save(update_fields=["first_name", "last_name"])

        # ---- Avatar update ----
        avatar = request.FILES.get("avatar")
        if avatar:
            profile.avatar = avatar
            profile.save(update_fields=["avatar"])

        return redirect("/profile/?updated=1")
    now = timezone.now()
    subscription_status = "NONE"
    subscription_plan = None
    subscription_end = None

    if sub.is_active and sub.plan in ["MONTHLY", "YEARLY"] and sub.paid_end:
        subscription_status = "PAID"
        subscription_plan = sub.get_plan_display()
        subscription_end = sub.paid_end
    elif sub.trial_end:
        subscription_end = sub.trial_end
        if sub.trial_start and sub.trial_start <= now <= sub.trial_end:
            subscription_status = "TRIAL"
        else:
            subscription_status = "TRIAL_EXPIRED"
    elif sub.plan == "FREE":
        subscription_status = "FREE"

    return render(request, "profile/profile.html", {
        "profile": profile,
        "subscription": sub,
        "subscription_status": subscription_status,
        "subscription_plan": subscription_plan,
        "subscription_end": subscription_end,
        "today": now,
    })


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def profile_api(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    avatar_url = profile.avatar.url if profile.avatar else None
    name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    return Response({
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "name": name,
        "avatar": avatar_url,
    })


@api_view(["PUT"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def profile_update_api(request):
    user = request.user
    first_name = str(request.data.get("first_name", "")).strip()
    last_name = str(request.data.get("last_name", "")).strip()

    user.first_name = first_name
    user.last_name = last_name
    user.save(update_fields=["first_name", "last_name"])

    name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    return Response({
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "name": name,
    })


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def profile_avatar_api(request):
    avatar = request.FILES.get("avatar")
    if not avatar:
        return Response({"error": "Avatar file required"}, status=400)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.avatar = avatar
    profile.save(update_fields=["avatar"])

    avatar_url = profile.avatar.url if profile.avatar else None
    return Response({
        "avatar": avatar_url,
    })


# =========================================================
# SIMPLE PAGE ROUTES
# =========================================================
@login_required
def ml_jobs(request):
    allowed_email = "1995praritsidana@gmail.com"
    user_email = (request.user.email or "").strip().lower()
    if user_email != allowed_email:
        return redirect("/dashboard/")
    return render(request, "ml_jobs/ml_jobs.html")


@login_required
def stock_search(request):
    return render(request, "stock_search/stock_search.html")


@login_required
@ensure_csrf_cookie
def stock_chat(request):
    get_token(request)
    return render(request, "stock_chat/stock_chat.html")


@login_required
def market_news(request):
    return render(request, "market_news/market_news.html")


@login_required
def prediction_history(request):
    return render(request, "prediction_history/prediction_history.html")


@login_required
def app_settings(request):
    return render(request, "app_settings/app_settings.html")


@login_required
def about_help(request):
    return render(request, "about_help/about_help.html")


@login_required
@ensure_csrf_cookie
def subscription(request):
    sub = getattr(request.user, "usersubscription", None)

    subscription_status = "NONE"
    trial_start = None
    trial_end = None

    if sub:
        # 🔹 Trial status
        if sub.trial_start and sub.trial_end:
            if sub.trial_start <= timezone.now() <= sub.trial_end:
                subscription_status = "TRIAL_ACTIVE"
            else:
                subscription_status = "TRIAL_EXPIRED"

        # 🔹 Paid override
        if sub.is_active and sub.plan in ["MONTHLY", "YEARLY"]:
            subscription_status = "PAID"

        trial_start = sub.trial_start
        trial_end = sub.trial_end

    return render(
        request,
        "subscription/subscription.html",
        {
            "subscription": sub,
            "subscription_status": subscription_status,
            "trial_start": trial_start,
            "trial_end": trial_end,
        },
    )



@login_required
def trial_expired(request):
    return render(request, "trial_expired/trial_expired.html")

@login_required
def terms(request):
    return render(request, "terms/terms.html")

def privacypolicy(request):
    return render(request, "privacypolicy/privacypolicy.html")


def delete_account_request(request):
    return render(request, "delete_account/delete_account.html")

@login_required
def watchlist_page(request):
    items = Watchlist.objects.filter(user=request.user)
    watchlist_data = []

    for item in items:
        symbol = item.symbol
        try:
            analysis = analyze_stock(symbol)
            watchlist_data.append({
                "symbol": symbol,
                "recommendation": analysis.get("final_signal"),
                "confidence": analysis.get("confidence"),
                "expected_range": analysis.get("expected_range"),
                "trend": analyze_trend(symbol),
                "sentiment": analyze_sentiment(symbol).get("overall"),
            })
        except Exception as e:
            watchlist_data.append({"symbol": symbol, "error": str(e)})

    return render(request, "watchlist/watchlist.html", {"watchlist": watchlist_data})


# =========================================================
# STOCK DETAIL
# =========================================================
@login_required
@ensure_csrf_cookie
def stock_detail_page(request):
    company = request.GET.get("company")
    if not company:
        return redirect("stock_search")

    return render(
        request,
        "stock_detail_page/stock_detail_page.html",
        {"company": company},
    )
