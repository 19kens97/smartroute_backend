# Generated for SmartRoute Lot 4B private document storage

import apps.documents.models
import apps.media_storage.services
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_alter_document_options_document_description_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="file",
            field=models.FileField(
                storage=apps.documents.models.PrivateDocumentStorage(),
                upload_to=apps.media_storage.services.document_upload_path,
            ),
        ),
    ]
