import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from academics.models import Course, Enrollment, Grade, StudentProfile

User = get_user_model()

COURSES = [
    ("CS 1010", "Introduction to Programming",         "Fundamentals of programming using Python.",                        3),
    ("CS 2110", "Data Structures",                     "Arrays, linked lists, trees, graphs, and hash tables.",            3),
    ("CS 3200", "Database Systems",                    "Relational model, SQL, normalization, and transactions.",          3),
    ("CS 3410", "Computer Organization",               "Processor design, memory hierarchy, and assembly language.",       3),
    ("CS 4280", "Programming Languages",               "Type systems, interpreters, and language design.",                 3),
    ("CS 4410", "Operating Systems",                   "Processes, threads, scheduling, and memory management.",           3),
    ("CS 4780", "Machine Learning",                    "Supervised and unsupervised learning algorithms.",                 3),
    ("CS 4820", "Algorithms",                          "Algorithm design, complexity theory, and NP-completeness.",        4),
    ("CS 4850", "Computer Networks",                   "Protocols, routing, and network security.",                        3),
    ("MATH 1910", "Calculus I",                        "Limits, derivatives, and integrals of single-variable functions.", 4),
    ("MATH 2940", "Linear Algebra",                    "Vectors, matrices, eigenvalues, and linear transformations.",      3),
    ("MATH 3110", "Probability & Statistics",          "Probability theory, distributions, and statistical inference.",    3),
    ("PHYS 2210", "Mechanics",                         "Newtonian mechanics, energy, and momentum.",                       4),
    ("ENGL 1170", "Academic Writing",                  "Composition, argumentation, and research writing.",                3),
    ("BUS 2400",  "Principles of Management",          "Organizational behavior, planning, and leadership.",               3),
]

# Weighted grade pool — realistic college distribution
GRADE_POOL = (
    ["A"]  * 20 +
    ["A-"] * 15 +
    ["B+"] * 12 +
    ["B"]  * 18 +
    ["B-"] * 12 +
    ["C+"] * 8  +
    ["C"]  * 8  +
    ["C-"] * 4  +
    ["D"]  * 2  +
    ["F"]  * 1
)

GRADE_POINTS = {
    "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0,
    "F": 0.0,
}


def calculate_gpa(graded_enrollments):
    total_points = Decimal("0")
    total_credits = 0
    for enrollment, letter in graded_enrollments:
        credits = enrollment.course.credits
        points = Decimal(str(GRADE_POINTS.get(letter, 0.0)))
        total_points += points * credits
        total_credits += credits
    if total_credits == 0:
        return Decimal("0.00")
    return (total_points / total_credits).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = "Seeds courses and assigns random graded enrollments to students"

    def handle(self, *args, **options):
        professors = list(User.objects.filter(role="professor"))

        # --- Create courses ---
        self.stdout.write("Creating courses...")
        created_courses = []
        for code, title, description, credits in COURSES:
            professor = random.choice(professors) if professors else None
            course, created = Course.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "description": description,
                    "credits": credits,
                    "capacity": random.randint(20, 40),
                    "professor": professor,
                },
            )
            created_courses.append(course)
            status = "created" if created else "exists"
            self.stdout.write(f"  [{status}] {course.code} — {course.title}")

        all_courses = list(Course.objects.all())

        # --- Assign enrollments to students ---
        students = User.objects.filter(role="student")
        if not students.exists():
            self.stdout.write(self.style.WARNING("No student accounts found. Create some students first."))
            return

        self.stdout.write(f"\nAssigning enrollments to {students.count()} student(s)...")

        for student in students:
            existing_approved = set(
                Enrollment.objects.filter(student=student, status="approved")
                .values_list("course_id", flat=True)
            )
            available = [c for c in all_courses if c.id not in existing_approved]
            if not available:
                self.stdout.write(f"  {student.username}: already fully enrolled, skipping")
                continue

            sample_size = min(random.randint(3, 5), len(available))
            chosen = random.sample(available, sample_size)

            graded = []
            for course in chosen:
                enrollment, _ = Enrollment.objects.get_or_create(
                    student=student,
                    course=course,
                    defaults={"status": "approved"},
                )
                enrollment.status = "approved"
                enrollment.save()

                letter = random.choice(GRADE_POOL)
                numeric = Decimal(str(GRADE_POINTS[letter]))
                grade, _ = Grade.objects.update_or_create(
                    enrollment=enrollment,
                    defaults={"final_grade": letter, "numeric_grade": numeric},
                )
                graded.append((enrollment, letter))
                self.stdout.write(f"    {course.code}: {letter}")

            # Recalculate GPA across all graded enrollments for this student
            all_graded = [
                (e, g.final_grade)
                for e in Enrollment.objects.filter(student=student, status="approved").select_related("course")
                for g in [Grade.objects.filter(enrollment=e).first()]
                if g
            ]
            gpa = calculate_gpa(all_graded)

            try:
                profile = student.student_profile
                profile.gpa = gpa
                profile.save()
                self.stdout.write(f"  {student.username} → GPA updated to {gpa}")
            except StudentProfile.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  {student.username}: no StudentProfile found, skipping GPA update"))

        self.stdout.write(self.style.SUCCESS("\nDone. Run again to add more enrollments."))
