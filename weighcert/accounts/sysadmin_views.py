"""
System Administrator views.
Only a user with role='sysadmin' can access these views.
There can only be ONE sysadmin in the system (enforced at creation).
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .decorators import sysadmin_required
from .models import Profile
from core.audit import log_audit
from accounts.middleware import get_client_ip


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────

@sysadmin_required
def sysadmin_dashboard(request):
    """
    Show all users (excluding the sysadmin themselves) with counts.
    """
    users = (
        User.objects.exclude(id=request.user.id)
        .select_related("profile")
        .order_by("profile__role", "last_name", "first_name")
    )
    total      = users.count()
    inspectors = users.filter(profile__role="inspector").count()
    officers   = users.filter(profile__role="officer").count()
    admins     = users.filter(profile__role="admin").count()
    active     = users.filter(profile__is_active=True).count()
    inactive   = users.filter(profile__is_active=False).count()

    stats = [
        ("Total Users",  total,      "text-primary",  "group"),
        ("Inspectors",   inspectors, "text-blue-600", "search"),
        ("Officers",     officers,   "text-purple-600","gavel"),
        ("Admins",       admins,     "text-amber-600","manage_accounts"),
        ("Active",       active,     "text-secondary","verified_user"),
        ("Inactive",     inactive,   "text-error",    "block"),
    ]
    return render(request, "sysadmin/dashboard.html", {
        "users":      users,
        "total":      total,
        "inspectors": inspectors,
        "officers":   officers,
        "admins":     admins,
        "active":     active,
        "inactive":   inactive,
        "stats":      stats,
    })


# ──────────────────────────────────────────────────────────────────────────────
# Create user
# ──────────────────────────────────────────────────────────────────────────────

@sysadmin_required
def sysadmin_create_user(request):
    """Create a new user (inspector / officer / admin)."""
    ALLOWED_ROLES = [
        ("inspector", "Inspector"),
        ("officer",   "Officer"),
        ("admin",     "Admin"),
    ]

    if request.method == "POST":
        username    = request.POST.get("username", "").strip()
        first_name  = request.POST.get("first_name", "").strip()
        last_name   = request.POST.get("last_name", "").strip()
        email       = request.POST.get("email", "").strip()
        role        = request.POST.get("role", "inspector")
        designation = request.POST.get("designation", "").strip()
        employee_id = request.POST.get("employee_id", "").strip()
        password    = request.POST.get("password", "")
        confirm_pw  = request.POST.get("confirm_password", "")
        must_change = request.POST.get("must_change_password") == "on"

        # Validate
        errors = []
        if not username:
            errors.append("Username is required.")
        elif User.objects.filter(username=username).exists():
            errors.append(f"Username '{username}' is already taken.")
        if password != confirm_pw:
            errors.append("Passwords do not match.")
        if role not in [r[0] for r in ALLOWED_ROLES]:
            errors.append("Invalid role selected.")
        try:
            validate_password(password)
        except ValidationError as e:
            errors.extend(e.messages)

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "sysadmin/user_form.html", {
                "mode": "create",
                "roles": ALLOWED_ROLES,
                "form_data": request.POST,
            })

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
            )
            profile = user.profile
            profile.role               = role
            profile.designation        = designation
            profile.employee_id        = employee_id
            profile.must_change_password = must_change
            profile.is_active          = True
            profile.save()

        log_audit(
            request.user, "create_user", "User", str(user.id),
            after={"username": username, "role": role},
            ip_address=get_client_ip(request),
        )
        messages.success(request, f"User '{username}' created successfully as {role.title()}.")
        return redirect("sysadmin_dashboard")

    return render(request, "sysadmin/user_form.html", {
        "mode":  "create",
        "roles": ALLOWED_ROLES,
        "form_data": {},
    })


# ──────────────────────────────────────────────────────────────────────────────
# Edit user
# ──────────────────────────────────────────────────────────────────────────────

@sysadmin_required
def sysadmin_edit_user(request, user_id):
    """Edit an existing user's details and optionally reset their password."""
    target_user = get_object_or_404(User, id=user_id)

    # Cannot edit the sysadmin account via this view (self-edit is blocked)
    if target_user.id == request.user.id:
        messages.error(request, "You cannot edit your own sysadmin account from here.")
        return redirect("sysadmin_dashboard")
    if hasattr(target_user, "profile") and target_user.profile.role == "sysadmin":
        messages.error(request, "Cannot edit another System Administrator account.")
        return redirect("sysadmin_dashboard")

    ALLOWED_ROLES = [
        ("inspector", "Inspector"),
        ("officer",   "Officer"),
        ("admin",     "Admin"),
    ]

    if request.method == "POST":
        first_name  = request.POST.get("first_name", "").strip()
        last_name   = request.POST.get("last_name", "").strip()
        email       = request.POST.get("email", "").strip()
        role        = request.POST.get("role", target_user.profile.role)
        designation = request.POST.get("designation", "").strip()
        employee_id = request.POST.get("employee_id", "").strip()
        is_active   = request.POST.get("is_active") == "on"
        must_change = request.POST.get("must_change_password") == "on"
        new_password = request.POST.get("new_password", "").strip()
        confirm_pw   = request.POST.get("confirm_password", "").strip()

        errors = []
        if role not in [r[0] for r in ALLOWED_ROLES]:
            errors.append("Invalid role selected.")
        if new_password:
            if new_password != confirm_pw:
                errors.append("New passwords do not match.")
            else:
                try:
                    validate_password(new_password, user=target_user)
                except ValidationError as e:
                    errors.extend(e.messages)

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "sysadmin/user_form.html", {
                "mode":        "edit",
                "target_user": target_user,
                "roles":       ALLOWED_ROLES,
                "form_data":   request.POST,
            })

        with transaction.atomic():
            target_user.first_name = first_name
            target_user.last_name  = last_name
            target_user.email      = email
            if new_password:
                target_user.set_password(new_password)
            target_user.save()

            profile = target_user.profile
            profile.role                = role
            profile.designation         = designation
            profile.employee_id         = employee_id
            profile.is_active           = is_active
            profile.must_change_password = must_change
            profile.save()

        log_audit(
            request.user, "edit_user", "User", str(target_user.id),
            after={"username": target_user.username, "role": role, "is_active": is_active},
            ip_address=get_client_ip(request),
        )
        messages.success(request, f"User '{target_user.username}' updated successfully.")
        return redirect("sysadmin_dashboard")

    return render(request, "sysadmin/user_form.html", {
        "mode":        "edit",
        "target_user": target_user,
        "roles":       ALLOWED_ROLES,
        "form_data":   {},
    })


