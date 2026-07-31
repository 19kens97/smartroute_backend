from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("delits", "0004_clean_demo_delit_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="delitcase",
            name="dcpj_status",
            field=models.CharField(choices=[("NOT_SENT", "Non transmis"), ("SENT", "Transmis"), ("ACKNOWLEDGED", "Accuse reception"), ("FAILED", "Echec transmission")], db_index=True, default="NOT_SENT", max_length=20),
        ),
        migrations.AddField(
            model_name="delitcase",
            name="dcpj_reference",
            field=models.CharField(blank=True, db_index=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="delitcase",
            name="dcpj_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="delitcase",
            name="dcpj_last_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="delitcase",
            name="dcpj_payload_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="delitcase",
            name="dcpj_response_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]