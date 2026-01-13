# backend/accounts/urls.py

from django.urls import path
from accounts.views import google_login_only

urlpatterns = [
    path("login/", google_login_only, name="account_login"),
]
