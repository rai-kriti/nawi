"""
Accounts models — Profile extends Django's built-in User.
Roles: sysadmin | inspector | officer | admin
"""
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    ROLE_SYSADMIN = "sysadmin"
    ROLE_INSPECTOR = "inspector"
    ROLE_OFFICER = "officer"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_SYSADMIN, "System Administrator"),
        (ROLE_INSPECTOR, "Inspector"),
        (ROLE_OFFICER, "Officer"),
        (ROLE_ADMIN, "Admin"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_INSPECTOR)
    designation = models.CharField(max_length=200, blank=True)
    employee_id = models.CharField(max_length=50, blank=True)
    signature = models.ImageField(upload_to="signatures/", blank=True, null=True)
    must_change_password = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.role})"

    def is_sysadmin(self):
        return self.role == self.ROLE_SYSADMIN

    def is_inspector(self):
        return self.role == self.ROLE_INSPECTOR

    def is_officer(self):
        return self.role == self.ROLE_OFFICER

    def is_admin(self):
        return self.role == self.ROLE_ADMIN


@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


class LoginAttempt(models.Model):
    """Track failed login attempts per username for lockout."""
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_attempt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("username", "ip_address")]

    def __str__(self):
        return f"{self.username} @ {self.ip_address}: {self.attempts} attempts"

