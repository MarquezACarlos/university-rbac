from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q, Sum

from accounts.decorators import role_required
from .forms import CourseForm, CreateUserForm, EditUserForm, MajorForm
from decimal import Decimal

from .models import Assignment, Course, Enrollment, Grade, Major, RegistrarEnrollmentChange, StudentProfile, Submission, TAProfile, TranscriptEntry

GRADE_POINTS = {
    "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0,
    "F": 0.0,
}


def _credit_counts(student):
    """Return (credits_enrolled, credits_earned) for a student."""
    approved = Enrollment.objects.filter(student=student, status="approved").select_related("course")
    credits_enrolled = sum(e.course.credits for e in approved)
    graded_ids = set(Grade.objects.filter(enrollment__in=approved).values_list("enrollment_id", flat=True))
    credits_earned = (
        sum(e.course.credits for e in approved if e.id in graded_ids)
        + sum(t.credits for t in TranscriptEntry.objects.filter(student=student))
    )
    return credits_enrolled, credits_earned


def _recalculate_gpa(student):
    """Recompute GPA from graded enrollments + transcript entries and save to profile."""
    approved = Enrollment.objects.filter(student=student, status="approved").select_related("course")
    grades = Grade.objects.filter(enrollment__in=approved).select_related("enrollment__course")

    total_points = Decimal("0")
    total_credits = 0

    for g in grades:
        pts = Decimal(str(GRADE_POINTS.get(g.final_grade, 0.0)))
        cr = g.enrollment.course.credits
        total_points += pts * cr
        total_credits += cr

    for t in TranscriptEntry.objects.filter(student=student):
        pts = Decimal(str(GRADE_POINTS.get(t.grade, 0.0)))
        total_points += pts * t.credits
        total_credits += t.credits

    gpa = (total_points / total_credits).quantize(Decimal("0.01")) if total_credits else Decimal("0.00")
    try:
        profile = student.student_profile
        profile.gpa = gpa
        profile.save()
    except StudentProfile.DoesNotExist:
        pass
    return gpa


@login_required
@role_required("student", "ta")
def student_dashboard(request):
    if request.user.role == "ta":
        return redirect("ta_dashboard")
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

    credits_enrolled, credits_earned = _credit_counts(request.user)
    return render(request, "student.html", {
        "enrollments": approved,
        "pending_enrollments": pending,
        "denied_enrollments": denied,
        "available_courses": available_courses,
        "profile": getattr(request.user, "student_profile", None),
        "credits_enrolled": credits_enrolled,
        "credits_earned": credits_earned,
    })


@login_required
@role_required("ta")
def ta_dashboard(request):
    approved = (
        Enrollment.objects.filter(student=request.user, status="approved")
        .select_related("course")
        .prefetch_related("course__assignments")
    )
    pending = Enrollment.objects.filter(student=request.user, status="pending").select_related("course")
    denied = Enrollment.objects.filter(student=request.user, status="denied").select_related("course")

    enrolled_course_ids = set(
        Enrollment.objects.filter(student=request.user)
        .exclude(status="denied")
        .values_list("course_id", flat=True)
    )
    available_courses = Course.objects.exclude(id__in=enrolled_course_ids).select_related("professor")

    ta_course = None
    try:
        ta_profile = request.user.ta_profile
        if ta_profile.course_id:
            ta_course = (
                Course.objects.filter(id=ta_profile.course_id)
                .annotate(student_count=Count("enrollments", filter=Q(enrollments__status="approved")))
                .select_related("professor")
                .first()
            )
    except TAProfile.DoesNotExist:
        pass

    credits_enrolled, credits_earned = _credit_counts(request.user)
    return render(request, "ta.html", {
        "enrollments": approved,
        "pending_enrollments": pending,
        "denied_enrollments": denied,
        "available_courses": available_courses,
        "ta_course": ta_course,
        "profile": getattr(request.user, "student_profile", None),
        "credits_enrolled": credits_enrolled,
        "credits_earned": credits_earned,
    })


