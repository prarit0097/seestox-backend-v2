from django.contrib import admin
from .models import UserSubscription


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "is_active",
        "trial_end",
        "created_at",
    )

    readonly_fields = (
        "trial_start",
        "trial_end",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "plan",
        "is_active",
    )

    search_fields = ("user__email",)
