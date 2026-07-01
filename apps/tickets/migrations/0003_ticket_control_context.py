# Generated manually for ticket control context.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0002_ticketproof_evidence_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="occurred_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="location_label",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ticket",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
    ]
