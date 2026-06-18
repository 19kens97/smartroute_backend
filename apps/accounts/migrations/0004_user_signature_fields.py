import apps.accounts.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_normalize_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="signature_file",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=apps.accounts.models.PrivateSignatureStorage(),
                upload_to=apps.accounts.models.user_signature_upload_path,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="signature_sha256",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="user",
            name="signature_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
