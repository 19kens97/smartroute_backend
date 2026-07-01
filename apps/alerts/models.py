from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible

from apps.core.models import TimeStampedModel
from apps.media_storage.services import alert_evidence_upload_path
from apps.vehicles.models import normalize_plate_number


@deconstructible
class PrivateAlertEvidenceStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_ALERT_EVIDENCE_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_alert_evidence_storage = PrivateAlertEvidenceStorage()


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


class AlertEvidence(TimeStampedModel):
    TYPE_AUDIO = "AUDIO"
    TYPE_VIDEO = "VIDEO"
    TYPE_CHOICES = [(TYPE_AUDIO, "Audio"), (TYPE_VIDEO, "Video")]

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="evidence")
    evidence_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    file = models.FileField(upload_to=alert_evidence_upload_path, storage=private_alert_evidence_storage)
    mime_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="alert_evidence",
    )

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self):
        return f"{self.alert_id}:{self.evidence_type}:{self.pk}"


class AlertReceipt(TimeStampedModel):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="receipts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_receipts",
    )
    opened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("alert", "user"),
                name="unique_alert_receipt_per_user",
            )
        ]

    def __str__(self):
        return f"{self.alert_id}:{self.user_id}"