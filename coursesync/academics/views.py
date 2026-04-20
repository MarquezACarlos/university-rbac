from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q, Sum
from django.core.exceptions import PermissionDenied

from accounts.decorators import role_required
from .forms import CourseForm, CreateUserForm, EditUserForm, MajorForm
from decimal import Decimal

from .models import Assignment, AuditLog, Course, Enrollment, Grade, Major, RegistrarEnrollmentChange, StudentProfile, Submission, TAProfile, TranscriptEntry


def _log(actor_label, action, target, event_type, color="green"):
    AuditLog.objects.create(
        actor_label=actor_label,
        action=action,
        target=target,
        event_type=event_type,
        color=color,
    )

GRADE_POINTS = {
    "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0,
    "F": 0.0,
}

GRADE_CHOICES_LIST = [
    ("A", "A"), ("A-", "A-"),
    ("B+", "B+"), ("B", "B"), ("B-", "B-"),
    ("C+", "C+"), ("C", "C"), ("C-", "C-"),
    ("D+", "D+"), ("D", "D"), ("F", "F"),
]


def _credit_counts(student):
    """Return (credits_enrolled, credits_earned) for a student."""
    approved = Enrollment.objects.filter(student=student, status="approved").select_related("course")
    credits_enrolled = sum(e.course.credits for e in approved)
    graded_ids = set(Grade.objects.filter(enrollment__in=approved, published=True).values_list("enrollment_id", flat=True))
    credits_earned = (
        sum(e.course.credits for e in approved if e.id in graded_ids)
        + sum(t.credits for t in TranscriptEntry.objects.filter(student=student))
    )
    return credits_enrolled, credits_earned


