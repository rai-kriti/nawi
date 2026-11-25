from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta
from django.contrib.auth.models import User
from accounts.decorators import role_required, admin_required, staff_required
from accounts.forms import UserCreateForm
from inspections.models import TestSession
from registry.models import TestWeight, Instrument
from reports.models import Report
from .models import LabSettings, RuleSet, ClassLimit, MpeBand, MultiIntervalCondition
from .audit import log_audit, verify_audit_chain, get_mongo_db


@staff_required
def dashboard_view(request):
    """Page 2: Dashboard"""
    today = timezone.now().date()
    month_start = today.replace(day=1)

    # 5 Bento stats
    drafts_count = TestSession.objects.filter(status=TestSession.STATUS_DRAFT).count()
    awaiting_approval_count = TestSession.objects.filter(status=TestSession.STATUS_SUBMITTED).count()
    passed_month_count = TestSession.objects.filter(
        status=TestSession.STATUS_ISSUED,
        overall_result=TestSession.RESULT_PASS,
        updated_at__gte=month_start
    ).count()
    failed_month_count = TestSession.objects.filter(
        overall_result=TestSession.RESULT_FAIL,
        updated_at__gte=month_start
    ).count()
    weights_due_30_count = TestWeight.objects.filter(
        is_active=True,
        calibration_due_date__lte=today + timedelta(days=30)
    ).count()

    # Needs your attention table
    profile = request.user.profile
    if profile.is_officer():
        attention_sessions = TestSession.objects.filter(
            status=TestSession.STATUS_SUBMITTED
        ).select_related("instrument", "instrument__owner", "inspector").order_by("updated_at")
    else:
        # Inspector or Admin sees returned tests & drafts
        attention_sessions = TestSession.objects.filter(
            status__in=[TestSession.STATUS_RETURNED, TestSession.STATUS_DRAFT]
        ).select_related("instrument", "instrument__owner", "inspector").order_by("-updated_at")

    # Recent reports
    recent_reports = Report.objects.select_related(
        "session", "session__instrument", "session__instrument__owner"
    ).order_by("-issued_at")[:10]

    context = {
        "drafts_count": drafts_count,
        "awaiting_approval_count": awaiting_approval_count,
        "passed_month_count": passed_month_count,
        "failed_month_count": failed_month_count,
        "weights_due_30_count": weights_due_30_count,
        "attention_sessions": attention_sessions[:5],
        "recent_reports": recent_reports,
    }
    return render(request, "dashboard.html", context)


@admin_required
def settings_view(request):
    """Page 11: Settings (Admin only)"""
    lab = LabSettings.get_settings()
    active_tab = request.GET.get("tab", "lab")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_lab":
            lab.lab_name = request.POST.get("lab_name", lab.lab_name)
            lab.address = request.POST.get("address", lab.address)
            lab.authority_text = request.POST.get("authority_text", lab.authority_text)
            lab.accreditation_number = request.POST.get("accreditation_number", lab.accreditation_number)
            lab.report_number_prefix = request.POST.get("report_number_prefix", lab.report_number_prefix)
            lab.report_footer_text = request.POST.get("report_footer_text", lab.report_footer_text)
            lab.allow_simplified_error = request.POST.get("allow_simplified_error") == "on"
            lab.year_reset_policy = request.POST.get("year_reset_policy", lab.year_reset_policy)
            if "logo" in request.FILES:
                lab.logo = request.FILES["logo"]
            lab.save()
            log_audit(request.user, "update", "LabSettings", "1", after={"lab_name": lab.lab_name})
            messages.success(request, "Lab settings updated successfully.")
            return redirect("/settings/?tab=lab")

        elif action == "create_user":
            form = UserCreateForm(request.POST)
            if form.is_valid():
                new_user = form.save()
                log_audit(request.user, "create", "User", str(new_user.id), after={"username": new_user.username, "role": new_user.profile.role})
                messages.success(request, f"User account created for {new_user.get_full_name()} ({new_user.username}).")
                return redirect("/settings/?tab=users")
            else:
                messages.error(request, f"Error creating user: {form.errors}")

    users = User.objects.select_related("profile").order_by("username")
    user_form = UserCreateForm()
    rule_set = RuleSet.objects.first()
    class_limits = ClassLimit.objects.filter(rule_set=rule_set) if rule_set else []
    mpe_bands = MpeBand.objects.filter(rule_set=rule_set) if rule_set else []
    multi_conds = MultiIntervalCondition.objects.filter(rule_set=rule_set) if rule_set else []

    # Fetch recent audit logs from MongoDB
    db = get_mongo_db()
    audit_logs = []
    if db is not None:
        try:
            audit_logs = list(db["audit_log"].find().sort("_id", -1).limit(50))
        except Exception:
            audit_logs = []

    context = {
        "lab": lab,
        "active_tab": active_tab,
        "users": users,
        "user_form": user_form,
        "rule_set": rule_set,
        "class_limits": class_limits,
        "mpe_bands": mpe_bands,
        "multi_conds": multi_conds,
        "audit_logs": audit_logs,
    }
    return render(request, "settings/settings.html", context)


@admin_required
def toggle_user_active(request, user_id):
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("/settings/?tab=users")

    profile = target.profile
    profile.is_active = not profile.is_active
    profile.save()
    status_str = "activated" if profile.is_active else "deactivated"
    log_audit(request.user, "update", "User", str(target.id), after={"is_active": profile.is_active})
    messages.success(request, f"User {target.username} has been {status_str}.")
    return redirect("/settings/?tab=users")


@admin_required
@require_POST
def reset_user_password(request, user_id):
    target = get_object_or_404(User, id=user_id)
    temp_pwd = request.POST.get("temporary_password", "")
    if not temp_pwd:
        messages.error(request, "Enter a temporary password to reset this account.")
        return redirect("/settings/?tab=users")
    target.set_password(temp_pwd)
    target.save()
    target.profile.must_change_password = True
    target.profile.save()
    log_audit(request.user, "reset_password", "User", str(target.id))
    messages.success(request, f"Password reset for {target.username}.")
    return redirect("/settings/?tab=users")


@admin_required
def verify_audit_chain_view(request):
    is_valid, count, msg = verify_audit_chain()
    return JsonResponse({"valid": is_valid, "count": count, "message": msg})
