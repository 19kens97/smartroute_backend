from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import Person
from apps.core.models import TimeStampedModel


class Driver(TimeStampedModel):
    """
    Dossier conducteur lié à l'identité civile centrale Person.

    NIF, nom, prénom et date de naissance ne sont pas dupliqués.
    """

    class Sex(models.TextChoices):
        MALE = "M", "Masculin"
        FEMALE = "F", "Féminin"

    person = models.OneToOneField(
        Person,
        on_delete=models.PROTECT,
        related_name="driver_record",
    )
    dossier_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    sex = models.CharField(
        max_length=1,
        choices=Sex.choices,
        blank=True,
        default="",
    )
    blood_group = models.CharField(
        max_length=5,
        blank=True,
        default="",
    )
    license_type = models.CharField(max_length=80)
    issue_place = models.CharField(
        max_length=120,
        blank=True,
        default="",
    )
    issue_date = models.DateField(null=True, blank=True)
    expires_at = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta:
        ordering = (
            "person__last_name",
            "person__first_name",
            "dossier_number",
        )
        verbose_name = "Dossier conducteur"
        verbose_name_plural = "Dossiers conducteurs"

    @staticmethod
    def normalize_dossier_number(value: str | None) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def normalize_text(value: str | None) -> str:
        return " ".join(str(value or "").strip().split())

    def clean(self):
        super().clean()

        self.dossier_number = self.normalize_dossier_number(
            self.dossier_number
        )
        self.address = self.normalize_text(self.address)
        self.blood_group = self.normalize_text(
            self.blood_group
        ).upper()
        self.license_type = self.normalize_text(self.license_type)
        self.issue_place = self.normalize_text(self.issue_place)

        if not self.dossier_number:
            raise ValidationError(
                {
                    "dossier_number": (
                        "Le numéro de dossier est obligatoire."
                    )
                }
            )

        if not self.license_type:
            raise ValidationError(
                {
                    "license_type": (
                        "Le type de permis est obligatoire."
                    )
                }
            )

        if (
            self.issue_date
            and self.expires_at
            and self.expires_at < self.issue_date
        ):
            raise ValidationError(
                {
                    "expires_at": (
                        "La date d'expiration ne peut pas être "
                        "antérieure à la date de délivrance."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def nif(self):
        return self.person.nif

    @property
    def full_name(self) -> str:
        return self.person.full_name

    @property
    def first_name(self) -> str:
        return self.person.first_name

    @property
    def last_name(self) -> str:
        return self.person.last_name

    @property
    def birth_date(self):
        return self.person.birth_date

    def __str__(self) -> str:
        return f"{self.full_name} ({self.dossier_number})"
