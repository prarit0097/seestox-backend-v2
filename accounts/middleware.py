from django.shortcuts import redirect
from django.http import JsonResponse
from accounts.models import UserSubscription


# 🔒 Pages which MUST be blocked after trial expiry
PROTECTED_PAGE_PREFIXES = (
    "/search/",
    "/stock_chat/",
    "/market_news/",
    "/watchlist/",
    "/stock-detail/",
)

# 🔒 APIs which MUST be blocked after trial expiry
PROTECTED_API_PREFIXES = (
    "/analyze-stock/",
    "/api/chat/",
    "/api/v1/watchlist/",
    "/api/v1/watchlist/remove/",
    "/watchlist/data/",
    "/watchlist/add/",
    "/watchlist/remove/",
)


class TrialPaidAccessMiddleware:
    """
    HARD BLOCK middleware for trial expired users
    - Pages → redirect to /subscription/
    - APIs  → JSON 403
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        path = request.path

        # =====================================================
        # ✅ ALWAYS ALLOWED (NO CHECKS)
        # =====================================================
        if (
            path.startswith("/subscription/")
            or path.startswith("/onboarding/")
            or path.startswith("/accounts/")
            or path.startswith("/market-snapshot/")
            or path.startswith("/static/")
            or path.startswith("/media/")
            or path == "/favicon.ico"
        ):
            return self.get_response(request)

        # =====================================================
        # AUTH CHECKS
        # =====================================================
        if not request.user.is_authenticated:
            return self.get_response(request)

        if request.user.is_staff or request.user.is_superuser:
            return self.get_response(request)

        # =====================================================
        # 🔥 CRITICAL FIX: ENSURE SUBSCRIPTION EXISTS
        # =====================================================
        sub, _ = UserSubscription.objects.get_or_create(
            user=request.user,
            defaults={
                "plan": "FREE",
                "is_active": False,
            },
        )


        # 🔑 NEW USER → onboarding phase → ALLOW EVERYTHING
        if not sub.onboarding_completed:
            return self.get_response(request)

        # Paid user → allow everything (only if still valid)
        if sub.is_valid():
            return self.get_response(request)

        # Trial expired user
        if not sub.is_valid():

            # 🔴 BLOCK APIs
            for api in PROTECTED_API_PREFIXES:
                if path.startswith(api):
                    return JsonResponse(
                        {
                            "error": "Your free trial has ended",
                            "action": "upgrade",
                        },
                        status=403,
                    )

            # 🔴 BLOCK PAGES
            for page in PROTECTED_PAGE_PREFIXES:
                if path.startswith(page):
                    return redirect("/subscription/")

        # Trial active → allow
        return self.get_response(request)
