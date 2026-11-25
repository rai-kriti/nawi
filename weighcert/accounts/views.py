from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .forms import LoginForm, ForcePasswordChangeForm
from .middleware import get_client_ip, is_user_locked_out, record_failed_attempt, clear_failed_attempts
from core.audit import log_audit


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    ip = get_client_ip(request)
    form = LoginForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            username = form.cleaned_data["username"].strip()
            password = form.cleaned_data["password"]

            # Check lockout
            locked, mins = is_user_locked_out(username, ip)
            if locked:
                messages.error(
                    request,
                    f"Account locked due to multiple failed attempts. Please try again in {mins} minute(s)."
                )
                return render(request, "accounts/login.html", {"form": form})

            user = authenticate(request, username=username, password=password)
            if user is not None:
                if hasattr(user, "profile") and not user.profile.is_active:
                    messages.error(request, "This account has been deactivated. Please contact your Administrator.")
                    return render(request, "accounts/login.html", {"form": form})

                clear_failed_attempts(username, ip)
                login(request, user)
                log_audit(user, "login", "User", str(user.id), after={"username": username}, ip_address=ip)

                if hasattr(user, "profile") and user.profile.must_change_password:
                    return redirect("change_password")

                next_url = request.GET.get("next") or reverse("dashboard")
                return redirect(next_url)
            else:
                attempts, until = record_failed_attempt(username, ip)
                if until:
                    messages.error(request, "Too many failed attempts. Account locked for 10 minutes.")
                else:
                    messages.error(request, f"Invalid credentials. Attempt {attempts} of 5.")

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    if request.user.is_authenticated:
        log_audit(request.user, "logout", "User", str(request.user.id), ip_address=get_client_ip(request))
        logout(request)
    return redirect("login")


@login_required
def change_password_view(request):
    form = ForcePasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        if hasattr(request.user, "profile"):
            request.user.profile.must_change_password = False
            request.user.profile.save()
        log_audit(request.user, "change_password", "User", str(request.user.id), ip_address=get_client_ip(request))
        messages.success(request, "Password updated successfully.")
        return redirect("dashboard")

    return render(request, "accounts/change_password.html", {"form": form})

