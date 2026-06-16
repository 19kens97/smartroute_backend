from django.db import models
from apps.core.models import TimeStampedModel


class Owner(TimeStampedModel):
    full_name = models.CharField(max_length=150)
    national_id = models.CharField(max_length=50, unique=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.full_name
