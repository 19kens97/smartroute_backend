import django.db.models.deletion
import apps.accounts.models
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


def build_user_identities(apps, schema_editor):
    Person = apps.get_model("accounts", "Person")
    User = apps.get_model("accounts", "User")
    AgentProfile = apps.get_model("accounts", "AgentProfile")

    for user in User.objects.all().order_by("id"):
        first_name = str(user.first_name or "").strip()
        last_name = str(user.last_name or "").strip()
        if not first_name and not last_name:
            first_name, last_name = split_name(user.username)

        nif = normalize_nif(getattr(user, "nif", ""))
        person = None
        if nif:
            person = Person.objects.filter(nif=nif).first()
        if person is None:
            person = Person.objects.create(
                nif=nif,
                first_name=first_name or "Inconnu",
                last_name=last_name or "Inconnu",
            )

        user.person_id = person.id
        user.account_type = "PROFESSIONAL"
        user.save(update_fields=["person", "account_type"])

        badge_number = str(getattr(user, "badge_number", "") or "").strip()
        if badge_number:
            AgentProfile.objects.get_or_create(
                user=user,
                defaults={
                    "role": getattr(user, "role", "AGENT_SAISIE") or "AGENT_SAISIE",
                    "badge_number": badge_number,
                    "post": getattr(user, "post", "") or "",
                    "precinct": getattr(user, "precinct", "") or "",
                    "signature_file": getattr(user, "signature_file", None),
                    "signature_sha256": getattr(user, "signature_sha256", "") or "",
                    "signature_updated_at": getattr(user, "signature_updated_at", None),
                    "is_active": user.is_active,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_user_signature_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Person",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "nif",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=40,
                        null=True,
                        unique=True,
                    ),
                ),
                ("first_name", models.CharField(max_length=80)),
                ("last_name", models.CharField(max_length=80)),
                ("birth_date", models.DateField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Personne",
                "verbose_name_plural": "Personnes",
                "ordering": ("last_name", "first_name", "id"),
            },
        ),
        migrations.AddField(
            model_name="user",
            name="account_type",
            field=models.CharField(
                choices=[
                    ("PROFESSIONAL", "Professionnel"),
                    ("PERSONAL", "Personnel"),
                ],
                db_index=True,
                default="PROFESSIONAL",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_accounts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="accounts",
                to="accounts.person",
            ),
        ),
        migrations.CreateModel(
            name="AgentProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("ADMIN", "Administrateur"),
                            ("AGENT_TERRAIN", "Agent de terrain"),
                            ("AGENT_SAISIE", "Agent de saisie"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("badge_number", models.CharField(max_length=40, unique=True)),
                ("post", models.CharField(blank=True, default="", max_length=120)),
                ("precinct", models.CharField(blank=True, default="", max_length=120)),
                (
                    "signature_file",
                    models.ImageField(
                        blank=True,
                        null=True,
                        storage=apps.accounts.models.PrivateSignatureStorage(),
                        upload_to=apps.accounts.models.user_signature_upload_path,
                    ),
                ),
                ("signature_sha256", models.CharField(blank=True, default="", max_length=64)),
                ("signature_updated_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Profil agent",
                "verbose_name_plural": "Profils agents",
            },
        ),
        migrations.AddIndex(
            model_name="person",
            index=models.Index(fields=("last_name", "first_name"), name="person_name_idx"),
        ),
        migrations.AddIndex(
            model_name="agentprofile",
            index=models.Index(fields=("role", "is_active"), name="agent_role_active_idx"),
        ),
        migrations.AddIndex(
            model_name="agentprofile",
            index=models.Index(fields=("precinct",), name="agent_precinct_idx"),
        ),
        migrations.RunPython(build_user_identities, migrations.RunPython.noop),
        migrations.RemoveField(model_name="user", name="badge_number"),
        migrations.RemoveField(model_name="user", name="nif"),
        migrations.RemoveField(model_name="user", name="phone"),
        migrations.RemoveField(model_name="user", name="post"),
        migrations.RemoveField(model_name="user", name="precinct"),
        migrations.RemoveField(model_name="user", name="role"),
        migrations.RemoveField(model_name="user", name="signature_file"),
        migrations.RemoveField(model_name="user", name="signature_sha256"),
        migrations.RemoveField(model_name="user", name="signature_updated_at"),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("person__isnull", False)),
                fields=("person", "account_type"),
                name="unique_account_type_per_person",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("account_type", "PROFESSIONAL"))
                & ~models.Q(("email", "")),
                fields=("email",),
                name="unique_professional_email",
            ),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=("account_type", "is_active"), name="account_type_active_idx"),
        ),
    ]
