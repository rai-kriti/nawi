from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from registry.models import Instrument, TestWeight
from rules.engine import multiplier_for_inspection


class TestSession(models.Model):
    """
    Test session (docket) for an instrument verification.
    Spec Section 6.3 & 8
    """
    INSPECTION_INITIAL = "initial_verification"
    INSPECTION_SUBSEQUENT = "subsequent_verification"
    INSPECTION_SERVICE = "service_inspection"
    INSPECTION_CHOICES = [
        (INSPECTION_INITIAL, "Initial Verification (1× MPE)"),
        (INSPECTION_SUBSEQUENT, "Subsequent Verification (1× MPE)"),
        (INSPECTION_SERVICE, "Service Inspection (2× MPE)"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_RETURNED = "returned"
    STATUS_ISSUED = "issued"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_SUPERSEDED, "Superseded"),
    ]

    RESULT_PASS = "pass"
    RESULT_FAIL = "fail"
    RESULT_INCOMPLETE = "incomplete"
    RESULT_CHOICES = [
        (RESULT_PASS, "PASS"),
        (RESULT_FAIL, "FAIL"),
        (RESULT_INCOMPLETE, "INCOMPLETE"),
    ]

    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="test_sessions")
    inspection_type = models.CharField(max_length=30, choices=INSPECTION_CHOICES, default=INSPECTION_INITIAL)
    limit_multiplier = models.PositiveSmallIntegerField(default=1)
    test_date = models.DateField(default=timezone.now)
    place_type = models.CharField(
        max_length=30,
        choices=[("place_of_use", "Place of Use"), ("manufacturer", "Manufacturer Site"), ("other", "Other")],
        default="place_of_use"
    )
    location_text = models.CharField(max_length=255, blank=True)
    gravity_note = models.CharField(max_length=200, blank=True)
    ambient_notes = models.CharField(
        max_length=255, blank=True,
        default="Temp: 20.4 °C | RH: 51.2% | Baro: 1013.1 hPa"
    )

    inspector = models.ForeignKey(User, on_delete=models.PROTECT, related_name="inspections")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    overall_result = models.CharField(max_length=20, choices=RESULT_CHOICES, default=RESULT_INCOMPLETE)
    remarks = models.TextField(blank=True)
    officer_comment = models.TextField(blank=True, help_text="Mandatory if returned by Officer.")
    rule_set_version = models.CharField(max_length=50, default="R76-1:2006")

    # Checklists (Stored as JSON dictionaries)
    visual_inspection = models.JSONField(
        default=dict, blank=True,
        help_text="Checklist results for class, Min/Max/e/d, software ID, module IDs, inscriptions, stamp mark place"
    )
    conformity_declaration = models.JSONField(
        default=dict, blank=True,
        help_text="Conformity items: devices operate correctly (zero, tare, calc), construction material"
    )
    marking_securing = models.JSONField(
        default=dict, blank=True,
        help_text="Marks applied (yes/no), mark type (stamp/sticker), serial/ref, next due date"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        # Always derive limit multiplier from inspection type
        self.limit_multiplier = multiplier_for_inspection(self.inspection_type)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Test #{self.id} on {self.instrument} ({self.get_status_display()})"


class SessionWeight(models.Model):
    """Standard weights selected for a test session."""
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="session_weights")
    weight = models.ForeignKey(TestWeight, on_delete=models.PROTECT)
    used_in_steps = models.CharField(max_length=150, blank=True, default="Accuracy, Eccentricity, Repeatability")

    class Meta:
        unique_together = [("session", "weight")]

    def __str__(self):
        return f"{self.session_id} - {self.weight.label_id}"


class ZeroCheck(models.Model):
    """Step 2: Accuracy of zero-setting device [4.5.2, A.4.2.3]"""
    session = models.OneToOneField(TestSession, on_delete=models.CASCADE, related_name="zero_check")
    indication_zero = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    delta_l = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    computed_e0 = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    passed = models.BooleanField(default=False)

    # Optional zero-range procedure fields
    initial_range_measured = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    tracking_range_measured = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    range_limit_passed = models.BooleanField(null=True, blank=True)

    def __str__(self):
        return f"ZeroCheck #{self.id} E0={self.computed_e0} (Pass={self.passed})"


class AccuracyReading(models.Model):
    """Step 3: Accuracy weighing test row [A.4.4.1]"""
    PHASE_UP = "up"
    PHASE_DOWN = "down"
    PHASE_CHOICES = [(PHASE_UP, "Increasing (Up)"), (PHASE_DOWN, "Decreasing (Down)")]

    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="accuracy_readings")
    sequence = models.PositiveIntegerField(default=1)
    phase = models.CharField(max_length=10, choices=PHASE_CHOICES, default=PHASE_UP)
    tare_kind = models.CharField(max_length=20, default="none")
    tare_value_g = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))

    # Inputs (Grams)
    load_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Applied Load L (g)")
    weights_used_text = models.CharField(max_length=255, blank=True)
    indication = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Indication I (g)")
    delta_l = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, verbose_name="ΔL (g)")

    # Stored Server-Computed Values
    m = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    range_order = models.PositiveIntegerField(default=1)
    e_used = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("1"))
    P = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    E = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    E0_used = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    Ec = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    mpe = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    passed = models.BooleanField(default=False)
    weight_error_status = models.CharField(max_length=10, choices=[("ok","OK"),("warn","Warning")], default="ok")

    class Meta:
        ordering = ["phase", "sequence"]

    def __str__(self):
        return f"Acc #{self.sequence} ({self.phase}) L={self.load_g}g -> Ec={self.Ec}g (Pass={self.passed})"


