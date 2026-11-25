"""Role-based access decorators."""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def role_required(*roles):
    """Restrict a view to users with any of the given roles."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            # Admin can view everything (but not create/edit tests)
            if not hasattr(request.user, "profile"):
                messages.error(request, "Your account has no role assigned.")
                return redirect("login")
            if not request.user.profile.is_active:
                messages.error(request, "Your account is deactivated.")
                return redirect("login")
            if request.user.profile.role not in roles:
                messages.error(request, "You do not have permission to access that page.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def sysadmin_required(view_func):
    """Only the System Administrator can access this view."""
    return role_required("sysadmin")(view_func)


def inspector_required(view_func):
    return role_required("inspector")(view_func)


def officer_required(view_func):
    return role_required("officer")(view_func)


def admin_required(view_func):
    return role_required("admin")(view_func)


def staff_required(view_func):
    """Any logged-in staff member (inspector, officer, admin, sysadmin)."""
    return role_required("inspector", "officer", "admin", "sysadmin")(view_func)

