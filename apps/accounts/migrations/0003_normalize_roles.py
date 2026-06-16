from django.db import migrations, models


def convert_supervisors_to_admins(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="SUPERVISEUR").update(role="ADMIN")


def convert_admins_to_supervisors(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(username="superviseur", role="ADMIN").update(role="SUPERVISEUR")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_profile_fields"),
    ]

    operations = [
        migrations.RunPython(convert_supervisors_to_admins, convert_admins_to_supervisors),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "ADMIN"),
                    ("AGENT_TERRAIN", "AGENT_TERRAIN"),
                    ("AGENT_SAISIE", "AGENT_SAISIE"),
                ],
                default="AGENT_SAISIE",
                max_length=20,
            ),
        ),
    ]
