from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import math


class UserSubscription(models.Model):
    PLAN_CHOICES = (
        ("FREE", "Free"),
        ("MONTHLY", "Monthly"),
        ("YEARLY", "Yearly"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default="FREE"
    )

    is_active = models.BooleanField(default=False)

    # 🔹 Trial period (Google login default)
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)

    # 🔹 Paid subscription period
    paid_start = models.DateTimeField(null=True, blank=True)
    paid_end = models.DateTimeField(null=True, blank=True)

    # ================================
    # 🔹 ONBOARDING STATE (NEW)
    # ================================
    onboarding_completed = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ================================
    # ACTIVATION HELPERS
    # ================================

    def activate_monthly(self):
        now = timezone.now()
        self.plan = "MONTHLY"
        self.is_active = True
        self.paid_start = now
        self.paid_end = now + timedelta(days=30)
        self.trial_start = None
        self.trial_end = None
        self.save(update_fields=[
            "plan", "is_active", "paid_start", "paid_end",
            "trial_start", "trial_end", "updated_at"
        ])

    def activate_yearly(self):
        now = timezone.now()
        self.plan = "YEARLY"
        self.is_active = True
        self.paid_start = now
        self.paid_end = now + timedelta(days=365)
        self.trial_start = None
        self.trial_end = None
        self.save(update_fields=[
            "plan", "is_active", "paid_start", "paid_end",
            "trial_start", "trial_end", "updated_at"
        ])

    # ================================
    # ONBOARDING HELPERS (NEW)
    # ================================

    def complete_onboarding(self):
        self.onboarding_completed = True
        self.onboarding_completed_at = timezone.now()
        self.save(update_fields=[
            "onboarding_completed",
            "onboarding_completed_at",
            "updated_at"
        ])

    # ================================
    # VALIDITY CHECK (CORE LOGIC)
    # ================================

    def is_valid(self):
        """
        Central truth for access control.
        Used by APIs, UI badge, feature gating.
        """
        now = timezone.now()

        # Active paid user
        if self.is_active and self.paid_end:
            return self.paid_end >= now

        # Trial user
        if self.trial_end:
            return self.trial_end >= now

        return False

    def ensure_trial_started(self, now=None):
        """
        Ensure a 7-day trial exists. Returns True if updated.
        """
        if self.trial_start and self.trial_end:
            return False

        now = now or timezone.now()
        self.trial_start = now
        self.trial_end = now + timedelta(days=7)
        self.save(update_fields=["trial_start", "trial_end", "updated_at"])
        return True

    def status_snapshot(self, now=None):
        now = now or timezone.now()

        paid_active = self.is_active and self.paid_end and now < self.paid_end
        trial_active = self.trial_end and now < self.trial_end

        if paid_active:
            status = "ACTIVE"
            access_level = "PRO"
            is_active = True
        elif trial_active:
            status = "TRIAL"
            access_level = "FREE"
            is_active = True
        else:
            status = "EXPIRED"
            access_level = "FREE"
            is_active = False

        days_left = 0
        if self.trial_end:
            delta_seconds = (self.trial_end - now).total_seconds()
            days_left = max(0, int(math.ceil(delta_seconds / 86400.0)))

        return {
            "status": status,
            "is_active": is_active,
            "access_level": access_level,
            "trial_started_at": self.trial_start,
            "trial_ends_at": self.trial_end,
            "days_left": days_left,
            "current_period_start": self.paid_start,
            "current_period_end": self.paid_end,
            "plan": self.plan if paid_active else None,
        }

    def __str__(self):
        return f"{self.user.email} | {self.plan}"

class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email
