from django.db import migrations


def format_nif(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) != 10:
        return None
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9]}"


def normalize_person_nifs(apps, schema_editor):
    Person = apps.get_model("accounts", "Person")
    seen = set()
    for person in Person.objects.all().only("id", "nif").order_by("id"):
        normalized = format_nif(person.nif)
        if normalized and normalized in seen:
            normalized = None
        if normalized:
            seen.add(normalized)
        if person.nif != normalized:
            person.nif = normalized
            person.save(update_fields=["nif"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_alter_user_managers"),
    ]

    operations = [
        migrations.RunPython(normalize_person_nifs, migrations.RunPython.noop),
    ]
