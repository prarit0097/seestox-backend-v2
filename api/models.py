import hashlib

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="watchlist_items")
    symbol = models.CharField(max_length=20)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "symbol")
        ordering = ["-added_on"]

    def __str__(self):
        return f"{self.user.email} ƒ+' {self.symbol}"


class EmailOtp(models.Model):
    email = models.EmailField()
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    resend_count = models.PositiveIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "expires_at"]),
            models.Index(fields=["email", "used_at"]),
        ]

    @staticmethod
    def hash_code(email: str, code: str) -> str:
        payload = f"{email}:{code}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
