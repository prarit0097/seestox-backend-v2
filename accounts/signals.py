from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from .models import UserSubscription


@receiver(post_save, sender=User)
def create_subscription_with_trial(sender, instance, created, **kwargs):
    if not created:
        return

    now = timezone.now()

    UserSubscription.objects.create(
        user=instance,
        plan="FREE",
        is_active=False,
        trial_start=now,
        trial_end=now + timedelta(days=7),
    )
