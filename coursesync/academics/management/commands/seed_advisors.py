from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from academics.models import Major

User = get_user_model()

ADVISOR_DATA = [
    {
        "username": "advisor.cs",
        "first_name": "Sarah",
        "last_name": "Chen",
        "email": "s.chen@university.edu",
        "major": "Computer Science",
    },
    {
        "username": "advisor.math",
        "first_name": "David",
        "last_name": "Okafor",
        "email": "d.okafor@university.edu",
        "major": "Mathematics",
    },
    {
        "username": "advisor.physics",
        "first_name": "Elena",
        "last_name": "Vasquez",
        "email": "e.vasquez@university.edu",
        "major": "Physics",
    },
    {
        "username": "advisor.english",
        "first_name": "Marcus",
        "last_name": "Webb",
        "email": "m.webb@university.edu",
        "major": "English Literature",
    },
    {
        "username": "advisor.business",
        "first_name": "Priya",
        "last_name": "Sharma",
        "email": "p.sharma@university.edu",
        "major": "Business Administration",
    },
]

DEFAULT_PASSWORD = "advisor123!"


class Command(BaseCommand):
    help = "Creates 5 advisor users each assigned to a field of study"

    def handle(self, *args, **options):
        created_count = 0

        for data in ADVISOR_DATA:
            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    "role": "advisor",
                },
            )
            if created:
                user.set_password(DEFAULT_PASSWORD)
                user.save()
                created_count += 1
                self.stdout.write(f"  Created advisor: {user.get_full_name()} ({user.username})")
            else:
                self.stdout.write(f"  Advisor already exists: {user.username}")

            major, _ = Major.objects.update_or_create(
                name=data["major"],
                defaults={"advisor": user},
            )
            self.stdout.write(f"    → Assigned to major: {major.name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created_count} new advisor(s) created. "
            f"Default password: {DEFAULT_PASSWORD}"
        ))
