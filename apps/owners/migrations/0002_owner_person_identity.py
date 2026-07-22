import django.db.models.deletion
from django.conf import settings
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


def ensure_system_user(apps):
    Person = apps.get_model("accounts", "Person")
    User = apps.get_model("accounts", "User")
    person, _ = Person.objects.get_or_create(
        nif="SYSTEMOWNER",
        defaults={"first_name": "Systeme", "last_name": "Migration"},
    )
    user, _ = User.objects.get_or_create(
        username="system_migration",
        defaults={
            "person_id": person.id,
            "account_type": "PROFESSIONAL",
            "email": "system.migration@smartroute.local",
            "is_staff": False,
            "is_superuser": False,
            "is_active": False,
        },
    )
    if user.person_id is None:
        user.person_id = person.id
        user.save(update_fields=["person"])
    return user


def populate_owner_people(apps, schema_editor):
    Owner = apps.get_model("owners", "Owner")
    Person = apps.get_model("accounts", "Person")
    system_user = ensure_system_user(apps)

    for owner in Owner.objects.all().order_by("id"):
        nif = normalize_nif(getattr(owner, "national_id", ""))
        person = Person.objects.filter(nif=nif).first() if nif else None
        if person is None:
            first_name, last_name = split_name(getattr(owner, "full_name", ""))
            person = Person.objects.create(
                nif=nif,
                first_name=first_name,
                last_name=last_name,
            )
        owner.person_id = person.id
        owner.created_by_id = owner.created_by_id or system_user.id
        owner.save(update_fields=["person", "created_by"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_person_agentprofile_user_identity"),
        ("owners", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="owner",
            name="person",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owner_record",
                to="accounts.person",
            ),
        ),
        migrations.AddField(
            model_name="owner",
            name="created_by",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="created_owners",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="owner",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.RunPython(populate_owner_people, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="owner",
            name="person",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owner_record",
                to="accounts.person",
            ),
        ),
        migrations.AlterField(
            model_name="owner",
            name="created_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="created_owners",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="owner",
            name="address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="owner",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.RemoveField(model_name="owner", name="full_name"),
        migrations.RemoveField(model_name="owner", name="national_id"),
        migrations.AlterModelOptions(
            name="owner",
            options={
                "ordering": ("person__last_name", "person__first_name", "id"),
                "verbose_name": "Proprietaire",
                "verbose_name_plural": "Proprietaires",
            },
        ),
        migrations.AddIndex(
            model_name="owner",
            index=models.Index(fields=("is_active",), name="owner_active_idx"),
        ),
    ]
