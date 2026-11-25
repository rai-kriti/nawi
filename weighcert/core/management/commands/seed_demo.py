import os
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from registry.models import Owner, Instrument, InstrumentRange, TestWeight
from inspections.models import (
    TestSession, SessionWeight, ZeroCheck, AccuracyReading,
    RepeatabilityTest, RepeatabilityReading, EccentricityTest, EccentricityReading
)
from reports.models import Report
from reports.snapshot import save_report_snapshot
from reports.pdf import generate_and_save_pdf
from core.numbering import generate_next_report_number
from rules.engine import mpe_lookup, error_calc, check_compliance, RangeSpec


class Command(BaseCommand):
    help = "Seed demo data for WeighCert: staff accounts, owners, weights, sample instruments, and test sessions."

    def handle(self, *args, **options):
        inspector_password = os.environ.get("DEMO_INSPECTOR_PASSWORD")
        officer_password = os.environ.get("DEMO_OFFICER_PASSWORD")
        if not inspector_password or not officer_password:
            raise CommandError(
                "Set DEMO_INSPECTOR_PASSWORD and DEMO_OFFICER_PASSWORD in the local .env before seeding demo data."
            )

        # Run base setup first
        call_command("setup_weighcert")
        self.stdout.write("Seeding comprehensive demo dataset...")

        # 1. Staff Accounts
        # Inspector
        insp_user, created = User.objects.get_or_create(
            username="inspector.singh@gov.in",
            defaults={"first_name": "Vikram", "last_name": "Singh", "email": "inspector.singh@gov.in"}
        )
        if created:
            insp_user.set_password(inspector_password)
            insp_user.save()
            insp_user.profile.role = "inspector"
            insp_user.profile.designation = "Senior Inspector (Legal Metrology)"
            insp_user.profile.employee_id = "INSP-DL-042"
            insp_user.profile.must_change_password = False
            insp_user.profile.save()
            self.stdout.write("✓ Created Inspector: inspector.singh@gov.in")

        # Officer
        off_user, created = User.objects.get_or_create(
            username="officer.sharma@gov.in",
            defaults={"first_name": "Rajesh", "last_name": "Sharma", "email": "officer.sharma@gov.in"}
        )
        if created:
            off_user.set_password(officer_password)
            off_user.save()
            off_user.profile.role = "officer"
            off_user.profile.designation = "Assistant Controller of Legal Metrology"
            off_user.profile.employee_id = "ACLM-NZ-108"
            off_user.profile.must_change_password = False
            off_user.profile.save()
            self.stdout.write("✓ Created Officer: officer.sharma@gov.in")

        admin_user = User.objects.get(username="admin@weighcert.gov.in")

        # 2. Standard Weights Register
        today = timezone.now().date()
        weights_data = [
            ("WT-E2-100G", Decimal("100"), "E2", "CERT-NPL-2024-089", Decimal("0.0001"), Decimal("0.00005"), today + timedelta(days=200)),
            ("WT-E2-200G", Decimal("200"), "E2", "CERT-NPL-2024-090", Decimal("0.0002"), Decimal("0.00008"), today + timedelta(days=200)),
            ("WT-F1-500G", Decimal("500"), "F1", "CERT-NPL-2024-112", Decimal("0.001"), Decimal("0.0005"), today + timedelta(days=150)),
            ("WT-F1-1KG",  Decimal("1000"), "F1", "CERT-NPL-2024-115", Decimal("0.002"), Decimal("0.001"), today + timedelta(days=150)),
            ("WT-M1-2KG",  Decimal("2000"), "M1", "CERT-RRSL-2024-401", Decimal("0.05"), Decimal("0.02"), today + timedelta(days=90)),
            ("WT-M1-5KG",  Decimal("5000"), "M1", "CERT-RRSL-2024-402", Decimal("0.10"), Decimal("0.05"), today + timedelta(days=15)), # Due soon!
            ("WT-M1-10KG", Decimal("10000"), "M1", "CERT-RRSL-2024-405", Decimal("0.20"), Decimal("0.10"), today + timedelta(days=120)),
            ("WT-M1-20KG", Decimal("20000"), "M1", "CERT-RRSL-2024-408", Decimal("0.40"), Decimal("0.20"), today - timedelta(days=5)), # Expired!
        ]
        test_weights = {}
        for wid, nom, oiml, cert, corr, unc, due in weights_data:
            w, _ = TestWeight.objects.get_or_create(
                label_id=wid,
                defaults={
                    "nominal_mass_g": nom,
                    "oiml_class": oiml,
                    "certificate_number": cert,
                    "certified_correction_g": corr,
                    "expanded_uncertainty_g": unc,
                    "calibrated_on": today - timedelta(days=180),
                    "calibration_due_date": due,
                    "is_active": True,
                }
            )
            test_weights[wid] = w
        self.stdout.write(f"✓ Seeded {len(weights_data)} Standard Test Weights")

        # 3. Owners
        owner1, _ = Owner.objects.get_or_create(
            name="Sun Pharma Laboratories Ltd.",
            defaults={"address": "Okhla Industrial Area Phase-I, New Delhi", "contact_person": "Dr. A. Verma", "phone": "011-26987412", "email": "verma.a@sunpharma.com", "gstin_or_id": "07AAACS1429B1Z8"}
        )
        owner2, _ = Owner.objects.get_or_create(
            name="Kirana Wholesale Mandi & Logistics",
            defaults={"address": "Chandni Chowk Depot No. 4, Old Delhi", "contact_person": "Ramesh Kumar Gupta", "phone": "9811234567", "email": "gupta.kirana@gmail.com", "gstin_or_id": "07AABCK8891C1ZT"}
        )
        owner3, _ = Owner.objects.get_or_create(
            name="Avery India Logistics & Terminal",
            defaults={"address": "FCI Grain Silo No. 4, Narela Hub, Delhi", "contact_person": "Col. S. Deshmukh", "phone": "011-27781200", "email": "silo4@fci.gov.in", "gstin_or_id": "07AAACF0001D1ZZ"}
        )

        # 4. Three Sample Instruments (Spec Requirement)
        # Instrument 1: Class III single range (Max 10 kg, e=1g, d=1g)
        inst1, _ = Instrument.objects.get_or_create(
            serial_number="ESS-2024-098",
            defaults={
                "instrument_id": "INST-DL-3811",
                "owner": owner2,
                "manufacturer": "Essae Teraoka",
                "model": "DS-215 Counter Scale",
                "type_approval_number": "IND/09/2022/411",
                "accuracy_class": Instrument.CLASS_III,
                "max_capacity_g": Decimal("10000"),
                "min_capacity_g": Decimal("20"),
                "e_g": Decimal("1"),
                "d_g": Decimal("1"),
                "unit": "kg",
                "is_multi_interval": False,
                "indication_type": Instrument.INDICATION_DIGITAL,
                "load_receptor_type": Instrument.RECEPTOR_PLATFORM,
                "points_of_support": 4,
                "place_of_use": "Chandni Chowk Depot",
            }
        )

        # Instrument 2: Class II (Max 500 g, e=0.1g, d=0.01g)
        inst2, _ = Instrument.objects.get_or_create(
            serial_number="SAR-882190",
            defaults={
                "instrument_id": "INST-DL-3891",
                "owner": owner1,
                "manufacturer": "Sartorius Lab Instruments",
                "model": "Practum 213 Precision Balance",
                "type_approval_number": "IND/09/2021/189",
                "accuracy_class": Instrument.CLASS_II,
                "max_capacity_g": Decimal("500"),
                "min_capacity_g": Decimal("2"),
                "e_g": Decimal("0.1"),
                "d_g": Decimal("0.01"),
                "unit": "g",
                "is_multi_interval": False,
                "indication_type": Instrument.INDICATION_DIGITAL,
                "load_receptor_type": Instrument.RECEPTOR_PLATFORM,
                "points_of_support": 4,
                "place_of_use": "Okhla Pharma R&D Lab",
            }
        )

        # Instrument 3: Class III multi-interval (Max 2/5/15 kg, e=1/2/10g)
        inst3, _ = Instrument.objects.get_or_create(
            serial_number="MET-Multi-7712",
            defaults={
                "instrument_id": "INST-DL-3840",
                "owner": owner2,
                "manufacturer": "Mettler Toledo",
                "model": "bRite Multi-Interval Retail Scale",
                "type_approval_number": "IND/09/2023/502",
                "accuracy_class": Instrument.CLASS_III,
                "max_capacity_g": Decimal("15000"),
                "min_capacity_g": Decimal("20"),
                "e_g": Decimal("1"),
                "d_g": Decimal("1"),
                "unit": "kg",
                "is_multi_interval": True,
                "indication_type": Instrument.INDICATION_DIGITAL,
                "load_receptor_type": Instrument.RECEPTOR_PLATFORM,
                "points_of_support": 4,
                "place_of_use": "Wholesale Market Counter",
            }
        )
        if not inst3.ranges.exists():
            InstrumentRange.objects.create(instrument=inst3, order=1, max_i_g=Decimal("2000"), e_i_g=Decimal("1"), d_i_g=Decimal("1"))
            InstrumentRange.objects.create(instrument=inst3, order=2, max_i_g=Decimal("5000"), e_i_g=Decimal("2"), d_i_g=Decimal("2"))
            InstrumentRange.objects.create(instrument=inst3, order=3, max_i_g=Decimal("15000"), e_i_g=Decimal("10"), d_i_g=Decimal("10"))

        self.stdout.write("✓ Seeded 3 Sample Instruments (Class III single, Class II, Class III multi-interval)")

        # 5. Create Sample Sessions and an Issued Report
        # Session 1: Issued report on inst1
        s1, s1_created = TestSession.objects.get_or_create(
            instrument=inst1,
            inspection_type=TestSession.INSPECTION_INITIAL,
            status=TestSession.STATUS_ISSUED,
            defaults={
                "inspector": insp_user,
                "overall_result": TestSession.RESULT_PASS,
                "test_date": today - timedelta(days=2),
                "remarks": "Instrument complies with OIML R 76-1:2006. Verification stamp affixed.",
                "visual_inspection": {"class_marking": True, "capacity_marking": True, "software_id": True, "inscriptions": True},
                "conformity_declaration": {"zero_device": True, "tare_device": True, "construction": True},
                "marking_securing": {"marks_applied": True, "mark_type": "stamp", "serial_reference": "STAMP-DL-2024-9902", "next_due_date": (today + timedelta(days=365)).isoformat()}
            }
        )
        if s1_created:
            SessionWeight.objects.create(session=s1, weight=test_weights["WT-M1-2KG"])
            SessionWeight.objects.create(session=s1, weight=test_weights["WT-M1-5KG"])
            SessionWeight.objects.create(session=s1, weight=test_weights["WT-M1-10KG"])

            ZeroCheck.objects.create(session=s1, indication_zero=Decimal("0"), delta_l=Decimal("0.5"), computed_e0=Decimal("0"), passed=True)

            ranges1 = [RangeSpec(order=1, max_g=inst1.max_capacity_g, e_g=inst1.e_g, d_g=inst1.d_g)]
            test_loads = [Decimal("20"), Decimal("500"), Decimal("2000"), Decimal("5000"), Decimal("10000")]
            for seq, ld in enumerate(test_loads, start=1):
                mpe_res = mpe_lookup(inst1.accuracy_class, ranges1, ld, 1)
                err_res = error_calc(I=ld, L=ld, e_i=inst1.e_g, d=inst1.d_g, E0=Decimal("0"), delta_L=Decimal("0.5"))
                AccuracyReading.objects.create(
                    session=s1, sequence=seq, phase="up", load_g=ld, indication=ld, delta_l=Decimal("0.5"),
                    m=mpe_res.m, range_order=1, e_used=inst1.e_g, P=err_res.P, E=err_res.E, Ec=err_res.Ec,
                    mpe=mpe_res.mpe, passed=True
                )
            for seq, ld in enumerate(reversed(test_loads), start=1):
                mpe_res = mpe_lookup(inst1.accuracy_class, ranges1, ld, 1)
                err_res = error_calc(I=ld, L=ld, e_i=inst1.e_g, d=inst1.d_g, E0=Decimal("0"), delta_L=Decimal("0.5"))
                AccuracyReading.objects.create(
                    session=s1, sequence=seq, phase="down", load_g=ld, indication=ld, delta_l=Decimal("0.5"),
                    m=mpe_res.m, range_order=1, e_used=inst1.e_g, P=err_res.P, E=err_res.E, Ec=err_res.Ec,
                    mpe=mpe_res.mpe, passed=True
                )

            # Repeatability
            rep = RepeatabilityTest.objects.create(session=s1, load_g=Decimal("8000"), required_count=3, computed_spread=Decimal("0.5"), spread_limit=Decimal("1.5"), passed=True)
            for i in range(1, 4):
                RepeatabilityReading.objects.create(test=rep, sequence=i, indication=Decimal("8000"), delta_l=Decimal("0.5"), computed_error=Decimal("0"), passed=True)

            # Eccentricity
            ecc = EccentricityTest.objects.create(session=s1, mode="up_to_4_supports", required_load_g=Decimal("3333"), actual_load_g=Decimal("3333"), positions_count=4, passed=True)
            for pos in ["Pos 1 (Front-Left)", "Pos 2 (Front-Right)", "Pos 3 (Rear-Right)", "Pos 4 (Rear-Left)"]:
                EccentricityReading.objects.create(test=ecc, position_label=pos, indication=Decimal("3333"), delta_l=Decimal("0.5"), computed_E=Decimal("0"), Ec=Decimal("0"), mpe=Decimal("1.5"), passed=True)

            # Issue Report
            rep_num = generate_next_report_number()
            report = Report.objects.create(
                session=s1,
                report_number=rep_num,
                revision=0,
                status=Report.STATUS_ISSUED,
                approved_by=off_user,
                snapshot_hash="init",
            )
            snap_hash = save_report_snapshot(report)
            report.snapshot_hash = snap_hash
            report.save(update_fields=["snapshot_hash"])
            try:
                generate_and_save_pdf(report)
                self.stdout.write(f"✓ Generated PDF for {report.report_number}")
            except Exception as e:
                self.stdout.write(f"PDF note: {e}")

            self.stdout.write(f"✓ Created Issued Report: {report.report_number}")

        # Session 2: Submitted session on inst2 (Awaiting Approval)
        s2, _ = TestSession.objects.get_or_create(
            instrument=inst2,
            inspection_type=TestSession.INSPECTION_SUBSEQUENT,
            status=TestSession.STATUS_SUBMITTED,
            defaults={
                "inspector": insp_user,
                "overall_result": TestSession.RESULT_PASS,
                "test_date": today,
                "remarks": "Subsequent verification completed. Accuracy verified at all test points.",
                "visual_inspection": {"class_marking": True, "capacity_marking": True},
                "conformity_declaration": {"zero_device": True},
            }
        )

        # Session 3: Returned session on inst3 (Needs Attention)
        s3, _ = TestSession.objects.get_or_create(
            instrument=inst3,
            inspection_type=TestSession.INSPECTION_INITIAL,
            status=TestSession.STATUS_RETURNED,
            defaults={
                "inspector": insp_user,
                "overall_result": TestSession.RESULT_INCOMPLETE,
                "test_date": today - timedelta(days=1),
                "officer_comment": "Please verify partial range changeover at 2,000 g and 5,000 g with extra load ΔL.",
                "remarks": "Testing in progress for multi-interval ranges.",
            }
        )

        self.stdout.write(self.style.SUCCESS("All demo data seeded successfully!"))
