from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.vehicles.models import Vehicle


class InsurancePolicy(TimeStampedModel):
    """
    Police d'assurance associée à un véhicule.

    Le fichier PDF ou l'image de la police reste géré par l'application
    `documents`. Ce modèle représente la donnée métier structurée.
    """

    class Status(models.TextChoices):
        VALID = "VALID", "Valide"
        EXPIRED = "EXPIRED", "Expirée"
        SUSPENDED = "SUSPENDED", "Suspendue"
        CANCELLED = "CANCELLED", "Annulée"

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="insurance_policies",
    )
    insurer = models.CharField(max_length=150)
    policy_number = models.CharField(
        max_length=80,
        unique=True,
    )
    valid_from = models.DateField(
        null=True,
        blank=True,
    )
    valid_until = models.DateField(
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VALID,
        db_index=True,
    )

    class Meta:
        ordering = ["-valid_until", "-id"]
        indexes = [
            models.Index(
                fields=["vehicle", "status"],
                name="insurance_vehicle_status_idx",
            ),
            models.Index(
                fields=["policy_number"],
                name="insurance_policy_number_idx",
            ),
        ]
        verbose_name = "Police d'assurance"
        verbose_name_plural = "Polices d'assurance"

    @staticmethod
    def normalize_policy_number(value):
        return " ".join(
            str(value or "").strip().upper().split()
        )

    def clean(self):
        super().clean()

        self.policy_number = self.normalize_policy_number(
            self.policy_number
        )
        self.insurer = (self.insurer or "").strip()

        if not self.policy_number:
            raise ValidationError(
                {
                    "policy_number": (
                        "Le numéro de police est obligatoire."
                    )
                }
            )

        if not self.insurer:
            raise ValidationError(
                {
                    "insurer": (
                        "Le nom de l'assureur est obligatoire."
                    )
                }
            )

        if (
            self.valid_from
            and self.valid_until
            and self.valid_until < self.valid_from
        ):
            raise ValidationError(
                {
                    "valid_until": (
                        "La date de fin ne peut pas être antérieure "
                        "à la date de début."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.policy_number = self.normalize_policy_number(
            self.policy_number
        )
        self.insurer = (self.insurer or "").strip()

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_currently_valid(self):
        today = timezone.localdate()

        if self.status != self.Status.VALID:
            return False

        if self.valid_from and self.valid_from > today:
            return False

        return self.valid_until >= today

    def __str__(self):
        return (
            f"{self.policy_number} - "
            f"{self.vehicle.plate_number}"
        )
