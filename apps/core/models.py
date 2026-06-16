from django.conf import settings
from django.db import models

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class AuditLog(TimeStampedModel):
    ACTIONS = [("CREATE","Create"),("UPDATE","Update"),("DELETE","Delete"),("STATUS_CHANGE","Status Change")]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    model_name = models.CharField(max_length=120)
    object_id = models.CharField(max_length=120)
    action = models.CharField(max_length=20, choices=ACTIONS)
    payload = models.JSONField(default=dict, blank=True)
