from django.urls import path
from . import views
from . import auth_views
from . import subscription_views
from .search_views import SearchSuggestionsAPI
from . import price_views
from api import watchlist_views
from .marketnews_views import market_news_api
from django.conf.urls.static import static
from django.conf import settings
from rest_framework_simplejwt.views import TokenRefreshView



urlpatterns = [


    # 🔥 ROOT MUST BE ROUTER
    path("", views.entry_point, name="entry_point"),

    path("onboarding/", views.onboarding, name="onboarding"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("analyze-stock/", views.analyze_stock_view),
    path("search-suggestions/", SearchSuggestionsAPI.as_view()),
    path("create-order/", views.create_order),
    path("verify-payment/", views.verify_payment),
    path("subscription-status/", views.subscription),

    # 🔥 Dashboard Market Snapshot API
    path("market-snapshot/", views.market_snapshot_api),

    path("search/", views.stock_search, name="stock_search"),
    path("stock_chat/", views.stock_chat, name="stock_chat"),

    # ✅ NEW: CHAT API
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/v1/auth/register", auth_views.register, name="register"),
    path("api/v1/auth/register/request-otp", auth_views.register_request_otp, name="register_request_otp"),
    path("api/v1/auth/register/resend-otp", auth_views.register_resend_otp, name="register_resend_otp"),
    path("api/v1/auth/forgot-password/request-otp", auth_views.forgot_password_request_otp, name="forgot_password_request_otp"),
    path("api/v1/auth/forgot-password/verify-otp", auth_views.forgot_password_verify_otp, name="forgot_password_verify_otp"),
    path("api/v1/auth/forgot-password/reset-otp", auth_views.forgot_password_reset_otp, name="forgot_password_reset_otp"),
    path("api/v1/auth/login", auth_views.login, name="login"),
    path("api/v1/auth/refresh", auth_views.SafeTokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/google", auth_views.google_auth, name="google_auth"),
    path("api/v1/auth/google/", auth_views.google_auth, name="google_auth_slash"),
    path("api/auth/google/", auth_views.google_auth, name="google_auth_legacy"),
    path("api/v1/onboarding/complete", views.onboarding_complete_api, name="onboarding_complete_api"),

    path("market_news/", views.market_news, name="market_news"),
    path("prediction_history/", views.prediction_history, name="prediction_history"),
    path("profile/", views.profile, name="profile"),
    path("app_settings/", views.app_settings, name="app_settings"),
    path("about_help/", views.about_help, name="about_help"),
    path("subscription/", views.subscription, name="subscription"),
    path("trial_expired/", views.trial_expired, name="trial_expired"),
    path("terms/", views.terms, name="terms"),
    path("privacypolicy/", views.privacypolicy, name="privacypolicy"),

    # ✅ INDEX PAGE
    path("stock-detail/", views.stock_detail_page, name="stock_detail"),

    # ✅ WATCHLIST PAGE
    path("watchlist/", watchlist_views.watchlist_page, name="watchlist"),

    # ✅ WATCHLIST PRICE API
    path("watchlist/data/", watchlist_views.watchlist_data, name="watchlist_data"),

    # ACTIONS
    path("watchlist/add/", watchlist_views.add_to_watchlist),
    path("watchlist/remove/", watchlist_views.remove_from_watchlist),
    path("api/v1/watchlist", watchlist_views.watchlist_api, name="watchlist_api_noslash"),
    path("api/v1/watchlist/", watchlist_views.watchlist_api, name="watchlist_api"),
    path("api/v1/watchlist/add", watchlist_views.watchlist_add_api, name="watchlist_add_api_noslash"),
    path("api/v1/watchlist/add/", watchlist_views.watchlist_add_api, name="watchlist_add_api"),
    path("api/v1/watchlist/remove", watchlist_views.watchlist_remove_api, name="watchlist_remove_api_noslash"),
    path("api/v1/watchlist/remove/", watchlist_views.watchlist_remove_api, name="watchlist_remove_api"),

    path("api/market-news/", market_news_api, name="market_news_api"),
    path("api/v1/market-news", market_news_api, name="market_news_api_v1"),
    path("api/v1/news/market", market_news_api, name="market_news_api_v1_alias"),
    path("api/v1/market/snapshot", views.market_snapshot_api, name="market_snapshot_api_v1"),
    path("api/v1/quotes", price_views.quotes_api, name="quotes_api_noslash"),
    path("api/v1/quotes/", price_views.quotes_api, name="quotes_api"),
    path("api/v1/stock-detail/", price_views.stock_detail_api, name="stock_detail_api"),
    path("api/v1/subscription/plans", subscription_views.subscription_plans, name="subscription_plans"),
    path("api/v1/subscription/status", subscription_views.subscription_status, name="subscription_status"),
    path("api/v1/subscription/checkout", subscription_views.subscription_checkout, name="subscription_checkout"),
    path("api/v1/subscription/verify", subscription_views.subscription_verify, name="subscription_verify"),
    path("api/v1/profile", views.profile_api, name="profile_api_noslash"),
    path("api/v1/profile/", views.profile_api, name="profile_api"),
    path("api/v1/profile/update", views.profile_update_api, name="profile_update_api_noslash"),
    path("api/v1/profile/update/", views.profile_update_api, name="profile_update_api"),
    path("api/v1/profile/avatar", views.profile_avatar_api, name="profile_avatar_api_noslash"),
    path("api/v1/profile/avatar/", views.profile_avatar_api, name="profile_avatar_api"),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
