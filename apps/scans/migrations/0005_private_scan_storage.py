# Generated for SmartRoute Lot 4B private scan storage

import apps.media_storage.services
import apps.scans.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0004_alter_geminiscan_created_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="geminiscan",
            name="image",
            field=models.ImageField(
                blank=True,
                storage=apps.scans.models.PrivateScanStorage(),
                upload_to=apps.media_storage.services.scan_upload_path,
            ),
        ),
    ]
