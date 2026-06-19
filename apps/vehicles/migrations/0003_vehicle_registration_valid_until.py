from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vehicles", "0002_vehicle_administrative_fields")]
    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="registration_valid_until",
            field=models.DateField(blank=True, null=True),
        ),
    ]