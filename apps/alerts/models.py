from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel

class Alert(TimeStampedModel):
    TYPE_CHOICES=[("FIELD_ESCAPE","FIELD_ESCAPE"),("REFUSED_CONTROL","REFUSED_CONTROL"),("SUSPICIOUS_BEHAVIOR","SUSPICIOUS_BEHAVIOR"),("WANTED_VEHICLE","WANTED_VEHICLE"),("STOLEN_PLATE","STOLEN_PLATE"),("JUDICIAL_ALERT","JUDICIAL_ALERT")]
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="alerts")
    alert_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    plate_number = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
