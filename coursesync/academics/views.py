from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q

from accounts.decorators import role_required
from .forms import CourseForm, CreateUserForm, MajorForm
from .models import Assignment, Course, Enrollment, Major, StudentProfile, Submission


@login_required
@role_required("student")
def student_dashboard(request):
    approved = (
        Enrollment.objects.filter(student=request.user, status="approved")
        .select_related("course")
        .prefetch_related("course__assignments")
    )
    pending = (
        Enrollment.objects.filter(student=request.user, status="pending")
        .select_related("course")
    )
    denied = (
        Enrollment.objects.filter(student=request.user, status="denied")
        .select_related("course")
    )

    enrolled_course_ids = set(
        Enrollment.objects.filter(student=request.user)
        .exclude(status="denied")
        .values_list("course_id", flat=True)
    )
    available_courses = Course.objects.exclude(id__in=enrolled_course_ids).select_related("professor")

    return render(request, "student.html", {
        "enrollments": approved,
        "pending_enrollments": pending,
        "denied_enrollments": denied,
        "available_courses": available_courses,
        "profile": getattr(request.user, "student_profile", None),
    })


@login_required
@role_required("professor")
def professor_dashboard(request):
    courses = list(
        Course.objects.filter(professor=request.user).annotate(
            student_count=Count("enrollments", filter=Q(enrollments__status="approved"))
        )
    )
    total_students = sum(c.student_count for c in courses)

    return render(request, "professor.html", {
        "courses": courses,
        "total_students": total_students,
    })


@login_required
@role_required("advisor")
def advisor_dashboard(request):
    advisees = (
        StudentProfile.objects.filter(advisor=request.user)
        .select_related("user")
        .prefetch_related("user__enrollments__course")
    )

    pending = (
        Enrollment.objects.filter(
            status="pending",
            student__student_profile__advisor=request.user,
        )
        .select_related("student", "course")
    )

    try:
        assigned_major = request.user.advised_major
    except Exception:
        assigned_major = None

    return render(request, "advisor.html", {
        "advisees": advisees,
        "pending_requests": pending,
        "assigned_major": assigned_major,
    })


@login_required
@role_required("registrar")
def registrar_dashboard(request):
    from accounts.models import User as UserModel
    courses = Course.objects.select_related("professor")
    pending = Enrollment.objects.filter(status="pending").select_related("student", "course")
    majors = Major.objects.select_related("advisor").all()
    student_count = UserModel.objects.filter(role="student").count()

    return render(request, "registrar.html", {
        "courses": courses,
        "pending_requests": pending,
        "majors": majors,
        "student_count": student_count,
    })


@login_required
@role_required("sysadmin")
def sysadmin_dashboard(request):
    from accounts.models import User

    users = User.objects.all().order_by("role", "username")
    majors = Major.objects.select_related("advisor").all()
    role_counts = {
        role: users.filter(role=role).count()
        for role in ["student", "professor", "advisor", "registrar", "sysadmin"]
    }
    return render(request, "sysadmin.html", {
        "users": users,
        "majors": majors,
        "role_counts": role_counts,
    })


@login_required
@role_required("sysadmin")
def create_user(request):
    majors = Major.objects.select_related("advisor").all()
    form = CreateUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("sysadmin_dashboard")
    return render(request, "create_user.html", {"form": form, "majors": majors})


# keep old URL name working
create_student = create_user


@login_required
@role_required("student")
def propose_enrollment(request, course_id):
    if request.method == "POST":
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


@login_required
@role_required("registrar")
def create_course(request):
    form = CourseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.professor = form.cleaned_data.get("professor")
        course.save()
        return redirect("registrar_dashboard")
    return render(request, "course_form.html", {"form": form, "action": "Create"})


@login_required
@role_required("registrar")
def edit_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    form = CourseForm(request.POST or None, instance=course)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.professor = form.cleaned_data.get("professor")
        course.save()
        return redirect("registrar_dashboard")
    return render(request, "course_form.html", {"form": form, "action": "Edit", "course": course})


@login_required
@role_required("registrar")
def create_major(request):
    form = MajorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("registrar_dashboard")
    return render(request, "major_form.html", {"form": form})


@login_required
@role_required("registrar")
def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if request.method == "POST":
        course.delete()
        return redirect("registrar_dashboard")
    return render(request, "course_confirm_delete.html", {"course": course})