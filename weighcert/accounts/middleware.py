"""Login attempt lockout middleware and helper."""
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from .models import LoginAttempt


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def is_user_locked_out(username, ip_address):
    """Check if the user/IP is currently locked out."""
    attempt = LoginAttempt.objects.filter(username=username, ip_address=ip_address).first()
    if not attempt:
        return False, None
    if attempt.locked_until and attempt.locked_until > timezone.now():
        remaining = int((attempt.locked_until - timezone.now()).total_seconds() / 60) + 1
        return True, remaining
    return False, None


def record_failed_attempt(username, ip_address):
    """Record a failed login attempt; lock out if threshold reached."""
    max_attempts = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
    lockout_minutes = getattr(settings, "LOGIN_LOCKOUT_MINUTES", 10)
    
    attempt, _ = LoginAttempt.objects.get_or_create(
        username=username, ip_address=ip_address
    )
    attempt.attempts += 1
    if attempt.attempts >= max_attempts:
        attempt.locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
    attempt.save()
    return attempt.attempts, attempt.locked_until


def clear_failed_attempts(username, ip_address):
    """Clear failed attempts upon successful login."""
    LoginAttempt.objects.filter(username=username, ip_address=ip_address).delete()


class LoginAttemptMiddleware:
    """Pass-through middleware (lockout logic checked directly in login view)."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
