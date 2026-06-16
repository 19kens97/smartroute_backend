from django.db import models
from apps.core.models import TimeStampedModel

class Infraction(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.label}"
