from django.db import models
from django.utils import timezone
from decimal import Decimal


class LabSettings(models.Model):
    """
    Single-row organization & lab settings.
    Spec Section 6.1
    """
    lab_name = models.CharField(max_length=255, default="Directorate of Legal Metrology")
    address = models.TextField(default="Central Standards Laboratory, New Delhi, India")
    logo = models.ImageField(upload_to="lab_logos/", blank=True, null=True)
    authority_text = models.CharField(
        max_length=255,
        default="Government of India / Department of Consumer Affairs"
    )
    accreditation_number = models.CharField(max_length=100, default="NABL-LM-2024-001")
    report_number_prefix = models.CharField(max_length=20, default="WC/DEL")
    report_footer_text = models.CharField(
        max_length=255,
        default="This test report is issued in accordance with OIML R 76-1:2006 and Legal Metrology Act 2009."
    )
    allow_simplified_error = models.BooleanField(
        default=False,
        help_text="If enabled, allows simple E = I - L without delta_L when d > 0.2e. Affects report notes."
    )
    report_counter = models.PositiveIntegerField(default=0)
    counter_year = models.PositiveIntegerField(default=timezone.now().year)
    year_reset_policy = models.CharField(
        max_length=20,
        choices=[("calendar", "Calendar Year (Jan 1)"), ("fiscal", "Fiscal Year (Apr 1)"), ("never", "Never")],
        default="calendar"
    )

    class Meta:
        verbose_name = "Lab Settings"
        verbose_name_plural = "Lab Settings"

    def __str__(self):
        return self.lab_name

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class RuleSet(models.Model):
    """Seeded regulatory rule-set version. Spec Section 6.6"""
    version_label = models.CharField(max_length=50, unique=True, default="R76-1:2006")
    effective_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, default="OIML Recommendation R 76-1, Edition 2006 (E)")

    def __str__(self):
        return self.version_label


class ClassLimit(models.Model):
    """Table 3 classification limits seeded per rule-set."""
    rule_set = models.ForeignKey(RuleSet, on_delete=models.CASCADE, related_name="class_limits")
    accuracy_class = models.CharField(max_length=10, choices=[("I","I"),("II","II"),("III","III"),("IIII","IIII")])
    e_min_g = models.DecimalField(max_digits=15, decimal_places=6)
    e_max_g = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    n_min = models.PositiveIntegerField()
    n_max = models.PositiveIntegerField(null=True, blank=True)
    min_factor = models.PositiveIntegerField(help_text="Min >= min_factor * d")

    def __str__(self):
        return f"{self.rule_set} Class {self.accuracy_class} (n: {self.n_min}-{self.n_max})"


class MpeBand(models.Model):
    """Table 6 MPE bands seeded per rule-set."""
    rule_set = models.ForeignKey(RuleSet, on_delete=models.CASCADE, related_name="mpe_bands")
    accuracy_class = models.CharField(max_length=10, choices=[("I","I"),("II","II"),("III","III"),("IIII","IIII")])
    m_upper = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    factor = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 0.5, 1.0, 1.5")

    def __str__(self):
        return f"{self.rule_set} Class {self.accuracy_class} m<={self.m_upper} -> {self.factor}e"


class MultiIntervalCondition(models.Model):
    """Table 4 multi-interval condition seeded per rule-set."""
    rule_set = models.ForeignKey(RuleSet, on_delete=models.CASCADE, related_name="multi_interval_conditions")
    accuracy_class = models.CharField(max_length=10, choices=[("I","I"),("II","II"),("III","III"),("IIII","IIII")])
    min_ratio = models.PositiveIntegerField(help_text="Minimum Max_i / e_{i+1}")

    def __str__(self):
        return f"{self.rule_set} Class {self.accuracy_class} ratio >= {self.min_ratio}"

