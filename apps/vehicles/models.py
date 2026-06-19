from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.owners.models import Owner


def normalize_plate_number(value):
    """Return the canonical representation used for stored registration plates."""
    return "".join((value or "").split()).upper()


def normalize_engine_number(value):
    normalized = " ".join((value or "").split()).upper()
    return normalized or None


def validate_vehicle_year(value):
    if value is not None and value > timezone.localdate().year:
        raise ValidationError("L'annee du vehicule ne peut pas etre dans le futur.")


class Vehicle(TimeStampedModel):
    plate_number = models.CharField(max_length=20, unique=True)
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="vehicles")
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=50, blank=True)
    year = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1900), validate_vehicle_year])
    engine_number = models.CharField(max_length=100, null=True, blank=True)
    registration_valid_until = models.DateField(null=True, blank=True)
    is_wanted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.plate_number = normalize_plate_number(self.plate_number)
        self.engine_number = normalize_engine_number(self.engine_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.plate_number
