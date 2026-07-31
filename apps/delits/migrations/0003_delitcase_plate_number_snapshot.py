# Generated manually for SmartRoute delit plate context.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("delits", "0002_seed_demo_delit_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="delitcase",
            name="plate_number_snapshot",
            field=models.CharField(blank=True, db_index=True, default="", max_length=20),
        ),
    ]