@login_required
@role_required("ta")
def ta_course_grades(request, course_id):
    get_object_or_404(TAProfile, user=request.user, course_id=course_id)
    course = get_object_or_404(Course, id=course_id)
    enrollments = (
        Enrollment.objects.filter(course=course, status="approved")
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    grade_rows = []
    for enrollment in enrollments:
        grade_obj = Grade.objects.filter(enrollment=enrollment).first()
        final_grade = grade_obj.final_grade if grade_obj else ""
        numeric = float(grade_obj.numeric_grade) if grade_obj else None
        if final_grade:
            status = "at_risk" if numeric is not None and numeric < 1.0 else "graded"
        else:
            status = "pending"
        grade_rows.append({
            "enrollment": enrollment,
            "student": enrollment.student,
            "final_grade": final_grade,
            "status": status,
        })
    return render(request, "course_grades.html", {
        "course": course,
        "grade_rows": grade_rows,
        "grade_choices": [],
        "readonly": True,
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
@role_required("professor")
def professor_course_grades(request, course_id):
    course = get_object_or_404(Course, id=course_id, professor=request.user)

    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("grade_"):
                enrollment_id = key[len("grade_"):]
                enrollment = Enrollment.objects.filter(id=enrollment_id, course=course, status="approved").first()
                if not enrollment:
                    continue
                value = value.strip().upper()
                if value in GRADE_POINTS:
                    Grade.objects.update_or_create(
                        enrollment=enrollment,
                        defaults={
                            "final_grade": value,
                            "numeric_grade": Decimal(str(GRADE_POINTS[value])),
                        },
                    )
                    _recalculate_gpa(enrollment.student)
                elif value == "":
                    Grade.objects.filter(enrollment=enrollment).delete()
                    _recalculate_gpa(enrollment.student)
        messages.success(request, f"Grades saved for {course.code}.")
        return redirect("professor_course_grades", course_id=course.id)

    enrollments = (
        Enrollment.objects.filter(course=course, status="approved")
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    grade_rows = []
    for enrollment in enrollments:
        grade_obj = Grade.objects.filter(enrollment=enrollment).first()
        final_grade = grade_obj.final_grade if grade_obj else ""
        numeric = float(grade_obj.numeric_grade) if grade_obj else None
        if final_grade:
            status = "at_risk" if numeric is not None and numeric < 1.0 else "graded"
        else:
            status = "pending"
        grade_rows.append({
            "enrollment": enrollment,
            "student": enrollment.student,
            "final_grade": final_grade,
            "status": status,
        })

    grade_choices = [g for g, _ in [
        ("A", "A"), ("A-", "A-"),
        ("B+", "B+"), ("B", "B"), ("B-", "B-"),
        ("C+", "C+"), ("C", "C"), ("C-", "C-"),
        ("D+", "D+"), ("D", "D"), ("F", "F"),
    ]]

    return render(request, "course_grades.html", {
        "course": course,
        "grade_rows": grade_rows,
        "grade_choices": grade_choices,
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

    pending_changes = (
        RegistrarEnrollmentChange.objects.filter(
            status="pending",
            student__student_profile__advisor=request.user,
        )
        .select_related("student", "course", "proposed_by")
        .order_by("proposed_at")
    )

    pending_drops = (
        Enrollment.objects.filter(
            status="drop_pending",
            student__student_profile__advisor=request.user,
        )
        .select_related("student", "course")
        .order_by("proposed_at")
    )

    return render(request, "advisor.html", {
        "advisees": advisees,
        "pending_requests": pending,
        "assigned_major": assigned_major,
        "pending_changes": pending_changes,
        "pending_drops": pending_drops,
    })


@login_required
@role_required("registrar")
def registrar_dashboard(request):
    from accounts.models import User as UserModel
    courses = Course.objects.select_related("professor")
    majors = Major.objects.select_related("advisor").all()
    student_count = UserModel.objects.filter(role="student").count()

    return render(request, "registrar.html", {
        "courses": courses,
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
        for role in ["student", "ta", "professor", "advisor", "registrar", "sysadmin"]
    }
    return render(request, "sysadmin.html", {
        "users": users,
        "majors": majors,
        "role_counts": role_counts,
    })


@login_required
@role_required("sysadmin")
def rbac_policies(request):
    roles = ["student", "ta", "professor", "advisor", "registrar", "sysadmin"]

    # Each policy: (category, label, set of roles that have this permission)
    policies = [
        ("Enrollment", "Request course enrollment",        {"student", "ta"}),
        ("Enrollment", "View own enrollments",             {"student", "ta"}),
        ("Enrollment", "Approve enrollment requests",      {"advisor"}),
        ("Enrollment", "Deny enrollment requests",         {"advisor"}),
        ("Courses",    "View available courses",           {"student", "ta", "professor", "advisor", "registrar", "sysadmin"}),
        ("Courses",    "View own course roster",           {"professor"}),
        ("Courses",    "View all course grade rosters",    {"ta"}),
        ("Courses",    "Create courses",                   {"registrar"}),
        ("Courses",    "Edit courses",                     {"registrar"}),
        ("Courses",    "Delete courses",                   {"registrar"}),
        ("Grades",     "View own grades",                  {"student", "ta"}),
        ("Grades",     "View course grades (read-only)",   {"ta"}),
        ("Grades",     "Enter / edit grades",              {"professor"}),
        ("Majors",     "Create majors",                    {"registrar"}),
        ("Students",   "View assigned advisees",           {"advisor"}),
        ("Students",   "View pending requests (own advisees)", {"advisor"}),
        ("Students",   "View all student enrollments",     set()),
        ("Users",      "Create user accounts",             {"sysadmin"}),
        ("Users",      "Edit user accounts",               {"sysadmin"}),
        ("Users",      "Delete user accounts",             {"sysadmin"}),
        ("Users",      "View all users",                   {"sysadmin"}),
        ("System",     "Access admin dashboard",           {"sysadmin"}),
        ("System",     "Manage RBAC policies (view)",      {"sysadmin"}),
    ]

    # Group by category
    from itertools import groupby
    categories = []
    for cat, items in groupby(policies, key=lambda p: p[0]):
        categories.append((cat, list(items)))

    return render(request, "rbac_policies.html", {
        "roles": roles,
        "categories": categories,
    })


@login_required
@role_required("sysadmin")
def users_list(request):
    from accounts.models import User

    role_filter = request.GET.get("role", "all")
    users = User.objects.all().order_by("role", "username")
    role_counts = {
        role: users.filter(role=role).count()
        for role in ["student", "ta", "professor", "advisor", "registrar", "sysadmin"]
    }
    if role_filter != "all":
        users = users.filter(role=role_filter)
    return render(request, "users_list.html", {
        "users": users,
        "role_counts": role_counts,
        "active_role": role_filter,
        "total": User.objects.count(),
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
@role_required("student", "ta")
def course_catalog(request):
    enrolled_course_ids = set(
        Enrollment.objects.filter(student=request.user)
        .exclude(status="denied")
        .values_list("course_id", flat=True)
    )
    available_courses = Course.objects.exclude(id__in=enrolled_course_ids).select_related("professor")
    return render(request, "course_catalog.html", {
        "available_courses": available_courses,
        "profile": getattr(request.user, "student_profile", None),
    })


@login_required
@role_required("student", "ta")
def my_courses(request):
    approved = (
        Enrollment.objects.filter(student=request.user, status="approved")
        .select_related("course__professor")
    )
    drop_pending = (
        Enrollment.objects.filter(student=request.user, status="drop_pending")
        .select_related("course__professor")
    )
    credits_enrolled, credits_earned = _credit_counts(request.user)
    return render(request, "my_courses.html", {
        "enrollments": approved,
        "drop_pending": drop_pending,
        "profile": getattr(request.user, "student_profile", None),
        "credits_enrolled": credits_enrolled,
        "credits_earned": credits_earned,
    })


@login_required
@role_required("student", "ta")
def student_drop_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, student=request.user, status="approved")
    if request.method == "POST":
        credits_after = (
            Enrollment.objects.filter(student=request.user, status="approved")
            .exclude(id=enrollment_id)
            .aggregate(total=Sum("course__credits"))["total"] or 0
        )
        if credits_after >= 12:
            enrollment.delete()
            messages.success(request, f"You have been dropped from {enrollment.course.code}.")
        else:
            enrollment.status = "drop_pending"
            enrollment.save()
            messages.success(
                request,
                f"Drop request for {enrollment.course.code} submitted. Advisor approval required "
                f"because your credits would fall below 12."
            )
    return redirect("my_courses")


@login_required
@role_required("student", "ta")
def student_grades(request):
    profile = getattr(request.user, "student_profile", None)
    gpa = profile.gpa if profile else None

    graded_rows = []
    enrollments = (
        Enrollment.objects.filter(student=request.user, status="approved")
        .select_related("course__professor")
        .order_by("course__code")
    )
    for enrollment in enrollments:
        grade = Grade.objects.filter(enrollment=enrollment).first()
        graded_rows.append({
            "enrollment": enrollment,
            "course": enrollment.course,
            "grade": grade,
        })

    transcript_entries = (
        TranscriptEntry.objects.filter(student=request.user)
        .order_by("course_code")
    )

    return render(request, "student_grades.html", {
        "graded_rows": graded_rows,
        "transcript_entries": transcript_entries,
        "gpa": gpa,
        "profile": profile,
        "at_risk": gpa is not None and gpa < 2,
    })


@login_required
@role_required("student", "ta")
def student_course_detail(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment, id=enrollment_id, student=request.user, status="approved"
    )
    grade = Grade.objects.filter(enrollment=enrollment).first()
    return render(request, "student_course_detail.html", {
        "enrollment": enrollment,
        "course": enrollment.course,
        "grade": grade,
    })


@login_required
@role_required("student", "ta")
def enrollment_history(request):
    denied = (
        Enrollment.objects.filter(student=request.user, status="denied")
        .select_related("course__professor", "reviewed_by")
    )
    return render(request, "enrollment_history.html", {
        "denied_enrollments": denied,
        "profile": getattr(request.user, "student_profile", None),
    })


@login_required
@role_required("student", "ta")
def propose_enrollment(request, course_id):
    if request.method == "POST":
        course = get_object_or_404(Course, id=course_id)
        approved_credits = (
            Enrollment.objects.filter(student=request.user, status="approved")
            .select_related("course")
            .aggregate(total=Sum("course__credits"))["total"] or 0
        )
        if approved_credits + course.credits > 20:
            messages.error(
                request,
                f"Cannot request {course.code}: you have {approved_credits} approved credit hours "
                f"and this course is {course.credits} credits, which would exceed the 20-credit limit."
            )
            return redirect("course_catalog")
        Enrollment.objects.get_or_create(student=request.user, course=course)
    return redirect("course_catalog")


@login_required
@role_required("advisor")
def student_detail(request, student_id):
    from accounts.models import User
    student = get_object_or_404(User, id=student_id, role="student")
    # Ensure this student is assigned to the requesting advisor
    if not StudentProfile.objects.filter(user=student, advisor=request.user).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    approved = Enrollment.objects.filter(student=student, status="approved").select_related("course__professor")
    denied = Enrollment.objects.filter(student=student, status="denied").select_related("course__professor", "reviewed_by")
    profile = getattr(student, "student_profile", None)
    credits_enrolled, credits_earned = _credit_counts(student)
    return render(request, "student_detail.html", {
        "student": student,
        "profile": profile,
        "approved_enrollments": approved,
        "denied_enrollments": denied,
        "credits_enrolled": credits_enrolled,
        "credits_earned": credits_earned,
    })


@login_required
@role_required("advisor")
def drop_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, status="approved")
    # Ensure the student belongs to this advisor
    if not StudentProfile.objects.filter(user=enrollment.student, advisor=request.user).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.method == "POST":
        enrollment.delete()
    return redirect("student_detail", student_id=enrollment.student.id)


@login_required
@role_required("advisor")
def approve_drop(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, status="drop_pending")
    if not StudentProfile.objects.filter(user=enrollment.student, advisor=request.user).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.method == "POST":
        enrollment.delete()
        messages.success(request, f"Drop approved: {enrollment.student.get_full_name()} removed from {enrollment.course.code}.")
    return redirect("advisor_dashboard")


@login_required
@role_required("advisor")
def deny_drop(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, status="drop_pending")
    if not StudentProfile.objects.filter(user=enrollment.student, advisor=request.user).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.method == "POST":
        enrollment.status = "approved"
        enrollment.reviewed_by = request.user
        enrollment.save()
        messages.success(request, f"Drop denied: {enrollment.student.get_full_name()} remains enrolled in {enrollment.course.code}.")
    return redirect("advisor_dashboard")


@login_required
@role_required("advisor")
def approve_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    approved_credits = (
        Enrollment.objects.filter(student=enrollment.student, status="approved")
        .select_related("course")
        .aggregate(total=Sum("course__credits"))["total"] or 0
    )
    if approved_credits + enrollment.course.credits > 20:
        messages.error(
            request,
            f"Cannot approve: {enrollment.student.get_full_name()} already has {approved_credits} approved "
            f"credit hours. Adding {enrollment.course.code} ({enrollment.course.credits} credits) would exceed the 20-credit limit."
        )
        return redirect("advisor_dashboard")
    enrollment.status = "approved"
    enrollment.reviewed_by = request.user
    enrollment.save()
    return redirect("dashboard_router")


@login_required
@role_required("advisor")
def deny_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = "denied"
    enrollment.reviewed_by = request.user
    enrollment.save()
    return redirect("dashboard_router")


@login_required
@role_required("registrar")
def registrar_students(request):
    from accounts.models import User
    students = (
        User.objects.filter(role="student")
        .select_related("student_profile__advisor")
        .order_by("last_name", "first_name")
    )
    return render(request, "registrar_students.html", {"students": students})


@login_required
@role_required("registrar")
def registrar_student_enrollment(request, student_id):
    from accounts.models import User
    student = get_object_or_404(User, id=student_id, role="student")
    profile = getattr(student, "student_profile", None)
    # Registrar can only touch denied (history) enrollments, not current approved ones
    denied = Enrollment.objects.filter(student=student, status="denied").select_related("course__professor")
    pending_changes = (
        RegistrarEnrollmentChange.objects.filter(student=student, status="pending")
        .select_related("course", "proposed_by")
    )
    # Courses already pending a change cannot be proposed again
    pending_course_ids = set(pending_changes.values_list("course_id", flat=True))
    actionable = [e for e in denied if e.course_id not in pending_course_ids]
    credits_enrolled, credits_earned = _credit_counts(student)
    from .models import GRADE_CHOICES
    transcript_entries = TranscriptEntry.objects.filter(student=student).select_related("added_by").order_by("-added_at")
    return render(request, "registrar_student_enrollment.html", {
        "student": student,
        "profile": profile,
        "denied_enrollments": actionable,
        "pending_changes": pending_changes,
        "credits_enrolled": credits_enrolled,
        "credits_earned": credits_earned,
        "transcript_entries": transcript_entries,
        "grade_choices": GRADE_CHOICES,
    })


@login_required
@role_required("registrar")
def propose_enrollment_add(request, student_id):
    from accounts.models import User
    if request.method != "POST":
        return redirect("registrar_student_enrollment", student_id=student_id)
    student = get_object_or_404(User, id=student_id, role="student")
    enrollment_id = request.POST.get("enrollment_id")
    # Only denied enrollments are eligible
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, student=student, status="denied")
    note = request.POST.get("note", "")
    _, created = RegistrarEnrollmentChange.objects.get_or_create(
        student=student, course=enrollment.course, change_type="add", status="pending",
        defaults={"proposed_by": request.user, "note": note},
    )
    if not created:
        messages.error(request, f"An add request for {enrollment.course.code} is already pending advisor review.")
    else:
        messages.success(request, f"Re-enroll request for {enrollment.course.code} sent to {student.get_full_name()}'s advisor.")
    return redirect("registrar_student_enrollment", student_id=student_id)


@login_required
@role_required("registrar")
def propose_enrollment_remove(request, student_id):
    from accounts.models import User
    if request.method != "POST":
        return redirect("registrar_student_enrollment", student_id=student_id)
    student = get_object_or_404(User, id=student_id, role="student")
    enrollment_id = request.POST.get("enrollment_id")
    # Only denied enrollments are eligible — cannot touch current approved enrollments
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, student=student, status="denied")
    note = request.POST.get("note", "")
    _, created = RegistrarEnrollmentChange.objects.get_or_create(
        student=student, course=enrollment.course, change_type="remove", status="pending",
        defaults={"proposed_by": request.user, "note": note},
    )
    if not created:
        messages.error(request, f"A remove request for {enrollment.course.code} is already pending advisor review.")
    else:
        messages.success(request, f"Remove request for {enrollment.course.code} sent to advisor.")
    return redirect("registrar_student_enrollment", student_id=student_id)


@login_required
@role_required("advisor")
def review_enrollment_change(request, change_id):
    change = get_object_or_404(RegistrarEnrollmentChange, id=change_id, status="pending")
    if not StudentProfile.objects.filter(user=change.student, advisor=request.user).exists():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.method != "POST":
        return redirect("advisor_dashboard")
    action = request.POST.get("action")
    if action == "approve":
        if change.change_type == "add":
            credits_enrolled, _ = _credit_counts(change.student)
            if credits_enrolled + change.course.credits > 20:
                messages.error(
                    request,
                    f"Cannot approve: {change.student.get_full_name()} already has {credits_enrolled} approved "
                    f"credit hours. Adding {change.course.code} would exceed the 20-credit limit."
                )
                return redirect("advisor_dashboard")
            # Promote the existing denied enrollment to approved
            Enrollment.objects.filter(
                student=change.student, course=change.course, status="denied"
            ).update(status="approved", reviewed_by=request.user)
        elif change.change_type == "remove":
            # Delete the denied enrollment record from history
            Enrollment.objects.filter(student=change.student, course=change.course, status="denied").delete()
        change.status = "approved"
        change.reviewed_by = request.user
        change.save()
        messages.success(request, f"Change approved: {change.change_type} {change.course.code} for {change.student.get_full_name()}.")
    elif action == "deny":
        change.status = "denied"
        change.reviewed_by = request.user
        change.save()
        messages.success(request, f"Change denied: {change.change_type} {change.course.code}.")
    return redirect("advisor_dashboard")


@login_required
@role_required("registrar")
def add_transcript_entry(request, student_id):
    from accounts.models import User
    from .models import GRADE_CHOICES
    if request.method != "POST":
        return redirect("registrar_student_enrollment", student_id=student_id)
    student = get_object_or_404(User, id=student_id, role="student")
    course_code = request.POST.get("course_code", "").strip()
    course_name = request.POST.get("course_name", "").strip()
    credits_raw = request.POST.get("credits", "3")
    grade = request.POST.get("grade", "")
    valid_grades = [g[0] for g in GRADE_CHOICES]
    if not course_code or not course_name or grade not in valid_grades:
        messages.error(request, "Please fill in all fields with valid values.")
        return redirect("registrar_student_enrollment", student_id=student_id)
    try:
        credits = int(credits_raw)
        if credits < 1 or credits > 6:
            raise ValueError
    except ValueError:
        messages.error(request, "Credits must be a whole number between 1 and 6.")
        return redirect("registrar_student_enrollment", student_id=student_id)
    TranscriptEntry.objects.create(
        student=student,
        course_code=course_code,
        course_name=course_name,
        credits=credits,
        grade=grade,
        added_by=request.user,
    )
    _recalculate_gpa(student)
    messages.success(request, f"Transcript entry for {course_code} added and GPA updated.")
    return redirect("registrar_student_enrollment", student_id=student_id)


@login_required
@role_required("registrar")
def delete_transcript_entry(request, student_id, entry_id):
    from accounts.models import User
    if request.method != "POST":
        return redirect("registrar_student_enrollment", student_id=student_id)
    student = get_object_or_404(User, id=student_id, role="student")
    entry = get_object_or_404(TranscriptEntry, id=entry_id, student=student)
    entry.delete()
    _recalculate_gpa(student)
    messages.success(request, f"Transcript entry for {entry.course_code} removed and GPA updated.")
    return redirect("registrar_student_enrollment", student_id=student_id)


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
@role_required("sysadmin")
def edit_user(request, user_id):
    from accounts.models import User
    user = get_object_or_404(User, id=user_id)
    form = EditUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("users_list")
    return render(request, "edit_user.html", {
        "form": form,
        "edited_user": user,
        "courses": Course.objects.select_related("professor").all(),
    })


@login_required
@role_required("sysadmin")
def delete_user(request, user_id):
    from accounts.models import User
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect("users_list")
        user.delete()
        return redirect("users_list")
    return render(request, "user_confirm_delete.html", {"deleted_user": user})


@login_required
@role_required("registrar")
def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if request.method == "POST":
        course.delete()
        return redirect("registrar_dashboard")
    return render(request, "course_confirm_delete.html", {"course": course})