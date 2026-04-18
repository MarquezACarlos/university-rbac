from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .forms import LoginForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard_router")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard_router")
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
    elif user.role == "professor":
        return redirect("professor_dashboard")
    elif user.role == "advisor":
        return redirect("advisor_dashboard")
    elif user.role == "registrar":
        return redirect("registrar_dashboard")
    elif user.role == "sysadmin":
        return redirect("sysadmin_dashboard")

    return redirect("login")