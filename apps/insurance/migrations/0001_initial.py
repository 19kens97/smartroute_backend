from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("vehicles", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsurancePolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("insurer", models.CharField(max_length=150)),
                ("policy_number", models.CharField(max_length=80, unique=True)),
                ("valid_until", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[("VALID", "Valide"), ("EXPIRED", "Expirée"), ("SUSPENDED", "Suspendue")],
                        default="VALID",
                        max_length=20,
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_policies",
                        to="vehicles.vehicle",
                    ),
                ),
            ],
        ),
    ]

