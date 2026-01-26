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
from datetime import datetime, timedelta, date
import razorpay
import yfinance as yf
from core_engine.symbol_resolver import resolve_symbol
from core_engine.symbol_resolver import DF as SYMBOL_DF
from core_engine.llm_chat_engine import explain_with_llm
from core_engine.analyzer import analyze_stock
from core_engine.sentiment_engine import analyze_sentiment
from core_engine.trend_engine import analyze_trend
from core_engine.universe import TOP_100_STOCKS
from core_engine.prediction_history import load_history_any
from core_engine import prediction_history as prediction_history
from django.utils import timezone
from api.models import Watchlist
from accounts.models import UserSubscription
from accounts.models import UserProfile
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
import os
from pathlib import Path
from zoneinfo import ZoneInfo

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
# ML JOBS HELPERS
# =========================================================
def _read_last_jsonl(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        lines = path.read_bytes().splitlines()
    except Exception:
        return None
    for raw in reversed(lines):
        if not raw:
            continue
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            continue
    return None


def _format_dt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return value


def _parse_prediction_dt(record: dict) -> datetime | None:
    if not isinstance(record, dict):
        return None
    ts = (
        record.get("timestamp")
        or record.get("created_at")
        or record.get("created_on")
        or record.get("evaluated_on")
    )
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt
        except Exception:
            pass
    date_val = record.get("date")
    if isinstance(date_val, str) and len(date_val) >= 10:
        try:
            dt = datetime.fromisoformat(date_val[:10])
            return dt
        except Exception:
            return None
    return None


def _prediction_date_only(record: dict) -> date | None:
    dt = _parse_prediction_dt(record)
    if not dt:
        return None
    return dt.date()


def _exact_match_percent(record: dict) -> float | None:
    expected = record.get("expected_range")
    if not isinstance(expected, dict):
        return None
    low = expected.get("low")
    high = expected.get("high")
    if low is None or high is None:
        return None
    try:
        low_val = float(low)
        high_val = float(high)
    except Exception:
        return None
    if high_val <= low_val:
        return None

    actual = (
        record.get("actual_close")
        or record.get("close")
        or record.get("actual")
    )
    try:
        actual_val = float(actual)
    except Exception:
        actual_val = None

    if actual_val is None:
        return None

    if low_val <= actual_val <= high_val:
        return 100.0

    range_error = record.get("range_error")
    if range_error is None:
        if actual_val > high_val:
            range_error = abs(actual_val - high_val)
        else:
            range_error = abs(actual_val - low_val)
    try:
        range_error_val = float(range_error)
    except Exception:
        return None

    width = high_val - low_val
    pct = max(0.0, 100.0 - (range_error_val / width * 100.0))
    return round(pct, 2)


def _load_history_latest() -> list[dict]:
    candidates: list[str] = []
    try:
        candidates = prediction_history._history_candidates()
    except Exception:
        candidates = []

    flat_records: list[dict] = []
    seen_ids: set[str] = set()

    def _append_record(record: dict) -> None:
        if not isinstance(record, dict):
            return
        record_id = record.get("id") or record.get("uuid")
        if record_id and record_id in seen_ids:
            return
        if record_id:
            seen_ids.add(str(record_id))
        flat_records.append(record)

    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r") as handle:
                data = json.load(handle)
        except Exception:
            continue

        if isinstance(data, list):
            for record in data:
                _append_record(record)
            continue

        if isinstance(data, dict):
            for symbol_key, records in data.items():
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    if not record.get("symbol"):
                        record["_symbol_key"] = symbol_key
                    _append_record(record)

    if not flat_records:
        history, _, _ = load_history_any()
        return history if isinstance(history, list) else []

    return flat_records


def _next_weekly_competition() -> str:
    tz = ZoneInfo("Asia/Kolkata")
    now_dt = datetime.now(tz)
    target = now_dt.replace(hour=3, minute=0, second=0, microsecond=0)
    days_ahead = (5 - now_dt.weekday()) % 7  # Saturday=5
    if days_ahead == 0 and now_dt >= target:
        days_ahead = 7
    target = target + timedelta(days=days_ahead)
    return target.strftime("%d %b %Y, %I:%M %p")


# =========================================================
# SIMPLE PAGE ROUTES
# =========================================================
@login_required
def ml_jobs(request):
    allowed_email = "1995praritsidana@gmail.com"
    user_email = (request.user.email or "").strip().lower()
    if user_email != allowed_email:
        return redirect("/dashboard/")

    from core_engine.ml_engine.expected_range import model_registry

    logs_dir = Path(settings.BASE_DIR) / "backend" / "logs"
    ml_report_path = logs_dir / "ml_cycle_report.jsonl"
    auto_report_path = logs_dir / "auto_prediction_report.jsonl"
    evaluator_report_path = logs_dir / "prediction_evaluator_report.jsonl"

    ml_report = _read_last_jsonl(ml_report_path) or {}
    auto_report = _read_last_jsonl(auto_report_path) or {}
    evaluator_report = _read_last_jsonl(evaluator_report_path) or {}

    scorecard = {}
    champ = {}
    if isinstance(ml_report, dict):
        scorecard = ml_report.get("steps", {}).get("scoring") or {}
        champ = ml_report.get("steps", {}).get("champion") or {}

    winner_pair = None
    if isinstance(champ, dict):
        champ_low = champ.get("champion_low")
        if isinstance(champ_low, str) and champ_low.endswith("_low"):
            winner_pair = champ_low.replace("_low", "")

    scores = []
    if isinstance(scorecard, dict):
        for pair, stats in scorecard.items():
            if not isinstance(stats, dict):
                continue
            scores.append({
                "pair": pair,
                "hit_rate": stats.get("hit_rate"),
                "mae": stats.get("mae"),
                "mae_low": stats.get("mae_low"),
                "mae_high": stats.get("mae_high"),
                "is_winner": pair == winner_pair,
            })
        scores.sort(key=lambda x: (x.get("hit_rate") or 0), reverse=True)

    total_models = 0
    model_meta = {}
    try:
        total_models = len(model_registry.get_all_models())
        model_meta = model_registry.get_registry_meta()
    except Exception:
        total_models = 0
        model_meta = {}

    data_samples = model_meta.get("samples")

    def _job_status(report: dict) -> str:
        if not report:
            return "job not done"
        status = str(report.get("status", "")).upper()
        return "job done" if status and status != "FAILED" else "job not done"

    auto_status = _job_status(auto_report)
    auto_time = _format_dt(auto_report.get("completed_at") or auto_report.get("started_at"))
    evaluator_status = _job_status(evaluator_report)
    evaluator_time = _format_dt(evaluator_report.get("completed_at") or evaluator_report.get("started_at"))

    # ---- TOP 100 STOCKS PANEL ----
    tz = ZoneInfo("Asia/Kolkata")
    target_date = (datetime.now(tz) - timedelta(days=1)).date()
    history = _load_history_latest()
    latest_by_symbol = {}
    latest_range_by_symbol = {}
    latest_dates = []
    latest_range_dates = []
    if isinstance(history, list):
        for record in history:
            if not isinstance(record, dict):
                continue
            symbol = record.get("symbol") or record.get("_symbol_key")
            if not symbol:
                continue
            symbol = str(symbol).upper().strip()
            rec_dt = _parse_prediction_dt(record)
            rec_date = rec_dt.date() if rec_dt else _prediction_date_only(record)
            if rec_dt is None and rec_date:
                rec_dt = datetime.combine(rec_date, datetime.min.time())

            expected = record.get("expected_range") if isinstance(record, dict) else None
            has_range = (
                isinstance(expected, dict)
                and expected.get("low") is not None
                and expected.get("high") is not None
            )

            existing = latest_by_symbol.get(symbol)
            if existing is None:
                latest_by_symbol[symbol] = (rec_dt, record, rec_date)
            else:
                prev_dt = existing[0]
                if rec_dt and (prev_dt is None or rec_dt > prev_dt):
                    latest_by_symbol[symbol] = (rec_dt, record, rec_date)

            if has_range:
                existing_range = latest_range_by_symbol.get(symbol)
                if existing_range is None:
                    latest_range_by_symbol[symbol] = (rec_dt, record, rec_date)
                else:
                    prev_dt = existing_range[0]
                    if rec_dt and (prev_dt is None or rec_dt > prev_dt):
                        latest_range_by_symbol[symbol] = (rec_dt, record, rec_date)

        for _, _, rec_date in latest_by_symbol.values():
            if rec_date:
                latest_dates.append(rec_date)
        for _, _, rec_date in latest_range_by_symbol.values():
            if rec_date:
                latest_range_dates.append(rec_date)

    company_map = {}
    try:
        for _, row in SYMBOL_DF.iterrows():
            sym = str(row.get("symbol") or "").upper().strip()
            if sym:
                company_map[sym] = str(row.get("company") or sym).strip()
    except Exception:
        company_map = {}

    top100_rows = []
    for symbol in TOP_100_STOCKS:
        record = latest_range_by_symbol.get(symbol, (None, None, None))[1]
        if record is None:
            record = latest_by_symbol.get(symbol, (None, None, None))[1]
        expected_range = None
        exact_match_pct = None
        exact_match_note = None
        current_price = None
        if isinstance(record, dict):
            context = record.get("context") if isinstance(record.get("context"), dict) else {}
            if context:
                current_price = context.get("price")
            if current_price is None:
                current_price = record.get("price") or record.get("close")
            try:
                if current_price is not None:
                    current_price = float(current_price)
            except Exception:
                current_price = None
            expected = record.get("expected_range")
            if isinstance(expected, dict) and expected.get("low") is not None and expected.get("high") is not None:
                try:
                    low_val = float(expected.get("low"))
                    high_val = float(expected.get("high"))
                    expected_range = f"Rs {low_val:.2f} - Rs {high_val:.2f}"
                except Exception:
                    expected_range = None
            exact_match_pct = _exact_match_percent(record)
            if exact_match_pct is None:
                if record.get("evaluated") is True or record.get("actual_close") is not None:
                    exact_match_note = None
                else:
                    exact_match_note = "pending"

        top100_rows.append({
            "symbol": symbol,
            "company": company_map.get(symbol, symbol),
            "current_price": current_price,
            "prediction_range": expected_range,
            "exact_match_pct": exact_match_pct,
            "exact_match_note": exact_match_note,
        })

    if latest_range_dates:
        latest_range_dates.sort()
        prediction_range_date = latest_range_dates[-1].strftime("%d %b %Y")
    elif latest_dates:
        latest_dates.sort()
        prediction_range_date = latest_dates[-1].strftime("%d %b %Y")
    else:
        prediction_range_date = target_date.strftime("%d %b %Y")

    context = {
        "total_models": total_models,
        "competition_time": _next_weekly_competition(),
        "competition_last_run_time": _format_dt(
            ml_report.get("completed_at") or ml_report.get("started_at")
        ) if isinstance(ml_report, dict) else None,
        "competition_data_count": data_samples,
        "winner_pair": winner_pair,
        "scores": scores,
        "auto_time": auto_time,
        "auto_status": auto_status,
        "evaluator_time": evaluator_time,
        "evaluator_status": evaluator_status,
        "top100_rows": top100_rows,
        "top100_symbols": ",".join(TOP_100_STOCKS),
        "prediction_range_date": prediction_range_date,
    }
    return render(request, "ml_jobs/ml_jobs.html", context)


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
