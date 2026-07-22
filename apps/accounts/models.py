from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible

from apps.core.models import TimeStampedModel
from apps.media_storage.services import user_signature_upload_path


@deconstructible
class PrivateSignatureStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_SIGNATURE_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_signature_storage = PrivateSignatureStorage()


class SmartRouteUserManager(UserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(username, email, password, **extra_fields)

    def _create_user(self, username=None, email=None, password=None, **extra_fields):
        if not username:
            username = User().generate_internal_username()
        return super()._create_user(username, email, password, **extra_fields)

class Person(TimeStampedModel):
    """Identité civile centrale de SmartRoute."""

    nif = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Facultative lorsque cette information n'est pas encore "
            "disponible, notamment pour un propriétaire."
        ),
    )

    class Meta:
        ordering = ("last_name", "first_name", "id")
        verbose_name = "Personne"
        verbose_name_plural = "Personnes"
        indexes = [
            models.Index(
                fields=("last_name", "first_name"),
                name="person_name_idx",
            )
        ]

    @staticmethod
    def normalize_nif(value: str | None) -> str:
        return "".join(
            char
            for char in str(value or "").strip().upper()
            if char.isalnum()
        )

    @staticmethod
    def normalize_name(value: str | None) -> str:
        return " ".join(str(value or "").strip().split())

    def clean(self):
        super().clean()

        self.first_name = self.normalize_name(self.first_name)
        self.last_name = self.normalize_name(self.last_name)

        if not self.first_name:
            raise ValidationError(
                {"first_name": "Le prénom est obligatoire."}
            )
        if not self.last_name:
            raise ValidationError(
                {"last_name": "Le nom est obligatoire."}
            )

        if self.nif:
            self.nif = self.normalize_nif(self.nif)
            if not self.nif:
                raise ValidationError({"nif": "Le NIF est invalide."})
        else:
            self.nif = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self) -> str:
        return self.full_name or f"Person #{self.pk}"


class User(AbstractUser):
    objects = SmartRouteUserManager()

    """Compte de connexion lié à une identité civile."""

    class AccountType(models.TextChoices):
        PROFESSIONAL = "PROFESSIONAL", "Professionnel"
        PERSONAL = "PERSONAL", "Personnel"

    person = models.ForeignKey(
        "accounts.Person",
        on_delete=models.PROTECT,
        related_name="accounts",
        null=True,
        blank=True,
        help_text=(
            "Peut rester vide uniquement pour un superutilisateur "
            "technique ou temporairement durant une migration."
        ),
    )
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.PROFESSIONAL,
        db_index=True,
    )
    email = models.EmailField(blank=True, default="")
    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_accounts",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("person", "account_type"),
                condition=models.Q(person__isnull=False),
                name="unique_account_type_per_person",
            ),
            models.UniqueConstraint(
                fields=("email",),
                condition=(
                    models.Q(account_type="PROFESSIONAL")
                    & ~models.Q(email="")
                ),
                name="unique_professional_email",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account_type", "is_active"),
                name="account_type_active_idx",
            )
        ]

    def generate_internal_username(self) -> str:
        prefix = (
            "pro"
            if self.account_type == self.AccountType.PROFESSIONAL
            else "per"
        )
        return f"{prefix}_{uuid.uuid4().hex}"

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower() if self.email else ""

        if not self.is_superuser and self.person_id is None:
            raise ValidationError(
                {
                    "person": (
                        "Une personne est obligatoire pour un compte "
                        "non technique."
                    )
                }
            )

        if (
            self.account_type == self.AccountType.PROFESSIONAL
            and not self.email
        ):
            raise ValidationError(
                {
                    "email": (
                        "Une adresse email est obligatoire pour un "
                        "compte professionnel."
                    )
                }
            )

        if (
            self.account_type == self.AccountType.PERSONAL
            and self.email
        ):
            raise ValidationError(
                {
                    "email": (
                        "Un compte personnel ne doit pas utiliser "
                        "un email de connexion."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.generate_internal_username()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_professional_account(self) -> bool:
        return self.account_type == self.AccountType.PROFESSIONAL

    @property
    def is_personal_account(self) -> bool:
        return self.account_type == self.AccountType.PERSONAL

    @property
    def full_name(self) -> str:
        return (
            self.person.full_name
            if self.person_id
            else self.get_full_name().strip()
        )

    @property
    def birth_date(self):
        return self.person.birth_date if self.person_id else None

    def __str__(self) -> str:
        identity = self.person.full_name if self.person_id else self.username
        return f"{identity} ({self.get_account_type_display()})"


class AgentProfile(TimeStampedModel):
    """Données métier d'un compte professionnel."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        AGENT_TERRAIN = "AGENT_TERRAIN", "Agent de terrain"
        AGENT_SAISIE = "AGENT_SAISIE", "Agent de saisie"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_profile",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        db_index=True,
    )
    badge_number = models.CharField(max_length=40, unique=True)
    post = models.CharField(max_length=120, blank=True, default="")
    precinct = models.CharField(max_length=120, blank=True, default="")
    signature_file = models.ImageField(
        upload_to=user_signature_upload_path,
        storage=private_signature_storage,
        blank=True,
        null=True,
    )
    signature_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    signature_updated_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Profil agent"
        verbose_name_plural = "Profils agents"
        indexes = [
            models.Index(
                fields=("role", "is_active"),
                name="agent_role_active_idx",
            ),
            models.Index(
                fields=("precinct",),
                name="agent_precinct_idx",
            ),
        ]

    @staticmethod
    def normalize_text(value: str | None) -> str:
        return " ".join(str(value or "").strip().split())

    def clean(self):
        super().clean()

        self.badge_number = self.normalize_text(
            self.badge_number
        ).upper()
        self.post = self.normalize_text(self.post)
        self.precinct = self.normalize_text(self.precinct)

        if not self.badge_number:
            raise ValidationError(
                {"badge_number": "Le numéro de badge est obligatoire."}
            )

        if (
            self.user_id
            and self.user.account_type
            != User.AccountType.PROFESSIONAL
        ):
            raise ValidationError(
                {
                    "user": (
                        "Un profil agent doit être lié à un compte "
                        "professionnel."
                    )
                }
            )

        if self.user_id and not self.user.is_active and self.is_active:
            raise ValidationError(
                {
                    "is_active": (
                        "Un profil actif ne peut pas être lié à un "
                        "compte utilisateur inactif."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def person(self):
        return self.user.person if self.user_id else None

    @property
    def full_name(self) -> str:
        return (
            self.user.person.full_name
            if self.user_id and self.user.person_id
            else ""
        )

    @property
    def birth_date(self):
        return (
            self.user.person.birth_date
            if self.user_id and self.user.person_id
            else None
        )

    def __str__(self) -> str:
        return f"{self.badge_number} - {self.get_role_display()}"
