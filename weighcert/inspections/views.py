import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.utils import timezone
from accounts.decorators import inspector_required, officer_required, staff_required
from core.audit import log_audit
from core.models import LabSettings
from core.numbering import generate_next_report_number
from registry.models import Instrument, TestWeight
from reports.models import Report
from reports.snapshot import save_report_snapshot
from reports.pdf import generate_and_save_pdf
from rules.engine import (
    mpe_lookup, error_calc, check_compliance, zero_check,
    repeatability_eval, eccentricity_required_load, suggested_loads,
    overall_result, required_repeatability_count, RangeSpec, weight_error_check,
    multiplier_for_inspection
)
from .models import (
    TestSession, SessionWeight, ZeroCheck, AccuracyReading, TareCheck,
    RepeatabilityTest, RepeatabilityReading, EccentricityTest, EccentricityReading,
    DiscriminationReading, SensitivityReading, TiltCheck
)


def _get_ranges_for_session(session: TestSession) -> list[RangeSpec]:
    inst = session.instrument
    return [
        RangeSpec(order=r.order, max_g=r.max_i_g, e_g=r.e_i_g, d_g=r.d_i_g)
        for r in inst.ranges.all()
    ] or [RangeSpec(order=1, max_g=inst.max_capacity_g, e_g=inst.e_g, d_g=inst.d_g)]


@inspector_required
def wizard_start_view(request):
    """Start New Test wizard (Step 1 entry or instrument picker)."""
    inst_id = request.GET.get("instrument")
    if inst_id:
        inst = get_object_or_404(Instrument, instrument_id=inst_id)
        # Create draft session
        session = TestSession.objects.create(
            instrument=inst,
            inspector=request.user,
            inspection_type=TestSession.INSPECTION_INITIAL,
            status=TestSession.STATUS_DRAFT,
        )
        log_audit(request.user, "create", "TestSession", str(session.id), after={"instrument": inst.instrument_id})
        return redirect("wizard_step", session_id=session.id, step="conditions")

    instruments = Instrument.objects.filter(status="active").select_related("owner")
    return render(request, "inspections/wizard_start.html", {"instruments": instruments})


