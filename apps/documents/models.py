from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel
from apps.vehicles.models import Vehicle

def upload_doc_path(instance, filename):
    return f"documents/{instance.vehicle_id}/{filename}"

class Document(TimeStampedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=120)
    file = models.FileField(upload_to=upload_doc_path)
