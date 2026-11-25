from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from inspections.models import TestSession
import secrets


def generate_verification_token() -> str:
    """Generate at least 128 bits of cryptographic randomness (hex string)."""
    return secrets.token_hex(24)


class Report(models.Model):
    """
    Issued, immutable Test Report.
    Spec Section 6.4
    """
    STATUS_ISSUED = "issued"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (STATUS_ISSUED, "Issued (Valid)"),
        (STATUS_SUPERSEDED, "Superseded by Newer Revision"),
    ]

    session = models.OneToOneField(TestSession, on_delete=models.PROTECT, related_name="report")
    report_number = models.CharField(max_length=100, db_index=True)
    revision = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ISSUED)
    issued_at = models.DateTimeField(default=timezone.now)
    approved_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="approved_reports")
    pdf_file = models.FileField(upload_to="generated_reports/", blank=True, null=True)
    snapshot_hash = models.CharField(max_length=64, help_text="SHA-256 hash of canonical snapshot JSON")
    verification_token = models.CharField(
        max_length=64, unique=True, default=generate_verification_token, db_index=True
    )
    supersedes = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="superseded_by"
    )

    class Meta:
        ordering = ["-issued_at"]
        unique_together = [("report_number", "revision")]

    def __str__(self):
        rev_str = f" Rev {self.revision}" if self.revision > 0 else ""
        return f"Report {self.report_number}{rev_str} ({self.get_status_display()})"

    @property
    def full_report_id(self) -> str:
        if self.revision > 0:
            return f"{self.report_number} Rev {self.revision}"
        return self.report_number

