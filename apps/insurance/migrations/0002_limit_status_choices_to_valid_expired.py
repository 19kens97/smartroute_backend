from django.db import migrations, models


def convert_suspended_to_expired(apps, schema_editor):
    InsurancePolicy = apps.get_model("insurance", "InsurancePolicy")
    InsurancePolicy.objects.filter(status="SUSPENDED").update(status="EXPIRED")


class Migration(migrations.Migration):

    dependencies = [
        ("insurance", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(convert_suspended_to_expired, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="insurancepolicy",
            name="status",
            field=models.CharField(
                choices=[("VALID", "Valide"), ("EXPIRED", "Expiree")],
                default="VALID",
                max_length=20,
            ),
        ),
    ]