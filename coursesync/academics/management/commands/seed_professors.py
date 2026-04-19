from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from academics.models import Course

User = get_user_model()

PROFESSOR_DATA = [
    {
        "username": "prof.miller",
        "first_name": "James",
        "last_name": "Miller",
        "email": "j.miller@university.edu",
        "courses": ["CS 1010", "CS 2110"],
    },
    {
        "username": "prof.nguyen",
        "first_name": "Linh",
        "last_name": "Nguyen",
        "email": "l.nguyen@university.edu",
        "courses": ["CS 3200", "CS 4280"],
    },
    {
        "username": "prof.okonkwo",
        "first_name": "Chidi",
        "last_name": "Okonkwo",
        "email": "c.okonkwo@university.edu",
        "courses": ["CS 3410", "CS 4410"],
    },
    {
        "username": "prof.patel",
        "first_name": "Ananya",
        "last_name": "Patel",
        "email": "a.patel@university.edu",
        "courses": ["CS 4780", "CS 4820"],
    },
    {
        "username": "prof.torres",
        "first_name": "Roberto",
        "last_name": "Torres",
        "email": "r.torres@university.edu",
        "courses": ["CS 4850"],
    },
    {
        "username": "prof.kim",
        "first_name": "Soo-Jin",
        "last_name": "Kim",
        "email": "s.kim@university.edu",
        "courses": ["MATH 1910", "MATH 2940", "MATH 3110"],
    },
    {
        "username": "prof.hassan",
        "first_name": "Fatima",
        "last_name": "Hassan",
        "email": "f.hassan@university.edu",
        "courses": ["PHYS 2210"],
    },
    {
        "username": "prof.brennan",
        "first_name": "Colin",
        "last_name": "Brennan",
        "email": "c.brennan@university.edu",
        "courses": ["ENGL 1170", "BUS 2400"],
    },
]

DEFAULT_PASSWORD = "professor123!"


class Command(BaseCommand):
    help = "Creates professor users and assigns them to courses"

    def handle(self, *args, **options):
        created_count = 0

        for data in PROFESSOR_DATA:
            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    "role": "professor",
                },
            )
            if created:
                user.set_password(DEFAULT_PASSWORD)
                user.save()
                created_count += 1
                self.stdout.write(f"  Created professor: {user.get_full_name()} ({user.username})")
            else:
                self.stdout.write(f"  Professor already exists: {user.username}")

            for code in data["courses"]:
                updated = Course.objects.filter(code=code).update(professor=user)
                if updated:
                    self.stdout.write(f"    → Assigned to {code}")
                else:
                    self.stdout.write(self.style.WARNING(f"    → Course not found: {code} (run seed_courses first)"))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created_count} new professor(s) created. "
            f"Default password: {DEFAULT_PASSWORD}"
        ))
