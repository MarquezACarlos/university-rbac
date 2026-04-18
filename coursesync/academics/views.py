from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count
from django.shortcuts import render

from accounts.decorators import role_required
from .models import Assignment, Course, Enrollment, StudentProfile, Submission


@login_required
@role_required("student")
def student_dashboard(request):
    enrollments = (
        Enrollment.objects.filter(student=request.user, status="approved")
        .select_related("course")
        .prefetch_related("course__assignments")
    )

    return render(request, "student.html", {
        "enrollments": enrollments,
        "profile": getattr(request.user, "student_profile", None),
    })


@login_required
@role_required("professor")
def professor_dashboard(request):
    courses = Course.objects.filter(professor=request.user).annotate(
        student_count=Count("enrollments")
    )

    return render(request, "professor.html", {
        "courses": courses,
    })


@login_required
@role_required("advisor")
def advisor_dashboard(request):
    advisees = StudentProfile.objects.filter(advisor=request.user).select_related("user")
    pending = Enrollment.objects.filter(
        student__student_profile__advisor=request.user,
        status="pending"
    ).select_related("student", "course")

    return render(request, "advisor.html", {
        "advisees": advisees,
        "pending_requests": pending,
    })


@login_required
@role_required("registrar")
def registrar_dashboard(request):
    courses = Course.objects.select_related("professor")
    pending = Enrollment.objects.filter(status="pending").select_related("student", "course")

    return render(request, "registrar.html", {
        "courses": courses,
        "pending_requests": pending,
    })


@login_required
@role_required("sysadmin")
def sysadmin_dashboard(request):
    from accounts.models import User

    users = User.objects.all().order_by("role", "username")
    return render(request, "sysadmin.html", {
        "users": users,
    })


@login_required
@role_required("student")
def propose_enrollment(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    Enrollment.objects.get_or_create(student=request.user, course=course)
    return redirect("student_dashboard")


@login_required
@role_required("advisor", "registrar")
def approve_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = "approved"
    enrollment.reviewed_by = request.user
    enrollment.save()
    return redirect("dashboard_router")


@login_required
@role_required("advisor", "registrar")
def deny_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = "denied"
    enrollment.reviewed_by = request.user
    enrollment.save()
    return redirect("dashboard_router")