class TareCheck(models.Model):
    """Step 3 Tare setting check and net load test [4.6.3]"""
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="tare_checks")
    tare_kind = models.CharField(max_length=20, choices=[("subtractive","Subtractive"),("additive","Additive")])
    tare_load_g = models.DecimalField(max_digits=18, decimal_places=6)
    measured_zero_error = models.DecimalField(max_digits=18, decimal_places=6)
    limit = models.DecimalField(max_digits=18, decimal_places=6)
    passed = models.BooleanField(default=False)

    def __str__(self):
        return f"TareCheck #{self.id} ({self.tare_kind}) Pass={self.passed}"


class RepeatabilityTest(models.Model):
    """Step 4: Repeatability test session summary [3.6.1, A.4.10]"""
    session = models.OneToOneField(TestSession, on_delete=models.CASCADE, related_name="repeatability_test")
    load_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Test Load (~0.8 Max)")
    required_count = models.PositiveIntegerField(default=3, help_text="3 for III/IIII, 6 for I/II")
    computed_spread = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    spread_limit = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    passed = models.BooleanField(default=False)

    def __str__(self):
        return f"Repeatability #{self.id} (Spread={self.computed_spread}g, Pass={self.passed})"


class RepeatabilityReading(models.Model):
    """Individual weighing cycle in repeatability test."""
    test = models.ForeignKey(RepeatabilityTest, on_delete=models.CASCADE, related_name="readings")
    sequence = models.PositiveIntegerField(default=1)
    indication = models.DecimalField(max_digits=18, decimal_places=6)
    delta_l = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    computed_error = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    passed = models.BooleanField(default=False)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return f"Rep #{self.sequence}: I={self.indication}g Error={self.computed_error}g"


class EccentricityTest(models.Model):
    """Step 5: Eccentric loading test [3.6.2, A.4.7]"""
    MODE_4_SUPPORTS = "up_to_4_supports"
    MODE_MORE_SUPPORTS = "more_than_4_supports"
    MODE_TANK_HOPPER = "tank_hopper"
    MODE_ROLLING = "rolling_load"
    MODE_CHOICES = [
        (MODE_4_SUPPORTS, "Up to 4 Points of Support (1/3 Max)"),
        (MODE_MORE_SUPPORTS, "More than 4 Supports (1/(n-1) Max)"),
        (MODE_TANK_HOPPER, "Tank / Hopper Receptor (1/10 Max)"),
        (MODE_ROLLING, "Rolling Load (0.8 Max cap)"),
    ]

    session = models.OneToOneField(TestSession, on_delete=models.CASCADE, related_name="eccentricity_test")
    mode = models.CharField(max_length=30, choices=MODE_CHOICES, default=MODE_4_SUPPORTS)
    required_load_g = models.DecimalField(max_digits=18, decimal_places=6)
    actual_load_g = models.DecimalField(max_digits=18, decimal_places=6)
    positions_count = models.PositiveIntegerField(default=4)
    sketch_positions = models.JSONField(default=list, blank=True)
    passed = models.BooleanField(default=False)
    is_omitted = models.BooleanField(default=False)
    omission_reason = models.TextField(blank=True)

    def __str__(self):
        return f"Eccentricity #{self.id} ({self.mode}, Pass={self.passed})"


class EccentricityReading(models.Model):
    """Reading at one position on the load receptor."""
    test = models.ForeignKey(EccentricityTest, on_delete=models.CASCADE, related_name="readings")
    position_label = models.CharField(max_length=100)
    indication = models.DecimalField(max_digits=18, decimal_places=6)
    delta_l = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    computed_E = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    E0_used = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    Ec = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    mpe = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    passed = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"EccPos {self.position_label}: I={self.indication}g -> Ec={self.Ec}g"


class DiscriminationReading(models.Model):
    """Step 6 (Conditional): Discrimination test [3.8]"""
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="discrimination_readings")
    load_step = models.CharField(max_length=20, choices=[("Min","Min"),("half_max","1/2 Max"),("Max","Max")])
    load_g = models.DecimalField(max_digits=18, decimal_places=6)
    extra_load_g = models.DecimalField(max_digits=18, decimal_places=6)
    visible_displacement = models.BooleanField(default=True)
    displacement_mm = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    threshold = models.DecimalField(max_digits=18, decimal_places=6)
    passed = models.BooleanField(default=True)

    def __str__(self):
        return f"Discrimination {self.load_step}: Pass={self.passed}"


class SensitivityReading(models.Model):
    """Step 6 (Conditional): Sensitivity of non-self-indicating instrument [6.1]"""
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="sensitivity_readings")
    load_g = models.DecimalField(max_digits=18, decimal_places=6)
    extra_load_g = models.DecimalField(max_digits=18, decimal_places=6)
    displacement_mm = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0"))
    passed = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Sensitivity at {self.load_g}g: Pass={self.passed}"


class TiltCheck(models.Model):
    """Step 6 (Conditional): Tilt test for mobile instruments [4.18]"""
    session = models.OneToOneField(TestSession, on_delete=models.CASCADE, related_name="tilt_check")
    passed = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"TiltCheck: Pass={self.passed}"

