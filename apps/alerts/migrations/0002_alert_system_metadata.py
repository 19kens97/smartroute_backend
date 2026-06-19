import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("alerts", "0001_initial"),
        ("vehicles", "0003_vehicle_registration_valid_until"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="alerts", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(model_name="alert", name="source", field=models.CharField(choices=[("MANUAL", "MANUAL"), ("SYSTEM", "SYSTEM")], default="MANUAL", max_length=20)),
        migrations.AddField(model_name="alert", name="subject_nif", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="alert", name="system_reasons", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="alert", name="control_period_start", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="alert", name="control_period_end", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="alert", name="deduplication_key", field=models.CharField(blank=True, max_length=160, null=True, unique=True)),
    ]