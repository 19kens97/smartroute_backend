from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible

from apps.accounts.models import Person
from apps.core.models import TimeStampedModel
from apps.media_storage.services import alert_evidence_upload_path
from apps.vehicles.models import Vehicle, normalize_plate_number


FIELD_ALERT_LIFETIME_HOURS = 6


def normalize_subject_nif(value):
    return "".join(
        character
        for character in str(value or "").upper()
        if character.isalnum()
    )


@deconstructible
class PrivateAlertEvidenceStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "location",
            settings.PRIVATE_ALERT_EVIDENCE_ROOT,
        )
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_alert_evidence_storage = PrivateAlertEvidenceStorage()


class Alert(TimeStampedModel):
    class Category(models.TextChoices):
        AUTOMATIC = "AUTOMATIC", "Automatique"
        FIELD_REPORT = "FIELD_REPORT", "Signalement terrain"
        ADMINISTRATIVE = "ADMINISTRATIVE", "Administrative"

    class AlertType(models.TextChoices):
        FIELD_ESCAPE = "FIELD_ESCAPE", "Fuite lors du contrôle"
        REFUSED_CONTROL = "REFUSED_CONTROL", "Refus de contrôle"
        SUSPICIOUS_BEHAVIOR = "SUSPICIOUS_BEHAVIOR", "Comportement suspect"
        WANTED_VEHICLE = "WANTED_VEHICLE", "Véhicule volé ou recherché"
        STOLEN_PLATE = "STOLEN_PLATE", "Plaque volée"
        JUDICIAL = "JUDICIAL_ALERT", "Alerte judiciaire"
        DOCUMENT_EXPIRY_WARNING = (
            "DOCUMENT_EXPIRY_WARNING",
            "Document proche de l'expiration",
        )

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manuelle"
        SYSTEM = "SYSTEM", "Système"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RESOLVED = "RESOLVED", "Résolue"
        CANCELLED = "CANCELLED", "Annulée"
        EXPIRED = "EXPIRED", "Expirée"

    class Severity(models.TextChoices):
        INFO = "INFO", "Information"
        WARNING = "WARNING", "Avertissement"
        CRITICAL = "CRITICAL", "Critique"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alerts",
    )
    category = models.CharField(
        max_length=24,
        choices=Category.choices,
        db_index=True,
    )
    alert_type = models.CharField(
        max_length=40,
        choices=AlertType.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.INFO,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        db_index=True,
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    plate_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
    )
    subject_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    subject_nif = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
    )
    description = models.TextField(blank=True, default="")
    system_reasons = models.JSONField(default=list, blank=True)
    control_period_start = models.DateField(null=True, blank=True)
    control_period_end = models.DateField(null=True, blank=True)
    document_expires_on = models.DateField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )
    resolution_note = models.TextField(blank=True, default="")
    deduplication_key = models.CharField(
        max_length=190,
        null=True,
        blank=True,
        unique=True,
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=["category", "status", "created_at"],
                name="alert_category_status_idx",
            ),
            models.Index(
                fields=["status", "severity", "created_at"],
                name="alert_status_severity_idx",
            ),
            models.Index(
                fields=["vehicle", "alert_type", "status"],
                name="alert_vehicle_type_idx",
            ),
        ]

    @property
    def is_terminal(self):
        return self.status in {
            self.Status.RESOLVED,
            self.Status.CANCELLED,
            self.Status.EXPIRED,
        }

    def clean(self):
        super().clean()

        self.plate_number = normalize_plate_number(
            self.plate_number
            or getattr(self.vehicle, "plate_number", "")
        )
        self.subject_nif = normalize_subject_nif(
            self.subject_nif
            or getattr(self.subject_person, "nif", "")
        )
        self.description = (self.description or "").strip()
        self.resolution_note = (self.resolution_note or "").strip()

        if (
            self.control_period_start
            and self.control_period_end
            and self.control_period_end < self.control_period_start
        ):
            raise ValidationError(
                {
                    "control_period_end": (
                        "La fin de la période ne peut pas précéder le début."
                    )
                }
            )

        if self.category == self.Category.AUTOMATIC:
            if self.source != self.Source.SYSTEM:
                raise ValidationError(
                    {"source": "Une alerte automatique doit provenir du système."}
                )
            if not self.deduplication_key:
                raise ValidationError(
                    {
                        "deduplication_key": (
                            "Une alerte automatique doit posséder "
                            "une clé de déduplication."
                        )
                    }
                )

        if (
            self.category != self.Category.AUTOMATIC
            and self.source != self.Source.MANUAL
        ):
            raise ValidationError(
                {"source": "Une alerte manuelle doit avoir la source MANUAL."}
            )

        if self.category == self.Category.FIELD_REPORT and self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(
                hours=FIELD_ALERT_LIFETIME_HOURS
            )

        if (
            self.category != self.Category.FIELD_REPORT
            and self.expires_at is not None
        ):
            raise ValidationError(
                {
                    "expires_at": (
                        "Seules les alertes terrain utilisent "
                        "une expiration horaire."
                    )
                }
            )

        if self.alert_type in {
            self.AlertType.WANTED_VEHICLE,
            self.AlertType.STOLEN_PLATE,
        } and not self.plate_number:
            raise ValidationError(
                {
                    "plate_number": (
                        "La plaque est obligatoire pour ce type d'alerte."
                    )
                }
            )

        if self.status == self.Status.ACTIVE:
            self.resolved_at = None
            self.resolved_by = None
            self.resolution_note = ""
        elif self.resolved_at is None:
            self.resolved_at = timezone.now()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_alert_type_display()} #{self.pk or 'nouvelle'}"


class AlertEvidence(TimeStampedModel):
    class EvidenceType(models.TextChoices):
        AUDIO = "AUDIO", "Audio"
        VIDEO = "VIDEO", "Vidéo"

    alert = models.ForeignKey(
        Alert,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    evidence_type = models.CharField(
        max_length=10,
        choices=EvidenceType.choices,
    )
    file = models.FileField(
        upload_to=alert_evidence_upload_path,
        storage=private_alert_evidence_storage,
    )
    mime_type = models.CharField(max_length=100, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
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
    alert = models.ForeignKey(
        Alert,
        on_delete=models.CASCADE,
        related_name="receipts",
    )
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