def _recalculate_gpa(student):
    """Recompute GPA from published graded enrollments + transcript entries and save to profile."""
    approved = Enrollment.objects.filter(student=student, status="approved").select_related("course")
    grades = Grade.objects.filter(enrollment__in=approved, published=True).select_related("enrollment__course")

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
def set_theme(request):
    if request.method == "POST":
        theme = request.POST.get("theme", "light")
        if theme in ("light", "dark"):
            request.session["theme"] = theme
    return redirect(request.POST.get("next", "/"))


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

    ta_course = None
    try:
        ta_profile = request.user.ta_profile
        if ta_profile.course_id:
            # Exclude TA's assigned course from the course catalog
            enrolled_course_ids.add(ta_profile.course_id)
            ta_course = (
                Course.objects.filter(id=ta_profile.course_id)
                .annotate(student_count=Count("enrollments", filter=Q(enrollments__status="approved")))
                .select_related("professor")
                .first()
            )
    except TAProfile.DoesNotExist:
        pass

    available_courses = Course.objects.exclude(id__in=enrolled_course_ids).select_related("professor")

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

    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("propose_"):
                enrollment_id = key[len("propose_"):]
                enrollment = Enrollment.objects.filter(id=enrollment_id, course=course, status="approved").first()
                if not enrollment:
                    continue
                value = value.strip().upper()
                if value in GRADE_POINTS:
                    grade_obj, _ = Grade.objects.get_or_create(enrollment=enrollment)
                    grade_obj.proposed_grade = value
                    grade_obj.proposed_by = request.user
                    grade_obj.save()
                elif value == "":
                    Grade.objects.filter(enrollment=enrollment).update(proposed_grade="", proposed_by=None)
        messages.success(request, f"Grade proposals submitted for {course.code}.")
        return redirect("ta_course_grades", course_id=course.id)

    enrollments = (
        Enrollment.objects.filter(course=course, status="approved")
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    grade_choices = [g for g, _ in GRADE_CHOICES_LIST]
    grade_rows = []
    for enrollment in enrollments:
        grade_obj = Grade.objects.filter(enrollment=enrollment).first()
        final_grade = grade_obj.final_grade if (grade_obj and grade_obj.published) else ""
        proposed_grade = grade_obj.proposed_grade if grade_obj else ""
        numeric = float(grade_obj.numeric_grade) if (grade_obj and grade_obj.numeric_grade) else None
        if final_grade:
            status = "at_risk" if numeric is not None and numeric < 1.0 else "graded"
        elif proposed_grade:
            status = "proposed"
        else:
            status = "pending"
        grade_rows.append({
            "enrollment": enrollment,
            "student": enrollment.student,
            "final_grade": final_grade,
            "proposed_grade": proposed_grade,
            "status": status,
        })
    return render(request, "course_grades.html", {
        "course": course,
        "grade_rows": grade_rows,
        "grade_choices": grade_choices,
        "is_ta": True,
    })


@login_required
@role_required("professor")
def professor_dashboard(request):
    courses = list(
        Course.objects.filter(professor=request.user).annotate(
            student_count=Count("enrollments", filter=Q(enrollments__status="approved"))
        ).prefetch_related("teaching_assistants__user")
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
        approve_id = request.POST.get("approve_proposal")
        reject_id = request.POST.get("reject_proposal")

        if approve_id:
            enrollment = Enrollment.objects.filter(id=approve_id, course=course, status="approved").first()
            if enrollment:
                grade_obj = Grade.objects.filter(enrollment=enrollment).first()
                if grade_obj and grade_obj.proposed_grade:
                    override = request.POST.get(f"grade_{approve_id}", "").strip().upper()
                    accepted_grade = override if override in GRADE_POINTS else grade_obj.proposed_grade
                    grade_obj.final_grade = accepted_grade
                    grade_obj.numeric_grade = Decimal(str(GRADE_POINTS[accepted_grade]))
                    grade_obj.proposed_grade = ""
                    grade_obj.proposed_by = None
                    grade_obj.published = True
                    grade_obj.save()
                    _recalculate_gpa(enrollment.student)
                    messages.success(request, f"Grade approved for {enrollment.student.get_full_name()}.")
            return redirect("professor_course_grades", course_id=course.id)

        elif reject_id:
            enrollment = Enrollment.objects.filter(id=reject_id, course=course, status="approved").first()
            if enrollment:
                Grade.objects.filter(enrollment=enrollment).update(proposed_grade="", proposed_by=None)
                messages.success(request, f"Proposed grade rejected for {enrollment.student.get_full_name()}.")
            return redirect("professor_course_grades", course_id=course.id)

        else:
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
                                "proposed_grade": "",
                                "proposed_by": None,
                                "published": True,
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
        proposed_grade = grade_obj.proposed_grade if grade_obj else ""
        published = grade_obj.published if grade_obj else False
        numeric = float(grade_obj.numeric_grade) if (grade_obj and grade_obj.numeric_grade) else None
        if final_grade and published:
            status = "at_risk" if numeric is not None and numeric < 1.0 else "graded"
        elif proposed_grade:
            status = "proposed"
        else:
            status = "pending"
        grade_rows.append({
            "enrollment": enrollment,
            "student": enrollment.student,
            "final_grade": final_grade,
            "proposed_grade": proposed_grade,
            "proposed_by": grade_obj.proposed_by if grade_obj else None,
            "published": published,
            "status": status,
        })

    grade_choices = [g for g, _ in GRADE_CHOICES_LIST]

    return render(request, "course_grades.html", {
        "course": course,
        "grade_rows": grade_rows,
        "grade_choices": grade_choices,
        "is_ta": False,
    })


@login_required
@role_required("professor")
def professor_assign_ta(request, course_id):
    from accounts.models import User as UserModel
    course = get_object_or_404(Course, id=course_id, professor=request.user)
    current_ta_profile = TAProfile.objects.filter(course=course).select_related("user").first()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "assign":
            student_id = request.POST.get("student_id")
            student = get_object_or_404(UserModel, id=student_id, role="student")

            if Enrollment.objects.filter(student=student, course=course, status__in=["approved", "pending"]).exists():
                messages.error(
                    request,
                    f"{student.get_full_name()} is currently enrolled in {course.code}. "
                    "They must be dropped from the course before being assigned as TA."
                )
                return redirect("professor_assign_ta", course_id=course_id)

            if current_ta_profile:
                old_ta = current_ta_profile.user
                current_ta_profile.delete()
                old_ta.role = "student"
                old_ta.save()

            student.role = "ta"
            student.save()
            TAProfile.objects.create(user=student, course=course)
            messages.success(request, f"{student.get_full_name()} has been assigned as TA for {course.code}.")
            return redirect("professor_dashboard")

        elif action == "remove":
            if current_ta_profile:
                old_ta = current_ta_profile.user
                current_ta_profile.delete()
                old_ta.role = "student"
                old_ta.save()
                messages.success(request, f"{old_ta.get_full_name()} has been removed as TA for {course.code}.")
            return redirect("professor_assign_ta", course_id=course_id)

    enrolled_ids = set(
        Enrollment.objects.filter(course=course, status__in=["approved", "pending"])
        .values_list("student_id", flat=True)
    )
    search_query = request.GET.get("q", "").strip()
    available_students = (
        UserModel.objects.filter(role="student")
        .exclude(id__in=enrolled_ids)
        .order_by("last_name", "first_name")
    )
    if search_query:
        available_students = available_students.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    return render(request, "professor_assign_ta.html", {
        "course": course,
        "current_ta": current_ta_profile.user if current_ta_profile else None,
        "available_students": available_students,
        "search_query": search_query,
    })


@login_required
@role_required("advisor")
def advisor_catalog(request):
    courses = Course.objects.select_related("professor").order_by("code")
    return render(request, "advisor_catalog.html", {"courses": courses})


@login_required
@role_required("advisor")
def advisor_students(request):
    advisees = (
        StudentProfile.objects.filter(advisor=request.user)
        .select_related("user")
        .order_by("user__last_name", "user__first_name")
    )
    return render(request, "advisor_students.html", {"advisees": advisees})


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

    at_risk_count = sum(1 for a in advisees if a.gpa < 2.0)

    return render(request, "advisor.html", {
        "advisees": advisees,
        "pending_requests": pending,
        "assigned_major": assigned_major,
        "pending_changes": pending_changes,
        "pending_drops": pending_drops,
        "at_risk_count": at_risk_count,
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
    total_users = users.count()
    role_percents = {
        role: round(count / total_users * 100) if total_users else 0
        for role, count in role_counts.items()
    }
    audit_log = AuditLog.objects.all()[:20]
    return render(request, "sysadmin.html", {
        "users": users,
        "majors": majors,
        "role_counts": role_counts,
        "role_percents": role_percents,
        "audit_log": audit_log,
    })


@login_required
@role_required("sysadmin")
def audit_log_view(request):
    filter_type = request.GET.get("filter", "all")
    qs = AuditLog.objects.all()
    if filter_type != "all":
        qs = qs.filter(event_type__istartswith=filter_type)
    logs = qs[:200]
    return render(request, "audit_log.html", {
        "audit_log": logs,
        "active_filter": filter_type,
    })


@login_required
@role_required("sysadmin")
def database_browser(request):
    from accounts.models import User

    LIMIT = 100
    TABLE_NAMES = [
        "User", "Course", "Major", "StudentProfile",
        "Enrollment", "Grade", "TranscriptEntry",
        "RegistrarEnrollmentChange", "TAProfile", "AuditLog",
    ]

    counts = {
        "User": User.objects.count(),
        "Course": Course.objects.count(),
        "Major": Major.objects.count(),
        "StudentProfile": StudentProfile.objects.count(),
        "Enrollment": Enrollment.objects.count(),
        "Grade": Grade.objects.count(),
        "TranscriptEntry": TranscriptEntry.objects.count(),
        "RegistrarEnrollmentChange": RegistrarEnrollmentChange.objects.count(),
        "TAProfile": TAProfile.objects.count(),
        "AuditLog": AuditLog.objects.count(),
    }

    active = request.GET.get("table", "User")
    if active not in TABLE_NAMES:
        active = "User"

    headers, rows = [], []

    if active == "User":
        headers = ["ID", "Username", "Full Name", "Role", "University ID", "Active"]
        rows = [
            (u.id, u.username, u.get_full_name() or "—", u.role, u.university_id or "—", "Yes" if u.is_active else "No")
            for u in User.objects.order_by("id")[:LIMIT]
        ]
    elif active == "Course":
        headers = ["ID", "Code", "Title", "Credits", "Capacity", "Professor"]
        rows = [
            (c.id, c.code, c.title, c.credits, c.capacity, c.professor.username if c.professor else "—")
            for c in Course.objects.select_related("professor").order_by("id")[:LIMIT]
        ]
    elif active == "Major":
        headers = ["ID", "Name", "Advisor"]
        rows = [
            (m.id, m.name, m.advisor.username if m.advisor else "—")
            for m in Major.objects.select_related("advisor").order_by("id")[:LIMIT]
        ]
    elif active == "StudentProfile":
        headers = ["ID", "Student", "Major", "GPA", "Advisor"]
        rows = [
            (p.id, p.user.username, p.major, p.gpa, p.advisor.username if p.advisor else "—")
            for p in StudentProfile.objects.select_related("user", "advisor").order_by("id")[:LIMIT]
        ]
    elif active == "Enrollment":
        headers = ["ID", "Student", "Course", "Status", "Reviewed By"]
        rows = [
            (e.id, e.student.username, e.course.code, e.status, e.reviewed_by.username if e.reviewed_by else "—")
            for e in Enrollment.objects.select_related("student", "course", "reviewed_by").order_by("id")[:LIMIT]
        ]
    elif active == "Grade":
        headers = ["ID", "Student", "Course", "Final Grade", "Proposed Grade", "Published"]
        rows = [
            (g.id, g.enrollment.student.username, g.enrollment.course.code,
             g.final_grade or "—", g.proposed_grade or "—", "Yes" if g.published else "No")
            for g in Grade.objects.select_related("enrollment__student", "enrollment__course").order_by("id")[:LIMIT]
        ]
    elif active == "TranscriptEntry":
        headers = ["ID", "Student", "Course Code", "Course Name", "Credits", "Grade", "Added By"]
        rows = [
            (t.id, t.student.username, t.course_code, t.course_name, t.credits, t.grade, t.added_by.username if t.added_by else "—")
            for t in TranscriptEntry.objects.select_related("student", "added_by").order_by("id")[:LIMIT]
        ]
    elif active == "RegistrarEnrollmentChange":
        headers = ["ID", "Student", "Course", "Type", "Status", "Proposed By", "Reviewed By"]
        rows = [
            (r.id, r.student.username, r.course.code, r.change_type, r.status,
             r.proposed_by.username if r.proposed_by else "—",
             r.reviewed_by.username if r.reviewed_by else "—")
            for r in RegistrarEnrollmentChange.objects.select_related("student", "course", "proposed_by", "reviewed_by").order_by("id")[:LIMIT]
        ]
    elif active == "TAProfile":
        headers = ["ID", "TA", "Course"]
        rows = [
            (t.id, t.user.username, t.course.code if t.course else "—")
            for t in TAProfile.objects.select_related("user", "course").order_by("id")[:LIMIT]
        ]
    elif active == "AuditLog":
        headers = ["ID", "Timestamp", "Actor", "Action", "Target", "Event Type", "Color"]
        rows = [
            (a.id, a.timestamp.strftime("%Y-%m-%d %H:%M:%S"), a.actor_label, a.action, a.target, a.event_type, a.color)
            for a in AuditLog.objects.order_by("-timestamp")[:LIMIT]
        ]

    return render(request, "database_browser.html", {
        "table_names": TABLE_NAMES,
        "active": active,
        "counts": counts,
        "headers": headers,
        "rows": rows,
        "limit": LIMIT,
        "total": counts[active],
    })


@login_required
@role_required("sysadmin")
def rbac_policies(request):
    roles = ["student", "ta", "professor", "advisor", "registrar", "sysadmin"]

    policies = [
        ("Enrollment", "Request course enrollment",        {"student", "ta"}),
        ("Enrollment", "View own enrollments",             {"student", "ta"}),
        ("Enrollment", "Approve enrollment requests",      {"advisor"}),
        ("Enrollment", "Deny enrollment requests",         {"advisor"}),
        ("Courses",    "View available courses",           {"student", "ta", "professor", "advisor", "registrar", "sysadmin"}),
        ("Courses",    "View own course roster",           {"professor"}),
        ("Courses",    "Propose grades for course",        {"ta"}),
        ("Courses",    "Create courses",                   {"registrar"}),
        ("Courses",    "Edit courses",                     {"registrar"}),
        ("Courses",    "Delete courses",                   {"registrar"}),
        ("Grades",     "View own grades (published only)", {"student", "ta"}),
        ("Grades",     "Propose grades",                   {"ta"}),
        ("Grades",     "Approve / enter / publish grades", {"professor"}),
        ("Grades",     "Reject TA grade proposals",        {"professor"}),
        ("TA Mgmt",    "Assign TA to own course",          {"professor"}),
        ("Majors",     "Create majors",                    {"registrar"}),
        ("Students",   "View assigned advisees",           {"advisor"}),
        ("Students",   "View pending requests (own advisees)", {"advisor"}),
        ("Users",      "Create user accounts",             {"sysadmin"}),
        ("Users",      "Edit user accounts / roles",       {"sysadmin"}),
        ("Users",      "Delete user accounts",             {"sysadmin"}),
        ("Users",      "View all users",                   {"sysadmin"}),
        ("System",     "Access admin dashboard",           {"sysadmin"}),
        ("System",     "Manage RBAC policies (view)",      {"sysadmin"}),
        ("System",     "View audit logs",                  {"sysadmin"}),
    ]

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
        new_user = form.save()
        _log(
            actor_label=request.user.username,
            action="created user",
            target=f"{new_user.username} [{new_user.role.upper()}]",
            event_type="USER_CREATE · RBAC3 role assigned",
            color="green",
        )
        return redirect("sysadmin_dashboard")
    return render(request, "create_user.html", {"form": form, "majors": majors})


# keep old URL name working
create_student = create_user


@login_required
@role_required("student", "ta")
def my_advisor(request):
    profile = getattr(request.user, "student_profile", None)
    advisor = profile.advisor if profile else None
    major = None
    if advisor:
        try:
            major = advisor.advised_major
        except Exception:
            pass
    return render(request, "my_advisor.html", {
        "advisor": advisor,
        "major": major,
        "profile": profile,
    })


@login_required
@role_required("student", "ta")
def course_catalog(request):
    enrolled_course_ids = set(
        Enrollment.objects.filter(student=request.user)
        .exclude(status="denied")
        .values_list("course_id", flat=True)
    )
    # TAs cannot enroll in their assigned course
    if request.user.role == "ta":
        try:
            ta_profile = request.user.ta_profile
            if ta_profile.course_id:
                enrolled_course_ids.add(ta_profile.course_id)
        except TAProfile.DoesNotExist:
            pass
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
        # Only show published grades to the student/TA
        grade = Grade.objects.filter(enrollment=enrollment, published=True).first()
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
    # Only show published grades
    grade = Grade.objects.filter(enrollment=enrollment, published=True).first()
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

        # Block TAs from enrolling in their own assigned course
        if request.user.role == "ta":
            try:
                ta_profile = request.user.ta_profile
                if ta_profile.course_id == course_id:
                    messages.error(request, f"TAs cannot enroll in the course they are assisting ({course.code}).")
                    return redirect("course_catalog")
            except TAProfile.DoesNotExist:
                pass

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
    if not StudentProfile.objects.filter(user=student, advisor=request.user).exists():
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
    if not StudentProfile.objects.filter(user=enrollment.student, advisor=request.user).exists():
        raise PermissionDenied
    if request.method == "POST":
        _log(
            actor_label=request.user.username,
            action="dropped enrollment for",
            target=f"{enrollment.student.username} → {enrollment.course.code}",
            event_type="ENROLL_DROP",
            color="amber",
        )
        enrollment.delete()
    return redirect("student_detail", student_id=enrollment.student.id)


@login_required
@role_required("advisor")
def approve_drop(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, status="drop_pending")
    if not StudentProfile.objects.filter(user=enrollment.student, advisor=request.user).exists():
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
    _log(
        actor_label=request.user.username,
        action="approved enrollment for",
        target=f"{enrollment.student.username} → {enrollment.course.code}",
        event_type="ENROLL_APPROVE · rbac_check: PASS",
        color="green",
    )
    return redirect("dashboard_router")


@login_required
@role_required("advisor")
def deny_enrollment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    enrollment.status = "denied"
    enrollment.reviewed_by = request.user
    enrollment.save()
    _log(
        actor_label=request.user.username,
        action="denied enrollment for",
        target=f"{enrollment.student.username} → {enrollment.course.code}",
        event_type="ENROLL_DENY · rbac_check: PASS",
        color="red",
    )
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
    denied = Enrollment.objects.filter(student=student, status="denied").select_related("course__professor")
    pending_changes = (
        RegistrarEnrollmentChange.objects.filter(student=student, status="pending")
        .select_related("course", "proposed_by")
    )
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
            Enrollment.objects.filter(
                student=change.student, course=change.course, status="denied"
            ).update(status="approved", reviewed_by=request.user)
        elif change.change_type == "remove":
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
        _log(
            actor_label=request.user.username,
            action="edited user",
            target=f"{user.username} [{user.role.upper()}]",
            event_type="USER_EDIT",
            color="amber",
        )
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
        _log(
            actor_label=request.user.username,
            action="deleted user",
            target=f"{user.username} [{user.role.upper()}]",
            event_type="USER_DELETE",
            color="red",
        )
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
