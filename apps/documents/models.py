from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.media_storage.services import document_upload_path
from apps.vehicles.models import Vehicle

upload_doc_path = document_upload_path


class Document(TimeStampedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=120)
    file = models.FileField(upload_to=upload_doc_path)