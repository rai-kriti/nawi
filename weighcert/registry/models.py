from django.db import models
from django.utils import timezone
from decimal import Decimal
import uuid


class Owner(models.Model):
    """Owner / applicant of the weighing instrument."""
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    gstin_or_id = models.CharField(max_length=100, blank=True, verbose_name="GSTIN / Registration ID")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Instrument(models.Model):
    """
    Non-Automatic Weighing Instrument (NAWI).
    Spec Section 6.2
    """
    CLASS_I = "I"
    CLASS_II = "II"
    CLASS_III = "III"
    CLASS_IIII = "IIII"
    CLASS_CHOICES = [
        (CLASS_I, "Class I (Special Accuracy)"),
        (CLASS_II, "Class II (High Accuracy)"),
        (CLASS_III, "Class III (Medium Accuracy)"),
        (CLASS_IIII, "Class IIII (Ordinary Accuracy)"),
    ]

    INDICATION_DIGITAL = "digital"
    INDICATION_ANALOG = "analog_self_indicating"
    INDICATION_NON_SELF = "non_self_indicating"
    INDICATION_CHOICES = [
        (INDICATION_DIGITAL, "Digital Indication"),
        (INDICATION_ANALOG, "Analog Self-Indicating"),
        (INDICATION_NON_SELF, "Non-Self-Indicating"),
    ]

    RECEPTOR_PLATFORM = "platform"
    RECEPTOR_TANK_HOPPER = "tank_hopper"
    RECEPTOR_ROLLING = "rolling_load"
    RECEPTOR_OTHER = "other"
    RECEPTOR_CHOICES = [
        (RECEPTOR_PLATFORM, "Platform Receptor (Standard)"),
        (RECEPTOR_TANK_HOPPER, "Tank / Hopper Receptor"),
        (RECEPTOR_ROLLING, "Rolling Load (Weighbridge / Rail)"),
        (RECEPTOR_OTHER, "Other Special Receptor"),
    ]

    UNIT_CHOICES = [
        ("g", "Grams (g)"),
        ("kg", "Kilograms (kg)"),
        ("mg", "Milligrams (mg)"),
        ("t", "Tonnes (t)"),
    ]

    instrument_id = models.CharField(max_length=50, unique=True, blank=True)
    owner = models.ForeignKey(Owner, on_delete=models.PROTECT, related_name="instruments")
    manufacturer = models.CharField(max_length=200)
    model = models.CharField(max_length=150, blank=True)
    serial_number = models.CharField(max_length=150)
    type_approval_number = models.CharField(max_length=150, blank=True)
    software_id = models.CharField(max_length=100, blank=True)
    year_of_manufacture = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("decommissioned", "Decommissioned")],
        default="active"
    )

    # Metrological Characteristics (Stored in GRAMS as Decimal)
    accuracy_class = models.CharField(max_length=10, choices=CLASS_CHOICES, default=CLASS_III)
    max_capacity_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Max (g)")
    min_capacity_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Min (g)")
    e_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="e (g)")
    d_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="d (g)")
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default="kg")
    is_multi_interval = models.BooleanField(default=False)
    indication_type = models.CharField(max_length=30, choices=INDICATION_CHOICES, default=INDICATION_DIGITAL)
    is_grading = models.BooleanField(default=False, help_text="Reduces Min requirement to 5 e [3.4.3]")

    # Tare and Zero Devices
    has_tare_device = models.BooleanField(default=False)
    tare_type = models.CharField(
        max_length=20,
        choices=[("additive", "Additive (T+)"), ("subtractive", "Subtractive (T-)"), ("both", "Both"), ("preset", "Preset Tare")],
        default="subtractive",
        blank=True
    )
    max_additive_tare_g = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    max_subtractive_tare_g = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    zero_setting_type = models.CharField(
        max_length=30,
        choices=[
            ("none", "None"),
            ("non_automatic", "Non-Automatic"),
            ("semi_automatic", "Semi-Automatic"),
            ("automatic_or_tracking", "Automatic / Zero-Tracking"),
            ("initial", "Initial Zero-Setting"),
        ],
        default="semi_automatic"
    )
    used_for_commercial = models.BooleanField(default=True)
    max_safe_load_g = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    special_temperature_limits = models.CharField(max_length=100, blank=True)

    # Load Receptor
    load_receptor_type = models.CharField(max_length=30, choices=RECEPTOR_CHOICES, default=RECEPTOR_PLATFORM)
    points_of_support = models.PositiveIntegerField(default=4)
    is_mobile = models.BooleanField(default=False)

    # Location of Use
    place_of_use = models.CharField(max_length=255, blank=True)
    location_address = models.TextField(blank=True)
    gravity_zone = models.CharField(max_length=150, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.instrument_id:
            short_uuid = uuid.uuid4().hex[:6].upper()
            self.instrument_id = f"INST-{short_uuid}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.manufacturer} {self.model} (SN: {self.serial_number}) [{self.instrument_id}]"

    @property
    def n(self) -> Decimal:
        if self.e_g and self.e_g > 0:
            return self.max_capacity_g / self.e_g
        return Decimal("0")

    @property
    def max_display(self) -> str:
        return self.format_mass(self.max_capacity_g)

    @property
    def min_display(self) -> str:
        return self.format_mass(self.min_capacity_g)

    @property
    def e_display(self) -> str:
        return self.format_mass(self.e_g)

    @property
    def d_display(self) -> str:
        return self.format_mass(self.d_g)

    def format_mass(self, mass_g: Decimal) -> str:
        """Helper to format grams into instrument's display unit."""
        if mass_g is None:
            return ""
        if self.unit == "kg":
            val = mass_g / Decimal("1000")
            return f"{val.normalize():f} kg"
        elif self.unit == "mg":
            val = mass_g * Decimal("1000")
            return f"{val.normalize():f} mg"
        elif self.unit == "t":
            val = mass_g / Decimal("1000000")
            return f"{val.normalize():f} t"
        return f"{mass_g.normalize():f} g"


class InstrumentRange(models.Model):
    """
    Partial weighing range for multi-interval instruments.
    Spec Section 6.2
    """
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="ranges")
    order = models.PositiveIntegerField(default=1)
    max_i_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Max_i (g)")
    e_i_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="e_i (g)")
    d_i_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="d_i (g)")

    class Meta:
        ordering = ["order"]
        unique_together = [("instrument", "order")]

    def __str__(self):
        return f"Range {self.order}: Max={self.max_i_g}g, e={self.e_i_g}g"

    @property
    def n_i(self) -> Decimal:
        if self.e_i_g and self.e_i_g > 0:
            return self.max_i_g / self.e_i_g
        return Decimal("0")


