from django.db import models

from apps.core.models import TimeStampedModel
from apps.vehicles.models import Vehicle


class InsurancePolicy(TimeStampedModel):
    STATUS_VALID = "VALID"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_SUSPENDED = "SUSPENDED"
    STATUS_CHOICES = (
        (STATUS_VALID, "Valide"),
        (STATUS_EXPIRED, "Expirée"),
        (STATUS_SUSPENDED, "Suspendue"),
    )

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="insurance_policies")
    insurer = models.CharField(max_length=150)
    policy_number = models.CharField(max_length=80, unique=True)
    valid_until = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VALID)

    def __str__(self):
        return f"{self.policy_number} - {self.vehicle.plate_number}"

