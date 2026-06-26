from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("gemini", "0002_geminiscan_vehicle"),
        ("Users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="geminiscan",
            name="agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gemini_scans",
                to="Users.user",
            ),
        ),
    ]
