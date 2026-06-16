from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel

class SyncLog(TimeStampedModel):
    client_uuid = models.CharField(max_length=120, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    direction = models.CharField(max_length=10, choices=[("PUSH", "PUSH"), ("PULL", "PULL")])
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="SUCCESS")
