from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="GeminiScan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plate_number", models.CharField(max_length=16)),
                ("model_used", models.CharField(max_length=120)),
                ("scanned_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-scanned_at"],
            },
        ),
    ]
