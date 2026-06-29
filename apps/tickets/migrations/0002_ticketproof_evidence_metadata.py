# Generated manually for ticket proof evidence metadata.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketproof",
            name="duration_seconds",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticketproof",
            name="evidence_type",
            field=models.CharField(choices=[("PHOTO", "Photo"), ("VIDEO", "Video"), ("AUDIO", "Audio")], default="PHOTO", max_length=10),
        ),
        migrations.AddField(
            model_name="ticketproof",
            name="mime_type",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
