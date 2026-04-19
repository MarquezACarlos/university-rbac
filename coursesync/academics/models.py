from django.conf import settings
from django.db import models


User = settings.AUTH_USER_MODEL


class Major(models.Model):
    name = models.CharField(max_length=100, unique=True)
    advisor = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advised_major",
        limit_choices_to={"role": "advisor"},
    )

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    major = models.CharField(max_length=100)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    advisor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advisees",
        limit_choices_to={"role": "advisor"},
    )

    def __str__(self):
        return f"{self.user.get_full_name()} Profile"


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    credits = models.PositiveIntegerField(default=3)
    capacity = models.PositiveIntegerField(default=30)
    professor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses_taught",
        limit_choices_to={"role": "professor"},
    )

    def __str__(self):
        return f"{self.code} - {self.title}"


class Enrollment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        DROP_PENDING = "drop_pending", "Drop Pending"

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": "student"},
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    proposed_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_enrollments",
    )

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student} -> {self.course} ({self.status})"


class RegistrarEnrollmentChange(models.Model):
    class ChangeType(models.TextChoices):
        ADD = "add", "Add"
        REMOVE = "remove", "Remove"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Advisor Review"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="registrar_changes",
        limit_choices_to={"role": "student"},
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="registrar_changes")
    change_type = models.CharField(max_length=10, choices=ChangeType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    proposed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="proposed_changes",
        limit_choices_to={"role": "registrar"},
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_changes",
        limit_choices_to={"role": "advisor"},
    )
    proposed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        unique_together = ("student", "course", "change_type", "status")

    def __str__(self):
        return f"{self.change_type.upper()} {self.course.code} for {self.student} [{self.status}]"


GRADE_CHOICES = [
    ("A", "A"), ("A-", "A-"),
    ("B+", "B+"), ("B", "B"), ("B-", "B-"),
    ("C+", "C+"), ("C", "C"), ("C-", "C-"),
    ("D+", "D+"), ("D", "D"),
    ("F", "F"),
]


class TranscriptEntry(models.Model):
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="transcript_entries",
        limit_choices_to={"role": "student"},
    )
    course_code = models.CharField(max_length=20)
    course_name = models.CharField(max_length=200)
    credits = models.PositiveIntegerField(default=3)
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES)
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="added_transcript_entries",
        limit_choices_to={"role": "registrar"},
    )
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.course_code} — {self.student} ({self.grade})"


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField()

    def __str__(self):
        return self.title


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="submissions",
        limit_choices_to={"role": "student"},
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to="submissions/", null=True, blank=True)
    text = models.TextField(blank=True)

    class Meta:
        unique_together = ("assignment", "student")


class Grade(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name="grade")
    final_grade = models.CharField(max_length=2, blank=True)
    numeric_grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.enrollment} - {self.final_grade or 'N/A'}"