class TestWeight(models.Model):
    """
    Standard test weights register with calibration due dates.
    Spec Section 4.11 & 6.2
    """
    CLASS_CHOICES = [
        ("E1", "OIML Class E1"),
        ("E2", "OIML Class E2"),
        ("F1", "OIML Class F1"),
        ("F2", "OIML Class F2"),
        ("M1", "OIML Class M1"),
        ("M2", "OIML Class M2"),
        ("M3", "OIML Class M3"),
    ]

    label_id = models.CharField(max_length=50, unique=True, verbose_name="Weight ID / Label")
    nominal_mass_g = models.DecimalField(max_digits=18, decimal_places=6, verbose_name="Nominal Mass (g)")
    oiml_class = models.CharField(max_length=10, choices=CLASS_CHOICES, default="M1")
    certificate_number = models.CharField(max_length=100)
    certified_correction_g = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        verbose_name="Certified Correction / Error (g)"
    )
    expanded_uncertainty_g = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        verbose_name="Expanded Uncertainty U (g)"
    )
    calibrated_on = models.DateField(default=timezone.now)
    calibration_due_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["nominal_mass_g"]

    def __str__(self):
        return f"{self.label_id} ({self.nominal_mass_g}g - Class {self.oiml_class})"

    @property
    def is_expired(self) -> bool:
        return self.calibration_due_date < timezone.now().date()

    @property
    def is_due_soon(self) -> bool:
        """Due within 30 days."""
        today = timezone.now().date()
        return today <= self.calibration_due_date <= (today + timezone.timedelta(days=30))

    @property
    def true_mass_g(self) -> Decimal:
        return self.nominal_mass_g + self.certified_correction_g
