from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0007_grade_proposal_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_label", models.CharField(max_length=150)),
                ("action", models.CharField(max_length=200)),
                ("target", models.CharField(max_length=200)),
                ("event_type", models.CharField(max_length=150)),
                ("color", models.CharField(default="green", max_length=10)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
    ]
