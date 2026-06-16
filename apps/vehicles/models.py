from django.db import models
from apps.core.models import TimeStampedModel
from apps.owners.models import Owner

class Vehicle(TimeStampedModel):
    plate_number = models.CharField(max_length=20, unique=True)
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, related_name="vehicles")
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=50, blank=True)
    is_wanted = models.BooleanField(default=False)

    def __str__(self):
        return self.plate_number
