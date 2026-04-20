from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import LoginForm


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard_router")

    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            from academics.models import AuditLog
            AuditLog.objects.create(
                actor_label=user.username,
                action="logged in —",
                target=f"role: {user.role.upper()}",
                event_type=f"AUTH_SUCCESS · ip: {_get_client_ip(request)}",
                color="green",
            )
            return redirect("dashboard_router")
        ip = _get_client_ip(request)
        from academics.models import AuditLog
        AuditLog.objects.create(
            actor_label=username or "unknown",
            action="failed login attempt —",
            target="invalid credentials",
            event_type=f"AUTH_FAIL · ip: {ip}",
            color="red",
        )
        messages.error(request, "Invalid username or password.")

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard_router(request):
    user = request.user

    if user.is_superuser:
        return redirect("sysadmin_dashboard")

    if user.role == "student":
        return redirect("student_dashboard")
    elif user.role == "ta":
        return redirect("ta_dashboard")
    elif user.role == "professor":
        return redirect("professor_dashboard")
    elif user.role == "advisor":
        return redirect("advisor_dashboard")
    elif user.role == "registrar":
        return redirect("registrar_dashboard")
    elif user.role == "sysadmin":
        return redirect("sysadmin_dashboard")

    return redirect("login")