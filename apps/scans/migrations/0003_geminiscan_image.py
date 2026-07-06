from django.db import migrations, models
import apps.media_storage.services


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0002_geminiscan"),
    ]

    operations = [
        migrations.AddField(
            model_name="geminiscan",
            name="image",
            field=models.ImageField(blank=True, upload_to=apps.media_storage.services.scan_upload_path),
        ),
    ]