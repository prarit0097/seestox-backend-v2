from django.utils import timezone


def trial_status(request):
    """
    Provides trial / subscription data to all templates
    - Header badge
    - Subscription page trial info
    """

    if not request.user.is_authenticated:
        return {}

    sub = getattr(request.user, "usersubscription", None)
    if not sub:
        return {}

    now = timezone.now()

    context = {}

    # =========================
    # PAID USER
    # =========================
    if sub.is_active and sub.paid_end and sub.paid_end >= now:
        context["trial_badge"] = {
            "label": "PRO",
            "type": "paid",
        }
        context["subscription_status"] = "PAID"
        return context

    # =========================
    # TRIAL USER
    # =========================
    if sub.trial_start and sub.trial_end:

        context["trial_start"] = sub.trial_start
        context["trial_end"] = sub.trial_end

        remaining = (sub.trial_end - now).days

        if remaining > 0:
            context["trial_badge"] = {
                "label": f"Trial: {remaining} days left",
                "type": "trial",
            }
            context["subscription_status"] = "TRIAL_ACTIVE"
        else:
            context["trial_badge"] = {
                "label": "Trial Expired",
                "type": "expired",
            }
            context["subscription_status"] = "TRIAL_EXPIRED"

    return context
