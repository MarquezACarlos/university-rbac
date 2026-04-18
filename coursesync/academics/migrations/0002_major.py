from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Major",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                (
                    "advisor",
                    models.OneToOneField(
                        blank=True,
                        limit_choices_to={"role": "advisor"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="advised_major",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
