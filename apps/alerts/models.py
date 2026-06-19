from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.vehicles.models import normalize_plate_number


class Alert(TimeStampedModel):
    TYPE_FIELD_ESCAPE = "FIELD_ESCAPE"
    TYPE_REFUSED_CONTROL = "REFUSED_CONTROL"
    TYPE_SUSPICIOUS_BEHAVIOR = "SUSPICIOUS_BEHAVIOR"
    TYPE_WANTED_VEHICLE = "WANTED_VEHICLE"
    TYPE_STOLEN_PLATE = "STOLEN_PLATE"
    TYPE_JUDICIAL = "JUDICIAL_ALERT"
    TYPE_CHOICES = [
        (TYPE_FIELD_ESCAPE, TYPE_FIELD_ESCAPE),
        (TYPE_REFUSED_CONTROL, TYPE_REFUSED_CONTROL),
        (TYPE_SUSPICIOUS_BEHAVIOR, TYPE_SUSPICIOUS_BEHAVIOR),
        (TYPE_WANTED_VEHICLE, TYPE_WANTED_VEHICLE),
        (TYPE_STOLEN_PLATE, TYPE_STOLEN_PLATE),
        (TYPE_JUDICIAL, TYPE_JUDICIAL),
    ]

    SOURCE_MANUAL = "MANUAL"
    SOURCE_SYSTEM = "SYSTEM"
    SOURCE_CHOICES = [(SOURCE_MANUAL, SOURCE_MANUAL), (SOURCE_SYSTEM, SOURCE_SYSTEM)]

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    plate_number = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    subject_nif = models.CharField(max_length=40, blank=True)
    system_reasons = models.JSONField(default=list, blank=True)
    control_period_start = models.DateField(null=True, blank=True)
    control_period_end = models.DateField(null=True, blank=True)
    deduplication_key = models.CharField(max_length=160, null=True, blank=True, unique=True)

    def save(self, *args, **kwargs):
        self.plate_number = normalize_plate_number(self.plate_number)
        super().save(*args, **kwargs)