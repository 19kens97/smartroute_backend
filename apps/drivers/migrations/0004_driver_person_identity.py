import django.db.models.deletion
from django.db import migrations, models


def split_name(full_name):
    parts = str(full_name or "").strip().split()
    if not parts:
        return "Inconnu", "Inconnu"
    if len(parts) == 1:
        return parts[0], "Inconnu"
    return parts[0], " ".join(parts[1:])


def normalize_nif(value):
    normalized = "".join(
        char for char in str(value or "").strip().upper() if char.isalnum()
    )
    return normalized or None


def populate_driver_people(apps, schema_editor):
    Driver = apps.get_model("drivers", "Driver")
    Person = apps.get_model("accounts", "Person")

    for driver in Driver.objects.all().order_by("id"):
        nif = normalize_nif(getattr(driver, "nif", ""))
        person = Person.objects.filter(nif=nif).first() if nif else None
        if person is None:
            first_name, last_name = split_name(getattr(driver, "full_name", ""))
            person = Person.objects.create(
                nif=nif,
                first_name=first_name,
                last_name=last_name,
                birth_date=getattr(driver, "birth_date", None),
            )
        driver.person_id = person.id
        driver.save(update_fields=["person"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_person_agentprofile_user_identity"),
        ("drivers", "0003_alter_driver_nif"),
    ]

    operations = [
        migrations.AddField(
            model_name="driver",
            name="person",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="driver_record",
                to="accounts.person",
            ),
        ),
        migrations.RunPython(populate_driver_people, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="driver",
            name="person",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="driver_record",
                to="accounts.person",
            ),
        ),
        migrations.AlterField(
            model_name="driver",
            name="address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="driver",
            name="blood_group",
            field=models.CharField(blank=True, default="", max_length=5),
        ),
        migrations.AlterField(
            model_name="driver",
            name="dossier_number",
            field=models.CharField(db_index=True, max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name="driver",
            name="expires_at",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="driver",
            name="issue_place",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AlterField(
            model_name="driver",
            name="sex",
            field=models.CharField(
                blank=True,
                choices=[("M", "Masculin"), ("F", "Feminin")],
                default="",
                max_length=1,
            ),
        ),
        migrations.RemoveField(model_name="driver", name="birth_date"),
        migrations.RemoveField(model_name="driver", name="full_name"),
        migrations.RemoveField(model_name="driver", name="nif"),
        migrations.AlterModelOptions(
            name="driver",
            options={
                "ordering": ("person__last_name", "person__first_name", "dossier_number"),
                "verbose_name": "Dossier conducteur",
                "verbose_name_plural": "Dossiers conducteurs",
            },
        ),
    ]
