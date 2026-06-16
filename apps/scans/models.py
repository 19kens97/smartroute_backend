from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel

class Scan(TimeStampedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    plate_number = models.CharField(max_length=20)
    source = models.CharField(max_length=30, default="MOBILE_GEMINI")
