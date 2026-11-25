import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from decimal import Decimal
from core.models import LabSettings, RuleSet, ClassLimit, MpeBand, MultiIntervalCondition
from rules.engine import CLASS_LIMITS, MPE_BANDS, MULTI_INTERVAL_MIN


class Command(BaseCommand):
    help = "Initial setup for WeighCert: seed reference tables, lab settings, and initial admin."

    def handle(self, *args, **options):
        admin_password = os.environ.get("DEMO_ADMIN_PASSWORD")
        if not admin_password:
            raise CommandError("Set DEMO_ADMIN_PASSWORD in the local .env before running setup.")

        self.stdout.write("Initializing WeighCert System Setup...")

        # 1. Lab Settings
        lab = LabSettings.get_settings()
        self.stdout.write(f"✓ LabSettings verified: {lab.lab_name}")

        # 2. RuleSet
        rule_set, _ = RuleSet.objects.get_or_create(
            version_label="R76-1:2006",
            defaults={"notes": "OIML R 76-1 Edition 2006 (E)"}
        )
        self.stdout.write(f"✓ RuleSet verified: {rule_set.version_label}")

        # 3. Class Limits (Table 3)
        ClassLimit.objects.filter(rule_set=rule_set).delete()
        for row in CLASS_LIMITS:
            cls, e_min, e_max, n_min, n_max, min_factor = row
            ClassLimit.objects.create(
                rule_set=rule_set,
                accuracy_class=cls,
                e_min_g=e_min,
                e_max_g=e_max,
                n_min=n_min,
                n_max=n_max,
                min_factor=min_factor,
            )
        self.stdout.write("✓ Seeded Table 3 (Classification Limits)")

        # 4. MPE Bands (Table 6)
        MpeBand.objects.filter(rule_set=rule_set).delete()
        for cls, bands in MPE_BANDS.items():
            for m_upper, factor in bands:
                MpeBand.objects.create(
                    rule_set=rule_set,
                    accuracy_class=cls,
                    m_upper=m_upper,
                    factor=factor,
                )
        self.stdout.write("✓ Seeded Table 6 (MPE Bands)")

        # 5. Multi-Interval Conditions (Table 4)
        MultiIntervalCondition.objects.filter(rule_set=rule_set).delete()
        for cls, min_ratio in MULTI_INTERVAL_MIN.items():
            MultiIntervalCondition.objects.create(
                rule_set=rule_set,
                accuracy_class=cls,
                min_ratio=min_ratio,
            )
        self.stdout.write("✓ Seeded Table 4 (Multi-Interval Conditions)")

        # 6. First Admin Account (Spec Section 3 & 3.1)
        admin_user, created = User.objects.get_or_create(
            username="admin@weighcert.gov.in",
            defaults={
                "email": "admin@weighcert.gov.in",
                "first_name": "Nodal",
                "last_name": "Administrator",
                "is_staff": True,
                "is_superuser": True,
            }
        )
        if created:
            admin_user.set_password(admin_password)
            admin_user.save()
            admin_user.profile.role = "admin"
            admin_user.profile.designation = "Director / Chief Metrologist"
            admin_user.profile.employee_id = "LM-ADMIN-01"
            admin_user.profile.must_change_password = False
            admin_user.profile.save()
            self.stdout.write(self.style.SUCCESS("✓ Admin user created: admin@weighcert.gov.in"))
        else:
            self.stdout.write("✓ Admin user already exists.")

        self.stdout.write(self.style.SUCCESS("WeighCert initial setup completed successfully!"))
