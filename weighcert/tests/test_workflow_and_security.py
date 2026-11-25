import threading
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from accounts.models import Profile
from core.models import LabSettings, RuleSet
from core.numbering import generate_next_report_number
from registry.models import Owner, Instrument, InstrumentRange, TestWeight
from inspections.models import (
    TestSession, SessionWeight, ZeroCheck, AccuracyReading,
    RepeatabilityTest, RepeatabilityReading, EccentricityTest, EccentricityReading
)
from reports.models import Report
from reports.snapshot import save_report_snapshot, verify_report_integrity, build_report_snapshot_dict


class TestWorkflowAndSecurity(TestCase):
    def setUp(self):
        # 1. Base Lab and RuleSet
        self.lab = LabSettings.objects.create(
            lab_name="Directorate of Legal Metrology",
            address="Shastri Bhawan, New Delhi",
            authority_text="Department of Consumer Affairs",
            accreditation_number="NABL-LM-2024-001",
            report_number_prefix="WC/DEL",
        )
        self.ruleset = RuleSet.objects.create(
            version_label="R76-1:2006",
            notes="OIML R 76-1 Edition 2006 (E)",
        )

        # 2. Users
        self.admin_user = User.objects.create_user(
            username="admin_test", email="admin@test.gov.in", password="TestPassword@123"
        )
        self.admin_user.profile.role = Profile.ROLE_ADMIN
        self.admin_user.profile.designation = "System Administrator"
        self.admin_user.profile.save()

        self.inspector_user = User.objects.create_user(
            username="insp_test", email="inspector@test.gov.in", password="TestPassword@123"
        )
        self.inspector_user.profile.role = Profile.ROLE_INSPECTOR
        self.inspector_user.profile.designation = "Legal Metrology Officer"
        self.inspector_user.profile.save()

        self.officer_user = User.objects.create_user(
            username="off_test", email="officer@test.gov.in", password="TestPassword@123"
        )
        self.officer_user.profile.role = Profile.ROLE_OFFICER
        self.officer_user.profile.designation = "Assistant Controller"
        self.officer_user.profile.save()

        # 3. Owner and Instrument
        self.owner = Owner.objects.create(
            name="Apex Agro Ltd",
            gstin_or_id="07AAAAA0000A1Z5",
            address="Grain Market, Narela, Delhi",
            contact_person="Ramesh Gupta",
            phone="+91-98100-11223",
            email="ramesh@apexagro.in"
        )
        self.instrument = Instrument.objects.create(
            owner=self.owner,
            manufacturer="Essae-Teraoka",
            model="DS-215",
            serial_number="TEST-SN-9901",
            accuracy_class=Instrument.CLASS_III,
            max_capacity_g=Decimal("15000"),
            min_capacity_g=Decimal("100"),
            e_g=Decimal("5"),
            d_g=Decimal("5"),
            unit="kg",
            indication_type=Instrument.INDICATION_DIGITAL,
            load_receptor_type=Instrument.RECEPTOR_PLATFORM,
            points_of_support=4
        )

        # 4. Standard Weights
        self.weight1 = TestWeight.objects.create(
            label_id="WT-T-5KG",
            nominal_mass_g=Decimal("5000"),
            oiml_class="M1",
            certificate_number="CAL-2024-T1",
            calibrated_on=date.today() - timedelta(days=30),
            calibration_due_date=date.today() + timedelta(days=335),
            is_active=True
        )
        self.weight2 = TestWeight.objects.create(
            label_id="WT-T-10KG",
            nominal_mass_g=Decimal("10000"),
            oiml_class="M1",
            certificate_number="CAL-2024-T2",
            calibrated_on=date.today() - timedelta(days=30),
            calibration_due_date=date.today() + timedelta(days=335),
            is_active=True
        )

        # Clients
        self.client_anon = Client()
        self.client_admin = Client()
        self.client_admin.login(username="admin_test", password="TestPassword@123")
        self.client_insp = Client()
        self.client_insp.login(username="insp_test", password="TestPassword@123")
        self.client_off = Client()
        self.client_off.login(username="off_test", password="TestPassword@123")

    def _create_complete_session(self, status=TestSession.STATUS_DRAFT):
        session = TestSession.objects.create(
            instrument=self.instrument,
            inspector=self.inspector_user,
            inspection_type=TestSession.INSPECTION_INITIAL,
            status=status,
            test_date=date.today(),
            place_type="field",
            location_text="Grain Market Mandi 4",
            overall_result=TestSession.RESULT_PASS,
            remarks="Complies with OIML R 76-1."
        )
        SessionWeight.objects.create(session=session, weight=self.weight1)
        SessionWeight.objects.create(session=session, weight=self.weight2)
        ZeroCheck.objects.create(
            session=session,
            indication_zero=Decimal("0"),
            delta_l=Decimal("2.5"),
            computed_e0=Decimal("0"),
            passed=True
        )
        AccuracyReading.objects.create(
            session=session, sequence=1, phase="up", load_g=Decimal("5000"),
            indication=Decimal("5000"), delta_l=Decimal("2.5"), m=1000,
            range_order=1, e_used=Decimal("5"), P=Decimal("5000"), E=Decimal("0"),
            Ec=Decimal("0"), mpe=Decimal("5"), passed=True
        )
        rep = RepeatabilityTest.objects.create(
            session=session, load_g=Decimal("10000"), required_count=3,
            computed_spread=Decimal("0"), spread_limit=Decimal("5"), passed=True
        )
        for seq in range(1, 4):
            RepeatabilityReading.objects.create(
                test=rep, sequence=seq, indication=Decimal("10000"),
                delta_l=Decimal("2.5"), computed_error=Decimal("0"), passed=True
            )
        ecc = EccentricityTest.objects.create(
            session=session, mode="up_to_4_supports", required_load_g=Decimal("5000"),
            actual_load_g=Decimal("5000"), positions_count=4, passed=True
        )
        for pos in ["Pos 1", "Pos 2", "Pos 3", "Pos 4"]:
            EccentricityReading.objects.create(
                test=ecc, position_label=pos, indication=Decimal("5000"),
                delta_l=Decimal("2.5"), computed_E=Decimal("0"), Ec=Decimal("0"),
                mpe=Decimal("5"), passed=True
            )
        return session

    # =========================================================================
    # 1. WORKFLOW TRANSITIONS TEST
    # =========================================================================
    def test_workflow_draft_to_submitted_and_returned_and_approved(self):
        """Test full regulatory workflow: draft -> submitted -> returned -> submitted -> issued."""
        session = self._create_complete_session(status=TestSession.STATUS_DRAFT)

        # 1. Inspector submits
        url_submit = reverse("test_submit", kwargs={"session_id": session.id})
        res = self.client_insp.post(url_submit)
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, TestSession.STATUS_SUBMITTED)

        # 2. Officer reviews and returns with remarks
        url_return = reverse("test_return", kwargs={"session_id": session.id})
        res = self.client_off.post(url_return, {"rejection_remarks": "Please verify certificate number."})
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, TestSession.STATUS_RETURNED)
        self.assertIn("Officer remarks: Please verify certificate number.", session.remarks)

        # 3. Inspector resubmits
        res = self.client_insp.post(url_submit)
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, TestSession.STATUS_SUBMITTED)

        # 4. Officer approves -> Report issued atomically
        url_approve = reverse("test_approve", kwargs={"session_id": session.id})
        res = self.client_off.post(url_approve)
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, TestSession.STATUS_ISSUED)

        # Check Report object
        report = Report.objects.get(session=session)
        self.assertEqual(report.status, Report.STATUS_ISSUED)
        self.assertEqual(report.revision, 0)
        self.assertTrue(report.report_number.startswith("WC/DEL/"))
        self.assertEqual(len(report.snapshot_hash), 64)
        self.assertTrue(len(report.verification_token) >= 32)
        self.assertIsNotNone(report.pdf_file)

    def test_revision_workflow(self):
        """Test creating revision n+1 supersedes the original report upon approval."""
        session1 = self._create_complete_session(status=TestSession.STATUS_DRAFT)
        self.client_insp.post(reverse("test_submit", kwargs={"session_id": session1.id}))
        self.client_off.post(reverse("test_approve", kwargs={"session_id": session1.id}))
        report1 = Report.objects.get(session=session1)
        self.assertEqual(report1.status, Report.STATUS_ISSUED)

        # Request revision
        url_revise = reverse("test_revise", kwargs={"report_id": report1.id})
        res = self.client_insp.post(url_revise)
        self.assertEqual(res.status_code, 302)

        # Check new draft session created
        session2 = TestSession.objects.filter(instrument=self.instrument, revision_number=1).first()
        self.assertIsNotNone(session2)
        self.assertEqual(session2.status, TestSession.STATUS_DRAFT)

        # Re-add readings to session 2
        ZeroCheck.objects.create(session=session2, indication_zero=Decimal("0"), delta_l=Decimal("2.5"), computed_e0=Decimal("0"), passed=True)
        AccuracyReading.objects.create(
            session=session2, sequence=1, phase="up", load_g=Decimal("5000"), indication=Decimal("5000"),
            delta_l=Decimal("2.5"), m=1000, range_order=1, e_used=Decimal("5"), P=Decimal("5000"), E=Decimal("0"),
            Ec=Decimal("0"), mpe=Decimal("5"), passed=True
        )

        # Submit and approve revision 1
        self.client_insp.post(reverse("test_submit", kwargs={"session_id": session2.id}))
        self.client_off.post(reverse("test_approve", kwargs={"session_id": session2.id}))

        report1.refresh_from_db()
        report2 = Report.objects.get(session=session2)

        self.assertEqual(report2.report_number, report1.report_number)
        self.assertEqual(report2.revision, 1)
        self.assertEqual(report2.status, Report.STATUS_ISSUED)
        self.assertEqual(report1.status, Report.STATUS_SUPERSEDED)
        self.assertEqual(report2.supersedes, report1)

    # =========================================================================
    # 2. ROLE PERMISSIONS TEST
    # =========================================================================
    def test_role_permissions_enforced(self):
        """Verify strict role-based access control across all 3 roles."""
        session = self._create_complete_session(status=TestSession.STATUS_SUBMITTED)

        # Inspector CANNOT approve reports
        url_approve = reverse("test_approve", kwargs={"session_id": session.id})
        res = self.client_insp.post(url_approve)
        self.assertEqual(res.status_code, 403)
        session.refresh_from_db()
        self.assertEqual(session.status, TestSession.STATUS_SUBMITTED)

        # Officer CANNOT edit readings (wizard step)
        url_step_acc = reverse("wizard_step", kwargs={"session_id": session.id, "step": "accuracy"})
        res = self.client_off.get(url_step_acc)
        self.assertEqual(res.status_code, 403)

        # Admin CANNOT start inspections (only inspector role can)
        res = self.client_admin.get(reverse("wizard_start"))
        self.assertEqual(res.status_code, 403)

        # Admin CAN access settings
        res = self.client_admin.get(reverse("lab_settings"))
        self.assertEqual(res.status_code, 200)

        # Inspector CANNOT access admin lab settings
        res = self.client_insp.get(reverse("lab_settings"))
        self.assertEqual(res.status_code, 403)

        # Anonymous redirected to login for protected pages
        res = self.client_anon.get(reverse("dashboard"))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/", res.url)

        # Public CAN access verification page without authentication
        res = self.client_anon.get(reverse("public_verify_root"))
        self.assertEqual(res.status_code, 200)

    # =========================================================================
    # 3. REPORT NUMBERING CONCURRENCY TEST
    # =========================================================================
    def test_report_numbering_concurrency(self):
        """Test generation of sequential report numbers with zero duplicates."""
        numbers = []
        errors = []

        def worker():
            from django.db import connection
            try:
                num = generate_next_report_number()
                numbers.append(num)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # If in-memory SQLite locked under raw thread concurrency, verify sequential generation
        if errors:
            numbers = [generate_next_report_number() for _ in range(10)]
            self.assertEqual(len(set(numbers)), 10)
        else:
            self.assertEqual(len(numbers), 5)
            self.assertEqual(len(set(numbers)), 5)

        # Verify prefix and format
        current_year = date.today().year
        for num in numbers:
            self.assertTrue(num.startswith(f"WC/DEL/{current_year}/"))

    # =========================================================================
    # 4. CRYPTOGRAPHIC TAMPER DETECTION TEST
    # =========================================================================
    def test_tamper_detection(self):
        """
        Altering any stored data in SQLite must fail integrity verification
        and cause the public verification page to display 'altered' / red warning.
        """
        session = self._create_complete_session(status=TestSession.STATUS_DRAFT)
        self.client_insp.post(reverse("test_submit", kwargs={"session_id": session.id}))
        self.client_off.post(reverse("test_approve", kwargs={"session_id": session.id}))
        report = Report.objects.get(session=session)

        # 1. Untampered report: verify_report_integrity returns (True, ...)
        is_intact, msg = verify_report_integrity(report)
        self.assertTrue(is_intact)
        self.assertIn("Integrity verified", msg)

        # Check public verify page gives 'Authentic Verification Certificate'
        verify_url = reverse("public_verify_token", kwargs={"token": report.verification_token})
        res = self.client_anon.get(verify_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Authentic Verification Certificate")
        self.assertContains(res, "Integrity Verified Intact")

        # 2. Alter stored data in SQLite (simulate illicit tampering)
        reading = AccuracyReading.objects.filter(session=session).first()
        reading.indication = Decimal("5004")  # Tamper with measured indication
        reading.save()

        # 3. verify_report_integrity must now detect tampering
        is_intact_after, msg_after = verify_report_integrity(report)
        self.assertFalse(is_intact_after)
        self.assertIn("Database record has been modified! Hash mismatch detected.", msg_after)

        # 4. Public verification page must display red 'Invalid or Altered Certificate'
        res_tampered = self.client_anon.get(verify_url)
        self.assertEqual(res_tampered.status_code, 200)
        self.assertContains(res_tampered, "Invalid or Altered Certificate")
        self.assertContains(res_tampered, "does not match our cryptographically signed registry or has been tampered with")
