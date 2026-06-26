from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("Vehicles", "0003_vehicle_owner"),
        ("gemini", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="geminiscan",
            name="vehicle",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gemini_scans",
                to="Vehicles.vehicle",
            ),
        ),
    ]