# ──────────────────────────────────────────────────────────────────────────────
# Toggle active / deactivate
# ──────────────────────────────────────────────────────────────────────────────

@sysadmin_required
def sysadmin_toggle_user(request, user_id):
    """Activate or deactivate a user account (POST only)."""
    if request.method != "POST":
        return redirect("sysadmin_dashboard")

    target_user = get_object_or_404(User, id=user_id)
    if target_user.id == request.user.id:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("sysadmin_dashboard")
    if hasattr(target_user, "profile") and target_user.profile.role == "sysadmin":
        messages.error(request, "Cannot deactivate the System Administrator account.")
        return redirect("sysadmin_dashboard")

    profile = target_user.profile
    profile.is_active = not profile.is_active
    profile.save()

    state = "activated" if profile.is_active else "deactivated"
    log_audit(
        request.user, "toggle_user", "User", str(target_user.id),
        after={"username": target_user.username, "is_active": profile.is_active},
        ip_address=get_client_ip(request),
    )
    messages.success(request, f"User '{target_user.username}' has been {state}.")
    return redirect("sysadmin_dashboard")


# ──────────────────────────────────────────────────────────────────────────────
# Delete user
# ──────────────────────────────────────────────────────────────────────────────

@sysadmin_required
def sysadmin_delete_user(request, user_id):
    """Permanently delete a user (POST only, with confirmation)."""
    if request.method != "POST":
        return redirect("sysadmin_dashboard")

    target_user = get_object_or_404(User, id=user_id)
    if target_user.id == request.user.id:
        messages.error(request, "You cannot delete your own sysadmin account.")
        return redirect("sysadmin_dashboard")
    if hasattr(target_user, "profile") and target_user.profile.role == "sysadmin":
        messages.error(request, "Cannot delete the System Administrator account.")
        return redirect("sysadmin_dashboard")

    username = target_user.username
    log_audit(
        request.user, "delete_user", "User", str(target_user.id),
        after={"username": username},
        ip_address=get_client_ip(request),
    )
    target_user.delete()
    messages.success(request, f"User '{username}' has been permanently deleted.")
    return redirect("sysadmin_dashboard")


# ──────────────────────────────────────────────────────────────────────────────
# Sysadmin change own password
# ──────────────────────────────────────────────────────────────────────────────

@sysadmin_required
def sysadmin_change_own_password(request):
    """Allow the sysadmin to change their own master key."""
    if request.method == "POST":
        current_pw  = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "").strip()
        confirm_pw   = request.POST.get("confirm_password", "").strip()

        errors = []
        if not request.user.check_password(current_pw):
            errors.append("Current master key is incorrect.")
        if new_password != confirm_pw:
            errors.append("New passwords do not match.")
        if new_password:
            try:
                validate_password(new_password, user=request.user)
            except ValidationError as e:
                errors.extend(e.messages)

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "sysadmin/change_password.html")

        request.user.set_password(new_password)
        request.user.save()
        # Update session so user is not logged out
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)

        log_audit(
            request.user, "sysadmin_change_password", "User", str(request.user.id),
            ip_address=get_client_ip(request),
        )
        messages.success(request, "Master key updated successfully.")
        return redirect("sysadmin_dashboard")

    return render(request, "sysadmin/change_password.html")
