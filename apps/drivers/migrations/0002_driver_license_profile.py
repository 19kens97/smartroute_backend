from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="driver",
            old_name="license_number",
            new_name="dossier_number",
        ),
        migrations.AddField(
            model_name="driver",
            name="nif",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="driver",
            name="address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="driver",
            name="birth_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="driver",
            name="sex",
            field=models.CharField(blank=True, choices=[("M", "Masculin"), ("F", "Feminin")], max_length=1),
        ),
        migrations.AddField(
            model_name="driver",
            name="blood_group",
            field=models.CharField(blank=True, max_length=5),
        ),
        migrations.AddField(
            model_name="driver",
            name="license_type",
            field=models.CharField(default="B", max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="driver",
            name="issue_place",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="driver",
            name="issue_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="driver",
            name="expires_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RemoveField(
            model_name="driver",
            name="phone",
        ),
    ]
