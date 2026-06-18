from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel

class Scan(TimeStampedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    plate_number = models.CharField(max_length=20)
    source = models.CharField(max_length=30, default="MOBILE_GEMINI")


class GeminiScan(TimeStampedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    plate_number = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=30, default="MOBILE_GEMINI")
    model_used = models.CharField(max_length=80, blank=True)
    raw_response = models.TextField(blank=True)
    plate_detected = models.BooleanField(default=False)
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gemini_scans",
    )
    scanned_at = models.DateTimeField(auto_now_add=True)
