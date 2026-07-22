from django.db import migrations, models


def populate_alert_categories(apps, schema_editor):
    Alert = apps.get_model("alerts", "Alert")
    Alert.objects.filter(source="SYSTEM").update(category="AUTOMATIC")
    Alert.objects.exclude(source="SYSTEM").update(category="ADMINISTRATIVE")


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0005_alertevidence_checksum_sha256"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="category",
            field=models.CharField(
                choices=[
                    ("AUTOMATIC", "Automatique"),
                    ("FIELD_REPORT", "Signalement terrain"),
                    ("ADMINISTRATIVE", "Administrative"),
                ],
                db_index=True,
                max_length=24,
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_alert_categories,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="alert",
            name="category",
            field=models.CharField(
                choices=[
                    ("AUTOMATIC", "Automatique"),
                    ("FIELD_REPORT", "Signalement terrain"),
                    ("ADMINISTRATIVE", "Administrative"),
                ],
                db_index=True,
                max_length=24,
            ),
        ),
    ]
