from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0003_registrarenrollmentchange"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TranscriptEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("course_code", models.CharField(max_length=20)),
                ("course_name", models.CharField(max_length=200)),
                ("credits", models.PositiveIntegerField(default=3)),
                ("grade", models.CharField(max_length=2, choices=[
                    ("A", "A"), ("A-", "A-"), ("B+", "B+"), ("B", "B"), ("B-", "B-"),
                    ("C+", "C+"), ("C", "C"), ("C-", "C-"), ("D+", "D+"), ("D", "D"), ("F", "F"),
                ])),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                (
                    "added_by",
                    models.ForeignKey(
                        limit_choices_to={"role": "registrar"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="added_transcript_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transcript_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
