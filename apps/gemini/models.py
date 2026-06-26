from django.db import models
from Vehicles.models import Vehicle
from django.conf import settings


class GeminiScan(models.Model):
    plate_number = models.CharField(max_length=16)
    model_used = models.CharField(max_length=120)
    vehicle = models.ForeignKey(
        Vehicle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gemini_scans",
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gemini_scans",
    )
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scanned_at"]

    def __str__(self):
        return f"{self.plate_number} ({self.model_used})"
