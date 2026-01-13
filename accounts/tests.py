from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import UserSubscription

User = get_user_model()


class SubscriptionStatusTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="dummy123",
        )
        self.sub = UserSubscription.objects.get(user=self.user)

    def test_status_trial_active(self):
        now = timezone.now()
        self.sub.trial_start = now - timedelta(days=1)
        self.sub.trial_end = now + timedelta(days=6)
        self.sub.is_active = False
        self.sub.paid_start = None
        self.sub.paid_end = None
        self.sub.save(update_fields=[
            "trial_start",
            "trial_end",
            "is_active",
            "paid_start",
            "paid_end",
            "updated_at",
        ])

        snapshot = self.sub.status_snapshot(now=now)

        self.assertEqual(snapshot["status"], "TRIAL")
        self.assertTrue(snapshot["is_active"])
        self.assertEqual(snapshot["access_level"], "FREE")
        self.assertEqual(snapshot["days_left"], 6)

    def test_status_expired(self):
        now = timezone.now()
        self.sub.trial_start = now - timedelta(days=8)
        self.sub.trial_end = now - timedelta(seconds=1)
        self.sub.is_active = False
        self.sub.paid_start = None
        self.sub.paid_end = None
        self.sub.save(update_fields=[
            "trial_start",
            "trial_end",
            "is_active",
            "paid_start",
            "paid_end",
            "updated_at",
        ])

        snapshot = self.sub.status_snapshot(now=now)

        self.assertEqual(snapshot["status"], "EXPIRED")
        self.assertFalse(snapshot["is_active"])
        self.assertEqual(snapshot["access_level"], "FREE")
        self.assertEqual(snapshot["days_left"], 0)

    def test_status_active_paid(self):
        now = timezone.now()
        self.sub.is_active = True
        self.sub.plan = "MONTHLY"
        self.sub.paid_start = now - timedelta(days=1)
        self.sub.paid_end = now + timedelta(days=29)
        self.sub.trial_start = now - timedelta(days=10)
        self.sub.trial_end = now - timedelta(days=3)
        self.sub.save(update_fields=[
            "is_active",
            "plan",
            "paid_start",
            "paid_end",
            "trial_start",
            "trial_end",
            "updated_at",
        ])

        snapshot = self.sub.status_snapshot(now=now)

        self.assertEqual(snapshot["status"], "ACTIVE")
        self.assertTrue(snapshot["is_active"])
        self.assertEqual(snapshot["access_level"], "PRO")
