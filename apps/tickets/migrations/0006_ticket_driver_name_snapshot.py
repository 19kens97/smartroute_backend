from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0005_ticketproof_checksum_sha256_ticketproof_created_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="driver_name_snapshot",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]