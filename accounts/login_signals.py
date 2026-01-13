from allauth.account.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import UserSubscription


@receiver(user_logged_in)
def start_trial_on_first_login(request, user, **kwargs):
    """
    Start 7-day trial ONLY on first successful login.
    """
    try:
        sub = UserSubscription.objects.get(user=user)
    except UserSubscription.DoesNotExist:
        return

    # Trial already started → do nothing
    if sub.trial_start and sub.trial_end:
        return

    now = timezone.now()

    sub.trial_start = now
    sub.trial_end = now + timedelta(days=7)
    sub.save(update_fields=["trial_start", "trial_end", "updated_at"])
