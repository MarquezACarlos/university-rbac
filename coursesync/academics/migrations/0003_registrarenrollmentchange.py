from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0002_major"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrarEnrollmentChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("change_type", models.CharField(choices=[("add", "Add"), ("remove", "Remove")], max_length=10)),
                ("status", models.CharField(
                    choices=[("pending", "Pending Advisor Review"), ("approved", "Approved"), ("denied", "Denied")],
                    default="pending", max_length=20,
                )),
                ("proposed_at", models.DateTimeField(auto_now_add=True)),
                ("note", models.TextField(blank=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrar_changes",
                        to="academics.course",
                    ),
                ),
                (
                    "proposed_by",
                    models.ForeignKey(
                        limit_choices_to={"role": "registrar"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proposed_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"role": "advisor"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrar_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("student", "course", "change_type", "status")},
            },
        ),
    ]
