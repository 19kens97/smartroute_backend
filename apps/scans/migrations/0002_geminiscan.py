# Generated manually for GeminiScan model

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GeminiScan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("plate_number", models.CharField(blank=True, max_length=20)),
                ("source", models.CharField(default="MOBILE_GEMINI", max_length=30)),
                ("model_used", models.CharField(blank=True, max_length=80)),
                ("raw_response", models.TextField(blank=True)),
                ("plate_detected", models.BooleanField(default=False)),
                (
                    "vehicle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gemini_scans",
                        to="vehicles.vehicle",
                    ),
                ),
                (
                    "agent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("scanned_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
