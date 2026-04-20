from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def mark_existing_grades_published(apps, schema_editor):
    Grade = apps.get_model("academics", "Grade")
    Grade.objects.filter(final_grade__gt="").update(published=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("academics", "0006_taprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="grade",
            name="proposed_grade",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="grade",
            name="proposed_by",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"role": "ta"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposed_grades",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="grade",
            name="published",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_grades_published, migrations.RunPython.noop),
    ]
