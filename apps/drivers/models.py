from django.db import models
from apps.core.models import TimeStampedModel

class Driver(TimeStampedModel):
    SEX_CHOICES = [("M", "Masculin"), ("F", "Feminin")]

    dossier_number = models.CharField(max_length=50, unique=True)
    nif = models.CharField(max_length=40, blank=True, db_index=True)
    full_name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    license_type = models.CharField(max_length=80)
    issue_place = models.CharField(max_length=120, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.dossier_number})"