@staff_required
def wizard_step_view(request, session_id, step):
    """Core 7-step guided test wizard."""
    session = get_object_or_404(
        TestSession.objects.select_related("instrument", "instrument__owner", "inspector"),
        id=session_id
    )

    # Permission: only inspector can edit drafts/returned; others view-only
    can_edit = (
        request.user.profile.is_inspector() and
        session.status in [TestSession.STATUS_DRAFT, TestSession.STATUS_RETURNED]
    )
    if not can_edit and request.method == "POST":
        messages.error(request, "You do not have permission to edit this test session.")
        return redirect("test_review", session_id=session.id)

    inst = session.instrument
    active_weights = TestWeight.objects.filter(is_active=True).order_by("nominal_mass_g")
    ranges = _get_ranges_for_session(session)

    # Dispatch to step logic
    if step == "conditions":
        if request.method == "POST" and can_edit:
            session.inspection_type = request.POST.get("inspection_type", session.inspection_type)
            session.limit_multiplier = multiplier_for_inspection(session.inspection_type)
            session.place_type = request.POST.get("place_type", session.place_type)
            session.location_text = request.POST.get("location_text", "")
            session.gravity_note = request.POST.get("gravity_note", "")
            session.ambient_notes = request.POST.get("ambient_notes", "")

            # Selected weights
            selected_weight_ids = request.POST.getlist("weights")
            SessionWeight.objects.filter(session=session).delete()
            for wid in selected_weight_ids:
                w = TestWeight.objects.filter(id=wid, is_active=True).first()
                if w and not w.is_expired:
                    SessionWeight.objects.create(session=session, weight=w)

            # Checklists
            session.visual_inspection = {
                "class_marking": request.POST.get("vi_class") == "yes",
                "capacity_marking": request.POST.get("vi_capacity") == "yes",
                "software_id": request.POST.get("vi_software") == "yes",
                "module_id": request.POST.get("vi_module") == "yes",
                "inscriptions": request.POST.get("vi_inscriptions") == "yes",
                "stamp_place": request.POST.get("vi_stamp") == "yes",
                "notes": request.POST.get("vi_notes", ""),
            }
            session.conformity_declaration = {
                "zero_device": request.POST.get("conf_zero") == "yes",
                "tare_device": request.POST.get("conf_tare") == "yes",
                "calc_device": request.POST.get("conf_calc") == "yes",
                "construction": request.POST.get("conf_construction") == "yes",
                "notes": request.POST.get("conf_notes", ""),
            }
            session.save()
            messages.success(request, "Conditions and checklists saved.")
            return redirect("wizard_step", session_id=session.id, step="zero")

        context = {
            "session": session,
            "instrument": inst,
            "active_weights": active_weights,
            "selected_weight_ids": set(session.session_weights.values_list("weight_id", flat=True)),
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_conditions.html", context)

    elif step == "zero":
        zero_chk, _ = ZeroCheck.objects.get_or_create(session=session)
        if request.method == "POST" and can_edit:
            ind_val = Decimal(request.POST.get("indication_zero", "0") or "0")
            dl_val_raw = request.POST.get("delta_l")
            dl_val = Decimal(dl_val_raw) if dl_val_raw else None

            # Compute E0 using rules engine
            lab = LabSettings.get_settings()
            err_res = error_calc(
                I=ind_val, L=Decimal("0"), e_i=inst.e_g, d=inst.d_g, E0=Decimal("0"),
                delta_L=dl_val, allow_simplified=lab.allow_simplified_error
            )
            e0_eval = zero_check(E0=err_res.E, e1=inst.e_g)

            zero_chk.indication_zero = ind_val
            zero_chk.delta_l = dl_val
            zero_chk.computed_e0 = err_res.E
            zero_chk.passed = e0_eval["passed"]
            zero_chk.save()

            messages.success(request, f"Zero check logged. E0 = {zero_chk.computed_e0} g (Pass = {zero_chk.passed})")
            return redirect("wizard_step", session_id=session.id, step="accuracy")

        context = {
            "session": session,
            "instrument": inst,
            "zero_chk": zero_chk,
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_zero.html", context)

    elif step == "accuracy":
        zero_chk = getattr(session, "zero_check", None)
        e0_basis = zero_chk.computed_e0 if zero_chk else Decimal("0")
        lab = LabSettings.get_settings()

        if request.method == "POST" and can_edit:
            action = request.POST.get("action")
            if action == "generate_loads":
                # Generate suggested loads per Section 7.5
                loads = suggested_loads(
                    cls=inst.accuracy_class,
                    ranges=ranges,
                    min_g=inst.min_capacity_g,
                    min_count=5,
                    include_min=(inst.min_capacity_g >= Decimal("0.1"))
                )
                AccuracyReading.objects.filter(session=session).delete()
                # Phase UP
                for seq, ld in enumerate(loads, start=1):
                    mpe_res = mpe_lookup(inst.accuracy_class, ranges, ld, session.limit_multiplier)
                    AccuracyReading.objects.create(
                        session=session, sequence=seq, phase="up", load_g=ld,
                        indication=ld, delta_l=(inst.e_g / Decimal("2")) if inst.d_g > Decimal("0.2") * inst.e_g else None,
                        m=mpe_res.m, range_order=mpe_res.range_order, e_used=mpe_res.e_used,
                        mpe=mpe_res.mpe
                    )
                # Phase DOWN
                for seq, ld in enumerate(reversed(loads), start=1):
                    mpe_res = mpe_lookup(inst.accuracy_class, ranges, ld, session.limit_multiplier)
                    AccuracyReading.objects.create(
                        session=session, sequence=seq, phase="down", load_g=ld,
                        indication=ld, delta_l=(inst.e_g / Decimal("2")) if inst.d_g > Decimal("0.2") * inst.e_g else None,
                        m=mpe_res.m, range_order=mpe_res.range_order, e_used=mpe_res.e_used,
                        mpe=mpe_res.mpe
                    )
                messages.success(request, f"Generated {len(loads) * 2} accuracy load test steps (Up & Down).")
                return redirect("wizard_step", session_id=session.id, step="accuracy")

            elif action == "save_readings":
                # Save and recompute every row via server-side rules engine
                all_readings = AccuracyReading.objects.filter(session=session)
                for r in all_readings:
                    load_val = Decimal(request.POST.get(f"load_{r.id}", str(r.load_g)))
                    ind_val = Decimal(request.POST.get(f"ind_{r.id}", str(r.indication)))
                    dl_val_raw = request.POST.get(f"dl_{r.id}")
                    dl_val = Decimal(dl_val_raw) if dl_val_raw else None
                    w_text = request.POST.get(f"w_{r.id}", "")

                    # Compute MPE
                    mpe_res = mpe_lookup(inst.accuracy_class, ranges, load_val, session.limit_multiplier)
                    # Compute Error
                    err_res = error_calc(
                        I=ind_val, L=load_val, e_i=mpe_res.e_used, d=inst.d_g,
                        E0=e0_basis, delta_L=dl_val, allow_simplified=lab.allow_simplified_error
                    )
                    comp_res = check_compliance(err_res, mpe_res)

                    r.load_g = load_val
                    r.indication = ind_val
                    r.delta_l = dl_val
                    r.weights_used_text = w_text
                    r.m = mpe_res.m
                    r.range_order = mpe_res.range_order
                    r.e_used = mpe_res.e_used
                    r.P = err_res.P
                    r.E = err_res.E
                    r.E0_used = e0_basis
                    r.Ec = err_res.Ec
                    r.mpe = mpe_res.mpe
                    r.passed = comp_res.passed
                    r.save()

                messages.success(request, "Accuracy readings recomputed and saved.")
                return redirect("wizard_step", session_id=session.id, step="repeatability")

        readings_up = session.accuracy_readings.filter(phase="up").order_by("sequence")
        readings_down = session.accuracy_readings.filter(phase="down").order_by("sequence")

        context = {
            "session": session,
            "instrument": inst,
            "readings_up": readings_up,
            "readings_down": readings_down,
            "e0_basis": e0_basis,
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_accuracy.html", context)

    elif step == "repeatability":
        rep_test, _ = RepeatabilityTest.objects.get_or_create(
            session=session,
            defaults={
                "load_g": Decimal("0.8") * inst.max_capacity_g,
                "required_count": required_repeatability_count(inst.accuracy_class),
            }
        )
        if request.method == "POST" and can_edit:
            load_val = Decimal(request.POST.get("load_g", str(rep_test.load_g)))
            rep_test.load_g = load_val
            rep_test.save()

            # MPE at this load
            mpe_res = mpe_lookup(inst.accuracy_class, ranges, load_val, session.limit_multiplier)
            lab = LabSettings.get_settings()
            zero_chk = getattr(session, "zero_check", None)
            e0_basis = zero_chk.computed_e0 if zero_chk else Decimal("0")

            errors_list = []
            rep_test.readings.all().delete()
            for seq in range(1, rep_test.required_count + 1):
                ind_val = Decimal(request.POST.get(f"ind_{seq}", str(load_val)) or "0")
                dl_val_raw = request.POST.get(f"dl_{seq}")
                dl_val = Decimal(dl_val_raw) if dl_val_raw else None

                err_res = error_calc(
                    I=ind_val, L=load_val, e_i=mpe_res.e_used, d=inst.d_g,
                    E0=e0_basis, delta_L=dl_val, allow_simplified=lab.allow_simplified_error
                )
                comp = check_compliance(err_res, mpe_res)
                errors_list.append(err_res.Ec)

                RepeatabilityReading.objects.create(
                    test=rep_test, sequence=seq, indication=ind_val,
                    delta_l=dl_val, computed_error=err_res.Ec, passed=comp.passed
                )

            rep_eval = repeatability_eval(errors_list, mpe_res.mpe)
            rep_test.computed_spread = rep_eval.spread
            rep_test.spread_limit = mpe_res.mpe
            rep_test.passed = rep_eval.passed
            rep_test.save()

            messages.success(request, f"Repeatability test saved. Spread = {rep_test.computed_spread} g (Pass = {rep_test.passed})")
            return redirect("wizard_step", session_id=session.id, step="eccentricity")

        context = {
            "session": session,
            "instrument": inst,
            "rep_test": rep_test,
            "readings": rep_test.readings.all(),
            "count_range": range(1, rep_test.required_count + 1),
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_repeatability.html", context)

    elif step == "eccentricity":
        req_load = eccentricity_required_load(
            mode=inst.load_receptor_type if inst.load_receptor_type in ["tank_hopper", "rolling_load"] else "up_to_4_supports",
            max_g=inst.max_capacity_g,
            tare_plus_g=inst.max_additive_tare_g,
            n_supports=inst.points_of_support,
        )
        ecc_test, _ = EccentricityTest.objects.get_or_create(
            session=session,
            defaults={
                "mode": "up_to_4_supports" if inst.points_of_support <= 4 else "more_than_4_supports",
                "required_load_g": req_load,
                "actual_load_g": req_load,
                "positions_count": 4,
            }
        )

        if request.method == "POST" and can_edit:
            if request.POST.get("is_omitted") == "on":
                ecc_test.is_omitted = True
                ecc_test.omission_reason = request.POST.get("omission_reason", "Operating conditions preclude eccentric loading.")
                ecc_test.passed = True
                ecc_test.save()
                messages.info(request, "Eccentricity test marked as omitted with reason.")
                return redirect("wizard_step", session_id=session.id, step="conditional")

            act_load = Decimal(request.POST.get("actual_load_g", str(ecc_test.actual_load_g)))
            ecc_test.actual_load_g = act_load
            ecc_test.is_omitted = False
            ecc_test.save()

            mpe_res = mpe_lookup(inst.accuracy_class, ranges, act_load, session.limit_multiplier)
            lab = LabSettings.get_settings()
            zero_chk = getattr(session, "zero_check", None)
            e0_basis = zero_chk.computed_e0 if zero_chk else Decimal("0")

            positions = ["Pos 1 (Front-Left)", "Pos 2 (Front-Right)", "Pos 3 (Rear-Right)", "Pos 4 (Rear-Left)"]
            ecc_test.readings.all().delete()
            all_passed = True
            for i, pos in enumerate(positions, start=1):
                ind_val = Decimal(request.POST.get(f"ind_{i}", str(act_load)) or "0")
                dl_val_raw = request.POST.get(f"dl_{i}")
                dl_val = Decimal(dl_val_raw) if dl_val_raw else None

                err_res = error_calc(
                    I=ind_val, L=act_load, e_i=mpe_res.e_used, d=inst.d_g,
                    E0=e0_basis, delta_L=dl_val, allow_simplified=lab.allow_simplified_error
                )
                comp = check_compliance(err_res, mpe_res)
                if not comp.passed:
                    all_passed = False

                EccentricityReading.objects.create(
                    test=ecc_test, position_label=pos, indication=ind_val,
                    delta_l=dl_val, computed_E=err_res.E, E0_used=e0_basis,
                    Ec=err_res.Ec, mpe=mpe_res.mpe, passed=comp.passed
                )

            ecc_test.passed = all_passed
            ecc_test.save()
            messages.success(request, f"Eccentricity test logged (Pass = {ecc_test.passed}).")
            return redirect("wizard_step", session_id=session.id, step="conditional")

        context = {
            "session": session,
            "instrument": inst,
            "ecc_test": ecc_test,
            "readings": ecc_test.readings.all(),
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_eccentricity.html", context)

    elif step == "conditional":
        # Step 6: Discrimination (analog only), Sensitivity, Tilt
        is_digital = inst.indication_type == Instrument.INDICATION_DIGITAL
        tilt, _ = TiltCheck.objects.get_or_create(session=session)

        if request.method == "POST" and can_edit:
            if inst.is_mobile:
                tilt.passed = request.POST.get("tilt_passed") == "on"
                tilt.note = request.POST.get("tilt_note", "")
                tilt.save()
            messages.success(request, "Conditional test details saved.")
            return redirect("wizard_step", session_id=session.id, step="remarks")

        context = {
            "session": session,
            "instrument": inst,
            "is_digital": is_digital,
            "tilt": tilt,
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_conditional.html", context)

    elif step == "remarks":
        # Step 7: Remarks and Marking
        if request.method == "POST" and can_edit:
            session.remarks = request.POST.get("remarks", "")
            session.marking_securing = {
                "marks_applied": request.POST.get("marks_applied") == "yes",
                "mark_type": request.POST.get("mark_type", "stamp"),
                "serial_reference": request.POST.get("serial_reference", ""),
                "next_due_date": request.POST.get("next_due_date", ""),
            }

            # Evaluate overall result using pure Python rules engine
            zero_ok = session.zero_check.passed if hasattr(session, "zero_check") else None
            acc_qs = session.accuracy_readings.all()
            acc_ok = (acc_qs.exists() and all(r.passed for r in acc_qs)) if acc_qs.exists() else None
            rep_ok = session.repeatability_test.passed if hasattr(session, "repeatability_test") else None
            ecc_ok = session.eccentricity_test.passed if hasattr(session, "eccentricity_test") else None

            session.overall_result = overall_result(
                zero_ok=zero_ok,
                accuracy_ok=acc_ok,
                repeatability_ok=rep_ok,
                eccentricity_ok=ecc_ok,
                tare_ok=None,
                discrimination_ok=None,
                sensitivity_ok=None,
                tilt_ok=session.tilt_check.passed if hasattr(session, "tilt_check") and inst.is_mobile else None,
                mandatory_complete=all(v is not None for v in [zero_ok, acc_ok, rep_ok, ecc_ok])
            )
            session.save()
            log_audit(request.user, "update", "TestSession", str(session.id), after={"overall_result": session.overall_result})
            messages.success(request, "Test completed and ready for review.")
            return redirect("test_review", session_id=session.id)

        context = {
            "session": session,
            "instrument": inst,
            "step": step,
            "can_edit": can_edit,
        }
        return render(request, "inspections/step_remarks.html", context)

    return redirect("test_review", session_id=session.id)


@staff_required
def test_review_view(request, session_id):
    """Page 6: Test Review & Approval"""
    session = get_object_or_404(
        TestSession.objects.select_related("instrument", "instrument__owner", "inspector"),
        id=session_id
    )
    inst = session.instrument

    # Check completeness
    zero_chk = getattr(session, "zero_check", None)
    rep_test = getattr(session, "repeatability_test", None)
    ecc_test = getattr(session, "eccentricity_test", None)
    acc_readings = session.accuracy_readings.all()

    context = {
        "session": session,
        "instrument": inst,
        "owner": inst.owner,
        "zero_chk": zero_chk,
        "rep_test": rep_test,
        "ecc_test": ecc_test,
        "acc_readings": acc_readings,
        "weights": session.session_weights.select_related("weight").all(),
    }
    return render(request, "inspections/test_review.html", context)


@inspector_required
def test_submit_view(request, session_id):
    """Inspector submits test session to Officer for approval."""
    session = get_object_or_404(TestSession, id=session_id)
    if session.status not in [TestSession.STATUS_DRAFT, TestSession.STATUS_RETURNED]:
        messages.error(request, "Only draft or returned tests can be submitted.")
        return redirect("test_review", session_id=session.id)

    session.status = TestSession.STATUS_SUBMITTED
    session.save()
    log_audit(request.user, "submit", "TestSession", str(session.id), after={"status": session.status})
    messages.success(request, "Test submitted to Officer for review and certificate approval.")
    return redirect("test_review", session_id=session.id)


@officer_required
def test_return_view(request, session_id):
    """Officer returns test session to Inspector with mandatory comment."""
    session = get_object_or_404(TestSession, id=session_id)
    if session.status != TestSession.STATUS_SUBMITTED:
        messages.error(request, "Only submitted tests can be returned.")
        return redirect("test_review", session_id=session.id)

    comment = request.POST.get("comment", "").strip()
    if not comment:
        messages.error(request, "A return comment explaining the reason is mandatory.")
        return redirect("test_review", session_id=session.id)

    session.status = TestSession.STATUS_RETURNED
    session.officer_comment = comment
    session.save()
    log_audit(request.user, "return", "TestSession", str(session.id), after={"officer_comment": comment})
    messages.warning(request, f"Test returned to Inspector: \"{comment}\"")
    return redirect("test_review", session_id=session.id)


@officer_required
def test_approve_view(request, session_id):
    """
    Officer approves test session.
    Atomic: Report number + Report row + Snapshot hash + MongoDB doc + PDF + QR code.
    Spec Section 8
    """
    session = get_object_or_404(TestSession, id=session_id)
    if session.status != TestSession.STATUS_SUBMITTED:
        messages.error(request, "Only submitted tests can be approved.")
        return redirect("test_review", session_id=session.id)

    with transaction.atomic():
        report_number = generate_next_report_number()
        report = Report.objects.create(
            session=session,
            report_number=report_number,
            revision=0,
            status=Report.STATUS_ISSUED,
            approved_by=request.user,
            snapshot_hash="temp",
        )
        session.status = TestSession.STATUS_ISSUED
        session.save()

        # Compute snapshot hash and store in MongoDB
        snap_hash = save_report_snapshot(report)
        report.snapshot_hash = snap_hash
        report.save(update_fields=["snapshot_hash"])

        # Generate and save immutable PDF
        generate_and_save_pdf(report, request)

        log_audit(
            request.user, "approve", "TestSession", str(session.id),
            after={"report_number": report_number, "hash": snap_hash}
        )

    messages.success(request, f"Report {report.report_number} officially approved and issued!")
    return redirect("report_preview", report_id=report.id)


@inspector_required
def test_revise_view(request, report_id):
    """
    Inspector creates revision n+1 from an issued report.
    Spec Section 8
    """
    old_report = get_object_or_404(Report, id=report_id)
    old_session = old_report.session

    with transaction.atomic():
        # Clone session
        new_session = TestSession.objects.create(
            instrument=old_session.instrument,
            inspection_type=old_session.inspection_type,
            limit_multiplier=old_session.limit_multiplier,
            test_date=timezone.now().date(),
            place_type=old_session.place_type,
            location_text=old_session.location_text,
            gravity_note=old_session.gravity_note,
            ambient_notes=old_session.ambient_notes,
            inspector=request.user,
            status=TestSession.STATUS_DRAFT,
            overall_result=TestSession.RESULT_INCOMPLETE,
            rule_set_version=old_session.rule_set_version,
            visual_inspection=old_session.visual_inspection,
            conformity_declaration=old_session.conformity_declaration,
            remarks=f"Revision of {old_report.report_number} (Rev {old_report.revision + 1})",
        )
        # Copy weights
        for sw in old_session.session_weights.all():
            SessionWeight.objects.create(session=new_session, weight=sw.weight, used_in_steps=sw.used_in_steps)

        log_audit(
            request.user, "revise", "Report", str(old_report.id),
            after={"new_session_id": new_session.id, "target_revision": old_report.revision + 1}
        )

    messages.success(request, f"New revision draft created (will become Rev {old_report.revision + 1} upon approval).")
    return redirect("wizard_step", session_id=new_session.id, step="conditions")


@staff_required
def api_rules_preview(request):
    """
    HTMX live calculation preview endpoint.
    Recalculates a single row or readings without updating DB.
    """
    try:
        data = json.loads(request.body) if request.body else request.POST
        cls_val = data.get("accuracy_class", "III")
        multiplier = int(data.get("multiplier", "1"))
        load_g = Decimal(str(data.get("load_g", "0") or "0"))
        ind_g = Decimal(str(data.get("indication", "0") or "0"))
        dl_raw = data.get("delta_l")
        dl_g = Decimal(str(dl_raw)) if dl_raw not in (None, "") else None
        e_g = Decimal(str(data.get("e_g", "1") or "1"))
        d_g = Decimal(str(data.get("d_g", "1") or "1"))
        e0_g = Decimal(str(data.get("e0", "0") or "0"))
        allow_simp = data.get("allow_simplified") in [True, "true", "on", 1]

        ranges = [RangeSpec(order=1, max_g=Decimal("10000000"), e_g=e_g, d_g=d_g)]
        mpe_res = mpe_lookup(cls_val, ranges, load_g, multiplier)
        err_res = error_calc(
            I=ind_g, L=load_g, e_i=e_g, d=d_g, E0=e0_g, delta_L=dl_g, allow_simplified=allow_simp
        )
        comp = check_compliance(err_res, mpe_res)

        return JsonResponse({
            "P": str(err_res.P) if err_res.P is not None else None,
            "E": str(err_res.E),
            "Ec": str(err_res.Ec),
            "mpe": str(mpe_res.mpe),
            "passed": comp.passed,
            "missing_delta_l": err_res.missing_delta_L,
        })
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

