from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.views.generic import RedirectView
from django.templatetags.static import static as static_url

urlpatterns = [
    path("admin/", admin.site.urls),
    path("favicon.ico", RedirectView.as_view(url=static_url("favicon.ico"))),

    # JWT auth (mobile)
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

     # 🔐 FORCE GOOGLE LOGIN FIRST
    path("accounts/", include("accounts.urls")),

    # allauth (keep this AFTER accounts)
    path("accounts/", include("allauth.urls")),

    path("", include("api.urls")),   # ROOT + API

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
