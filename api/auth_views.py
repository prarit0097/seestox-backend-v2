import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, authenticate
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.models import UserSubscription
from .models import EmailOtp


_ALLOWED_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

OTP_TTL_MINUTES = 5
OTP_RESEND_COOLDOWN_SECONDS = 30
OTP_MAX_ATTEMPTS = 5


def _get_google_client_ids():
    client_ids = getattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", None) or []
    if isinstance(client_ids, str):
        client_ids = [client_ids]
    return [cid for cid in client_ids if cid]


def _build_auth_response(user, picture=None):
    refresh = RefreshToken.for_user(user)
    name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    return JsonResponse(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "name": name,
                "picture": picture,
            },
        }
    )


@csrf_exempt
@require_POST
def google_auth(request):
    """
    Exchange Google id_token for JWT access/refresh.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    token = payload.get("id_token")
    if not token:
        return JsonResponse({"error": "id_token required"}, status=400)

    client_ids = _get_google_client_ids()
    if not client_ids:
        return JsonResponse({"error": "GOOGLE_OAUTH_CLIENT_IDS not configured"}, status=500)

    idinfo = None
    for client_id in client_ids:
        try:
            idinfo = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                client_id,
            )
            break
        except Exception:
            continue

    if not idinfo:
        return JsonResponse({"error": "Invalid or expired Google token"}, status=401)

    issuer = idinfo.get("iss")
    if issuer not in _ALLOWED_GOOGLE_ISSUERS:
        return JsonResponse({"error": "Invalid token issuer"}, status=401)

    aud = idinfo.get("aud")
    if aud not in client_ids:
        return JsonResponse({"error": "Invalid token audience"}, status=401)

    email = (idinfo.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"error": "Email not available from Google"}, status=400)

    first_name = idinfo.get("given_name") or ""
    last_name = idinfo.get("family_name") or ""
    picture = idinfo.get("picture")

    User = get_user_model()
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "first_name": first_name,
            "last_name": last_name,
        },
    )

    update_fields = []
    if created:
        user.set_unusable_password()
        update_fields.append("password")

    if not user.is_active:
        user.is_active = True
        update_fields.append("is_active")

    if first_name and not user.first_name:
        user.first_name = first_name
        update_fields.append("first_name")
    if last_name and not user.last_name:
        user.last_name = last_name
        update_fields.append("last_name")

    if update_fields:
        user.save(update_fields=list(dict.fromkeys(update_fields)))

    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={"plan": "FREE", "is_active": False},
    )
    sub.ensure_trial_started()

    return _build_auth_response(user, picture=picture)


def _generate_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def _send_register_otp(email, code):
    subject = "Your SeeStox OTP"

    message = (
        f"Hello,\n\n"
        f"Your One-Time Password (OTP) for SeeStox is:\n\n"
        f"{code}\n\n"
        f"This OTP is valid for 5 minutes.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"Thanks,\n"
        f"Team SeeStox"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=None,  # DEFAULT_FROM_EMAIL use hoga
        recipient_list=[email],
        fail_silently=False,
    )



def _send_password_reset_otp(email: str, code: str):
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(
        settings, "EMAIL_HOST_USER", ""
    )
    send_mail(
        subject="Your SeeStox password reset code",
        message=(
            "Your password reset code is: "
            f"{code}\n\n"
            f"This code expires in {OTP_TTL_MINUTES} minutes."
        ),
        from_email=from_email,
        recipient_list=[email],
        fail_silently=False,
    )


def _get_active_otp(email: str):
    return EmailOtp.objects.filter(
        email=email,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()


def _create_or_refresh_otp(email: str):
    now = timezone.now()
    active = _get_active_otp(email)
    if active and active.last_sent_at:
        delta = (now - active.last_sent_at).total_seconds()
        if delta < OTP_RESEND_COOLDOWN_SECONDS:
            return None, int(OTP_RESEND_COOLDOWN_SECONDS - delta), None

    code = _generate_otp()
    code_hash = EmailOtp.hash_code(email, code)
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    if active and not active.is_expired():
        active.code_hash = code_hash
        active.expires_at = expires_at
        active.last_sent_at = now
        active.resend_count += 1
        active.attempts = 0
        active.used_at = None
        active.save(update_fields=[
            "code_hash",
            "expires_at",
            "last_sent_at",
            "resend_count",
            "attempts",
            "used_at",
        ])
        otp_obj = active
    else:
        otp_obj = EmailOtp.objects.create(
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            last_sent_at=now,
        )

    try:
        _send_register_otp(email, code)
    except Exception as exc:
        return None, None, str(exc)

    return otp_obj, None, None


def _create_or_refresh_password_reset_otp(email: str):
    now = timezone.now()
    active = _get_active_otp(email)
    if active and active.last_sent_at:
        delta = (now - active.last_sent_at).total_seconds()
        if delta < OTP_RESEND_COOLDOWN_SECONDS:
            return None, int(OTP_RESEND_COOLDOWN_SECONDS - delta), None

    code = _generate_otp()
    code_hash = EmailOtp.hash_code(email, code)
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    if active and not active.is_expired():
        active.code_hash = code_hash
        active.expires_at = expires_at
        active.last_sent_at = now
        active.resend_count += 1
        active.attempts = 0
        active.used_at = None
        active.save(update_fields=[
            "code_hash",
            "expires_at",
            "last_sent_at",
            "resend_count",
            "attempts",
            "used_at",
        ])
        otp_obj = active
    else:
        otp_obj = EmailOtp.objects.create(
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            last_sent_at=now,
        )

    try:
        _send_password_reset_otp(email, code)
    except Exception as exc:
        return None, None, str(exc)

    return otp_obj, None, None


@csrf_exempt
@require_POST
def register(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    first_name = payload.get("first_name") or ""
    last_name = payload.get("last_name") or ""
    otp = (payload.get("otp") or "").strip()

    if not email or not password:
        return JsonResponse({"error": "email and password required"}, status=400)

    try:
        validate_email(email)
    except Exception:
        return JsonResponse({"error": "invalid email"}, status=400)

    if len(password) < 8:
        return JsonResponse({"error": "password must be at least 8 characters"}, status=400)

    User = get_user_model()
    if User.objects.filter(email=email).exists():
        return JsonResponse({"error": "email already exists"}, status=400)

    if not otp:
        _, retry_seconds, send_error = _create_or_refresh_otp(email)
        if send_error:
            return JsonResponse({"error": "otp_send_failed"}, status=500)
        if retry_seconds is not None:
            return JsonResponse(
                {"error": "otp_resend_too_soon", "retry_seconds": retry_seconds},
                status=429,
            )
        return JsonResponse(
            {
                "otp_required": True,
                "message": "OTP sent to your email.",
                "expires_in_seconds": OTP_TTL_MINUTES * 60,
            },
            status=202,
        )

    otp_record = _get_active_otp(email)
    if not otp_record:
        return JsonResponse({"error": "otp_expired"}, status=400)
    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        return JsonResponse({"error": "otp_too_many_attempts"}, status=429)
    if EmailOtp.hash_code(email, otp) != otp_record.code_hash:
        otp_record.attempts += 1
        otp_record.save(update_fields=["attempts"])
        return JsonResponse({"error": "otp_mismatch"}, status=400)

    otp_record.mark_used()

    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={"plan": "FREE", "is_active": False},
    )
    sub.ensure_trial_started()

    return _build_auth_response(user)


@csrf_exempt
@require_POST
def register_request_otp(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"error": "email required"}, status=400)

    try:
        validate_email(email)
    except Exception:
        return JsonResponse({"error": "invalid email"}, status=400)

    User = get_user_model()
    if User.objects.filter(email=email).exists():
        return JsonResponse({"error": "email already exists"}, status=400)

    _, retry_seconds, send_error = _create_or_refresh_otp(email)
    if send_error:
        return JsonResponse({"error": "otp_send_failed"}, status=500)
    if retry_seconds is not None:
        return JsonResponse(
            {"error": "otp_resend_too_soon", "retry_seconds": retry_seconds},
            status=429,
        )
    return JsonResponse(
        {"otp_sent": True, "expires_in_seconds": OTP_TTL_MINUTES * 60},
        status=202,
    )


@csrf_exempt
@require_POST
def register_resend_otp(request):
    return register_request_otp(request)


@csrf_exempt
@require_POST
def forgot_password_request_otp(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    try:
        validate_email(email)
    except Exception:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    User = get_user_model()
    if not User.objects.filter(email=email).exists():
        return JsonResponse({"error": "AUTH_EMAIL_NOT_FOUND"}, status=404)

    _, retry_seconds, send_error = _create_or_refresh_password_reset_otp(email)
    if send_error:
        return JsonResponse({"error": "OTP_SEND_FAILED"}, status=500)
    if retry_seconds is not None:
        return JsonResponse(
            {"error": "OTP_RESEND_TOO_SOON", "retry_seconds": retry_seconds},
            status=429,
        )

    return JsonResponse(
        {"otp_sent": True, "expires_in_seconds": OTP_TTL_MINUTES * 60},
        status=202,
    )


@csrf_exempt
@require_POST
def forgot_password_verify_otp(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    email = (payload.get("email") or "").strip().lower()
    otp = (payload.get("otp") or "").strip()
    if not email or not otp:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    try:
        validate_email(email)
    except Exception:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    User = get_user_model()
    if not User.objects.filter(email=email).exists():
        return JsonResponse({"error": "AUTH_EMAIL_NOT_FOUND"}, status=404)

    otp_record = _get_active_otp(email)
    if not otp_record:
        return JsonResponse({"error": "OTP_EXPIRED"}, status=400)
    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        return JsonResponse({"error": "OTP_TOO_MANY_ATTEMPTS"}, status=429)
    if EmailOtp.hash_code(email, otp) != otp_record.code_hash:
        otp_record.attempts += 1
        otp_record.save(update_fields=["attempts"])
        return JsonResponse({"error": "OTP_MISMATCH"}, status=400)

    return JsonResponse({"verified": True}, status=200)


@csrf_exempt
@require_POST
def forgot_password_reset_otp(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    email = (payload.get("email") or "").strip().lower()
    otp = (payload.get("otp") or "").strip()
    new_password = payload.get("new_password") or ""

    if not email or not otp or not new_password:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    try:
        validate_email(email)
    except Exception:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    if len(new_password) < 8:
        return JsonResponse({"error": "VALIDATION_ERROR"}, status=400)

    User = get_user_model()
    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"error": "AUTH_EMAIL_NOT_FOUND"}, status=404)

    otp_record = _get_active_otp(email)
    if not otp_record:
        return JsonResponse({"error": "OTP_EXPIRED"}, status=400)
    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        return JsonResponse({"error": "OTP_TOO_MANY_ATTEMPTS"}, status=429)
    if EmailOtp.hash_code(email, otp) != otp_record.code_hash:
        otp_record.attempts += 1
        otp_record.save(update_fields=["attempts"])
        return JsonResponse({"error": "OTP_MISMATCH"}, status=400)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    otp_record.mark_used()

    return JsonResponse({"password_updated": True}, status=200)


class SafeTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except get_user_model().DoesNotExist:
            return Response(
                {"error": "user_not_found"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


@csrf_exempt
@require_POST
def login(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return JsonResponse({"error": "email and password required"}, status=400)

    user = authenticate(request, username=email, password=password)
    if user is None:
        User = get_user_model()
        existing = User.objects.filter(email=email).first()
        if existing:
            user = authenticate(
                request,
                username=existing.username,
                password=password,
            )

    if user is None:
        return JsonResponse({"error": "invalid credentials"}, status=401)

    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={"plan": "FREE", "is_active": False},
    )
    sub.ensure_trial_started()

    return _build_auth_response(user)
