# backend/accounts/views.py

from django.shortcuts import redirect


def google_login_only(request):
    """
    Force all login requests to Google OAuth
    """
    return redirect("/accounts/google/login/")
