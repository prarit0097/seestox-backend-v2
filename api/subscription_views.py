from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
import razorpay

from accounts.models import UserSubscription
from .serializers import SubscriptionPlanSerializer, SubscriptionStatusSerializer


PLAN_CATALOG = {
    "PRO_MONTHLY": {
        "code": "PRO_MONTHLY",
        "name": "Pro Monthly",
        "price_inr": 199,
        "interval": "month",
        "features": ["AI Chat", "Watchlist Alerts", "Premium Insights"],
        "amount_paise": 19900,
        "db_plan": "MONTHLY",
        "days": 30,
    },
    "PRO_YEARLY": {
        "code": "PRO_YEARLY",
        "name": "Pro Yearly",
        "price_inr": 1999,
        "interval": "year",
        "features": ["AI Chat", "Watchlist Alerts", "Premium Insights"],
        "amount_paise": 199900,
        "db_plan": "YEARLY",
        "days": 365,
    },
}


def _iso(dt):
    if not dt:
        return None
    value = dt.isoformat()
    return value.replace("+00:00", "Z")


def _plan_payload_from_db(db_plan):
    for plan in PLAN_CATALOG.values():
        if plan["db_plan"] == db_plan:
            return {
                "code": plan["code"],
                "name": plan["name"],
                "interval": plan["interval"],
                "price_inr": plan["price_inr"],
            }
    return None


def _status_payload(sub):
    snapshot = sub.status_snapshot()
    status = snapshot["status"]
    plan_payload = _plan_payload_from_db(sub.plan) if status == "ACTIVE" else None

    data = {
        "status": status,
        "is_active": snapshot["is_active"],
        "access_level": snapshot["access_level"],
        "plan": plan_payload,
        "trial": {
            "is_trial": status == "TRIAL",
            "trial_started_at": _iso(snapshot["trial_started_at"]),
            "trial_ends_at": _iso(snapshot["trial_ends_at"]),
            "days_left": snapshot["days_left"],
        },
        "current_period": {
            "starts_at": _iso(snapshot["current_period_start"]),
            "ends_at": _iso(snapshot["current_period_end"]),
        },
        "paywall": {
            "required": status == "EXPIRED",
            "reason": "TRIAL_EXPIRED" if status == "EXPIRED" else None,
        },
    }
    return SubscriptionStatusSerializer(data).data


razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


@api_view(["GET"])
@permission_classes([AllowAny])
def subscription_plans(request):
    plans = [plan for plan in PLAN_CATALOG.values()]
    payload = {
        "currency": "INR",
        "plans": SubscriptionPlanSerializer(plans, many=True).data,
    }
    return Response({"success": True, "data": payload})


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def subscription_status(request):
    sub, _ = UserSubscription.objects.get_or_create(
        user=request.user,
        defaults={"plan": "FREE", "is_active": False},
    )
    sub.ensure_trial_started()
    return Response({"success": True, "data": _status_payload(sub)})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def subscription_checkout(request):
    plan_code = (request.data.get("plan_code") or "").upper().strip()
    plan = PLAN_CATALOG.get(plan_code)
    if not plan:
        return Response(
            {"success": False, "error": {"code": "INVALID_PLAN", "message": "Unknown plan_code"}},
            status=400,
        )

    order = razorpay_client.order.create(
        {
            "amount": plan["amount_paise"],
            "currency": "INR",
            "payment_capture": 1,
        }
    )

    name = " ".join(part for part in [request.user.first_name, request.user.last_name] if part).strip()
    if not name:
        name = request.user.email

    payload = {
        "provider": "razorpay",
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "order": {
            "order_id": order["id"],
            "amount_paise": plan["amount_paise"],
            "currency": "INR",
        },
        "prefill": {
            "name": name,
            "email": request.user.email,
            "contact": "",
        },
        "notes": {
            "user_id": request.user.id,
            "plan_code": plan_code,
        },
    }
    return Response({"success": True, "data": payload})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def subscription_verify(request):
    plan_code = (request.data.get("plan_code") or "").upper().strip()
    plan = PLAN_CATALOG.get(plan_code)
    if not plan:
        return Response(
            {"success": False, "error": {"code": "INVALID_PLAN", "message": "Unknown plan_code"}},
            status=400,
        )

    order_id = request.data.get("razorpay_order_id")
    payment_id = request.data.get("razorpay_payment_id")
    signature = request.data.get("razorpay_signature")
    if not order_id or not payment_id or not signature:
        return Response(
            {
                "success": False,
                "error": {"code": "MISSING_FIELDS", "message": "Payment fields required"},
            },
            status=400,
        )

    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except Exception:
        return Response(
            {
                "success": False,
                "error": {
                    "code": "PAYMENT_VERIFICATION_FAILED",
                    "message": "Invalid signature",
                },
            },
            status=400,
        )

    order = razorpay_client.order.fetch(order_id)
    order_amount = int(order.get("amount", 0))
    if order_amount != plan["amount_paise"]:
        return Response(
            {
                "success": False,
                "error": {"code": "AMOUNT_MISMATCH", "message": "Order amount mismatch"},
            },
            status=400,
        )

    sub, _ = UserSubscription.objects.get_or_create(
        user=request.user,
        defaults={"plan": "FREE", "is_active": False},
    )
    now = timezone.now()
    sub.is_active = True
    sub.plan = plan["db_plan"]
    sub.paid_start = now
    sub.paid_end = now + timedelta(days=plan["days"])
    sub.save(update_fields=["is_active", "plan", "paid_start", "paid_end", "updated_at"])

    return Response({"success": True, "data": _status_payload(sub)})
