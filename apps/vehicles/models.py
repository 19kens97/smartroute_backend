from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.owners.models import Owner


def normalize_plate_number(value):
    """Retourne la représentation canonique d'une plaque."""
    return "".join(
        (value or "").replace("-", "").split()
    ).upper()


def plate_number_lookup_variants(value):
    """
    Retourne les variantes acceptées pour les anciennes plaques
    compactes ou avec tiret.
    """
    normalized = normalize_plate_number(value)
    variants = {normalized} if normalized else set()

    if len(normalized) > 2:
        variants.add(
            f"{normalized[:2]}-{normalized[2:]}"
        )

    return list(variants)


def normalize_engine_number(value):
    normalized = " ".join(
        (value or "").split()
    ).upper()
    return normalized or None


def validate_vehicle_year(value):
    if (
        value is not None
        and value > timezone.localdate().year
    ):
        raise ValidationError(
            "L'année du véhicule ne peut pas être dans le futur."
        )


class Vehicle(TimeStampedModel):
    plate_number = models.CharField(
        max_length=20,
        unique=True,
    )
    owner = models.ForeignKey(
        Owner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicles",
    )
    brand = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    model = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    color = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )
    year = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1900),
            validate_vehicle_year,
        ],
    )
    engine_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    registration_valid_until = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )
    is_wanted = models.BooleanField(
        default=False,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["plate_number"],
                name="vehicle_plate_idx",
            ),
            models.Index(
                fields=["owner", "is_wanted"],
                name="vehicle_owner_wanted_idx",
            ),
        ]
        verbose_name = "Véhicule"
        verbose_name_plural = "Véhicules"

    def clean(self):
        super().clean()

        self.plate_number = normalize_plate_number(
            self.plate_number
        )
        self.engine_number = normalize_engine_number(
            self.engine_number
        )

        if not self.plate_number:
            raise ValidationError(
                {
                    "plate_number": (
                        "Le numéro d'immatriculation est obligatoire."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.plate_number = normalize_plate_number(
            self.plate_number
        )
        self.engine_number = normalize_engine_number(
            self.engine_number
        )

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.plate_number
