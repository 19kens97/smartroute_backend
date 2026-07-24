from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible
from apps.core.models import TimeStampedModel
from apps.media_storage.services import scan_upload_path


@deconstructible
class PrivateScanStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_SCAN_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Private scan files are not directly addressable.")


private_scan_storage = PrivateScanStorage()


class Scan(TimeStampedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    plate_number = models.CharField(max_length=20)
    source = models.CharField(max_length=30, default="MOBILE_GEMINI")


class GeminiScan(TimeStampedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    plate_number = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=30, default="MOBILE_GEMINI")
    image = models.ImageField(upload_to=scan_upload_path, storage=private_scan_storage, blank=True)
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
