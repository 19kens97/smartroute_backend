from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.accounts.models import Person
from apps.core.models import TimeStampedModel


class Owner(TimeStampedModel):
    """
    Profil métier d'un propriétaire.

    Les informations civiles (NIF, prénom, nom, date de naissance) restent
    exclusivement dans Person.
    """

    person = models.OneToOneField(
        Person,
        on_delete=models.PROTECT,
        related_name="owner_record",
    )
    phone = models.CharField(max_length=30, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_owners",
    )

    class Meta:
        ordering = ("person__last_name", "person__first_name", "id")
        verbose_name = "Propriétaire"
        verbose_name_plural = "Propriétaires"
        indexes = [
            models.Index(
                fields=("is_active",),
                name="owner_active_idx",
            ),
        ]

    @staticmethod
    def normalize_text(value):
        return " ".join(str(value or "").strip().split())

    def clean(self):
        super().clean()
        self.phone = self.normalize_text(self.phone)
        self.address = self.normalize_text(self.address)

        if not self.person_id:
            raise ValidationError(
                {"person": "Une personne est obligatoire."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def nif(self):
        return self.person.nif

    @property
    def first_name(self):
        return self.person.first_name

    @property
    def last_name(self):
        return self.person.last_name

    @property
    def full_name(self):
        return self.person.full_name

    @property
    def birth_date(self):
        return self.person.birth_date

    def __str__(self):
        return self.full_name


class VehicleOwnership(TimeStampedModel):
    """Historique de propriété d'un véhicule."""

    class OwnershipType(models.TextChoices):
        FULL_OWNER = "FULL_OWNER", "Propriétaire principal"
        CO_OWNER = "CO_OWNER", "Copropriétaire"
        LEGAL_CUSTODIAN = "LEGAL_CUSTODIAN", "Détenteur légal"
        COMPANY_VEHICLE = "COMPANY_VEHICLE", "Véhicule d'entreprise"
        GOVERNMENT_VEHICLE = "GOVERNMENT_VEHICLE", "Véhicule administratif"
        TEMPORARY_HOLDER = "TEMPORARY_HOLDER", "Détenteur temporaire"

    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.PROTECT,
        related_name="ownerships",
    )
    owner = models.ForeignKey(
        Owner,
        on_delete=models.PROTECT,
        related_name="vehicle_ownerships",
    )
    ownership_type = models.CharField(
        max_length=30,
        choices=OwnershipType.choices,
        default=OwnershipType.FULL_OWNER,
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    source_document_reference = models.CharField(
        max_length=120,
        blank=True,
        default="",
    )
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_vehicle_ownerships",
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ended_vehicle_ownerships",
    )

    class Meta:
        ordering = ("-is_current", "-start_date", "-id")
        verbose_name = "Propriété de véhicule"
        verbose_name_plural = "Propriétés de véhicules"
        constraints = [
            models.UniqueConstraint(
                fields=("vehicle",),
                condition=Q(is_current=True),
                name="unique_current_owner_per_vehicle",
            ),
            models.CheckConstraint(
                condition=(
                    Q(end_date__isnull=True)
                    | Q(end_date__gte=models.F("start_date"))
                ),
                name="ownership_end_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_current=True, end_date__isnull=True)
                    | Q(is_current=False)
                ),
                name="current_ownership_has_no_end_date",
            ),
        ]
        indexes = [
            models.Index(
                fields=("vehicle", "is_current"),
                name="ownership_vehicle_current_idx",
            ),
            models.Index(
                fields=("owner", "is_current"),
                name="ownership_owner_current_idx",
            ),
        ]

    @staticmethod
    def normalize_text(value):
        return " ".join(str(value or "").strip().split())

    def clean(self):
        super().clean()
        self.source_document_reference = self.normalize_text(
            self.source_document_reference
        )
        self.note = str(self.note or "").strip()

        if self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {
                    "end_date": (
                        "La date de fin ne peut pas être antérieure "
                        "à la date de début."
                    )
                }
            )

        if self.is_current and self.end_date:
            raise ValidationError(
                {
                    "end_date": (
                        "Une propriété actuelle ne doit pas avoir de date de fin."
                    )
                }
            )

        if not self.is_current and not self.end_date:
            raise ValidationError(
                {
                    "end_date": (
                        "Une propriété terminée doit avoir une date de fin."
                    )
                }
            )

        if self.owner_id and not self.owner.is_active and self.is_current:
            raise ValidationError(
                {
                    "owner": (
                        "Un propriétaire inactif ne peut pas devenir "
                        "propriétaire actuel."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vehicle_id} - {self.owner.full_name}"
