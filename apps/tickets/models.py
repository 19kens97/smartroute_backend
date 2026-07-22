import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible

from apps.core.models import TimeStampedModel
from apps.drivers.models import Driver
from apps.infractions.models import Infraction
from apps.media_storage.services import ticket_proof_upload_path
from apps.vehicles.models import Vehicle, normalize_plate_number


def proof_upload_path(instance, filename):
    """Compatibilité avec la migration initiale existante."""
    return ticket_proof_upload_path(instance, filename)


@deconstructible
class PrivateTicketProofStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_TICKET_PROOF_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_ticket_proof_storage = PrivateTicketProofStorage()


class Ticket(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "En cours"
        CLOSED = "CLOSED", "Clôturé"
        CANCELLED = "CANCELLED", "Annulé"

    class SyncStatus(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SYNCED = "SYNCED", "Synchronisé"
        FAILED = "FAILED", "Échec"

    class PricingStatus(models.TextChoices):
        NOT_REQUESTED = "NOT_REQUESTED", "Non demandé"
        PENDING = "PENDING", "Demande en cours"
        AVAILABLE = "AVAILABLE", "Disponible"
        FAILED = "FAILED", "Échec"

    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    ticket_number = models.CharField(max_length=8, unique=True, db_index=True, editable=False)
    barcode_value = models.CharField(max_length=120, unique=True, db_index=True, editable=False)

    driver = models.ForeignKey(
        Driver,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tickets",
    )
    driver_dossier_snapshot = models.CharField(max_length=80, blank=True, default="", db_index=True)
    driver_name_snapshot = models.CharField(max_length=160, blank=True, default="")
    driver_nif_snapshot = models.CharField(max_length=40, blank=True, default="", db_index=True)

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_tickets",
    )
    opened_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.SYNCED,
        db_index=True,
    )

    pricing_status = models.CharField(
        max_length=20,
        choices=PricingStatus.choices,
        default=PricingStatus.NOT_REQUESTED,
        db_index=True,
    )
    pricing_authority = models.CharField(max_length=40, blank=True, default="")
    pricing_external_reference = models.CharField(max_length=120, blank=True, default="")
    pricing_requested_at = models.DateTimeField(null=True, blank=True)
    pricing_last_checked_at = models.DateTimeField(null=True, blank=True)
    pricing_message = models.CharField(max_length=255, blank=True, default="")

    note = models.TextField(blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_tickets",
    )
    closure_reason = models.TextField(blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_tickets",
    )
    cancellation_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-opened_at", "-id")
        indexes = [
            models.Index(fields=["status", "opened_at"], name="ticket_status_opened_idx"),
            models.Index(fields=["driver", "status"], name="ticket_driver_status_idx"),
            models.Index(fields=["pricing_status", "status"], name="ticket_pricing_status_idx"),
        ]

    def clean(self):
        super().clean()
        self.driver_dossier_snapshot = (self.driver_dossier_snapshot or "").strip().upper()
        self.driver_name_snapshot = (self.driver_name_snapshot or "").strip()
        self.driver_nif_snapshot = (self.driver_nif_snapshot or "").strip().upper()
        self.note = (self.note or "").strip()
        self.pricing_authority = (self.pricing_authority or "").strip().upper()
        self.pricing_external_reference = (self.pricing_external_reference or "").strip()
        self.pricing_message = (self.pricing_message or "").strip()
        self.closure_reason = (self.closure_reason or "").strip()
        self.cancellation_reason = (self.cancellation_reason or "").strip()

        if self.driver is not None:
            self.driver_dossier_snapshot = self.driver.dossier_number
            person = getattr(self.driver, "person", None)
            if person is not None:
                self.driver_name_snapshot = getattr(person, "full_name", "") or self.driver_name_snapshot
                self.driver_nif_snapshot = getattr(person, "nif", "") or self.driver_nif_snapshot

        if not (self.driver_id or self.driver_dossier_snapshot or self.driver_nif_snapshot):
            raise ValidationError({"driver": "Le conducteur ou une référence d'identification est obligatoire."})

        if self.status == self.Status.CLOSED:
            if not self.closed_at:
                self.closed_at = timezone.now()
            if not self.closed_by:
                raise ValidationError({"closed_by": "L'auteur de la clôture est obligatoire."})
            if len(self.closure_reason) < 5:
                raise ValidationError({"closure_reason": "Le motif de clôture doit contenir au moins 5 caractères."})
            self.cancelled_at = None
            self.cancelled_by = None
            self.cancellation_reason = ""
        elif self.status == self.Status.CANCELLED:
            if not self.cancelled_at:
                self.cancelled_at = timezone.now()
            if not self.cancelled_by:
                raise ValidationError({"cancelled_by": "L'auteur de l'annulation est obligatoire."})
            if len(self.cancellation_reason) < 5:
                raise ValidationError({"cancellation_reason": "Le motif d'annulation doit contenir au moins 5 caractères."})
            self.closed_at = None
            self.closed_by = None
            self.closure_reason = ""
        else:
            self.closed_at = None
            self.closed_by = None
            self.closure_reason = ""
            self.cancelled_at = None
            self.cancelled_by = None
            self.cancellation_reason = ""

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            from .services import generate_unique_ticket_number
            self.ticket_number = generate_unique_ticket_number()
        if not self.barcode_value:
            self.barcode_value = f"PV:{self.ticket_number}"
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def verbalization_count(self):
        return self.verbalizations.filter(status=TicketVerbalization.Status.ACTIVE).count()

    def __str__(self):
        return self.ticket_number


class TicketVerbalization(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CANCELLED = "CANCELLED", "Annulée"

    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="verbalizations")
    sequence_number = models.PositiveIntegerField()
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ticket_verbalizations",
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_verbalizations",
    )
    plate_number_snapshot = models.CharField(max_length=20, db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    location_label = models.CharField(max_length=255, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_ticket_verbalizations",
    )
    cancellation_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("sequence_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("ticket", "sequence_number"),
                name="unique_verbalization_sequence_per_ticket",
            ),
        ]
        indexes = [
            models.Index(fields=["ticket", "status", "occurred_at"], name="verbal_ticket_status_idx"),
            models.Index(fields=["plate_number_snapshot", "occurred_at"], name="verbal_plate_occurred_idx"),
        ]

    def clean(self):
        super().clean()
        self.plate_number_snapshot = normalize_plate_number(
            self.plate_number_snapshot or getattr(self.vehicle, "plate_number", "")
        )
        self.location_label = (self.location_label or "").strip()
        self.note = (self.note or "").strip()
        self.cancellation_reason = (self.cancellation_reason or "").strip()

        if self.ticket_id and self.ticket.status != Ticket.Status.OPEN:
            raise ValidationError({"ticket": "Une verbalisation ne peut être ajoutée qu'à un PV en cours."})
        if not self.plate_number_snapshot:
            raise ValidationError({"plate_number_snapshot": "La plaque est obligatoire."})

        if self.status == self.Status.CANCELLED:
            if not self.cancelled_at:
                self.cancelled_at = timezone.now()
            if not self.cancelled_by:
                raise ValidationError({"cancelled_by": "L'auteur de l'annulation est obligatoire."})
            if len(self.cancellation_reason) < 5:
                raise ValidationError({"cancellation_reason": "Le motif d'annulation doit contenir au moins 5 caractères."})
        else:
            self.cancelled_at = None
            self.cancelled_by = None
            self.cancellation_reason = ""

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket.ticket_number} - verbalisation {self.sequence_number}"


class TicketInfraction(models.Model):
    verbalization = models.ForeignKey(
        TicketVerbalization,
        on_delete=models.CASCADE,
        related_name="infractions",
    )
    infraction = models.ForeignKey(
        Infraction,
        on_delete=models.PROTECT,
        related_name="verbalization_links",
    )
    code_snapshot = models.CharField(max_length=20)
    label_snapshot = models.CharField(max_length=255)
    article_snapshot = models.CharField(max_length=160, blank=True, default="")
    penalty_type_snapshot = models.CharField(max_length=20)
    amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    minimum_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    maximum_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_options_snapshot = models.JSONField(default=list, blank=True)
    penalty_text_snapshot = models.CharField(max_length=255, blank=True, default="")
    currency_snapshot = models.CharField(max_length=3, default="HTG")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("verbalization", "infraction"),
                name="unique_infraction_per_verbalization",
            )
        ]
        ordering = ("id",)

    def clean(self):
        super().clean()
        if self.infraction_id:
            self.code_snapshot = self.infraction.code
            self.label_snapshot = self.infraction.label
            self.article_snapshot = self.infraction.article
            self.penalty_type_snapshot = self.infraction.penalty_type
            self.amount_snapshot = self.infraction.amount
            self.minimum_amount_snapshot = self.infraction.minimum_amount
            self.maximum_amount_snapshot = self.infraction.maximum_amount
            self.amount_options_snapshot = list(self.infraction.amount_options)
            self.penalty_text_snapshot = self.infraction.penalty_text
            self.currency_snapshot = self.infraction.currency

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.verbalization_id} - {self.code_snapshot}"


class TicketProof(TimeStampedModel):
    class EvidenceType(models.TextChoices):
        PHOTO = "PHOTO", "Photo"
        VIDEO = "VIDEO", "Vidéo"
        AUDIO = "AUDIO", "Audio"

    verbalization = models.ForeignKey(
        TicketVerbalization,
        on_delete=models.CASCADE,
        related_name="proofs",
    )
    file = models.FileField(
        upload_to=ticket_proof_upload_path,
        storage=private_ticket_proof_storage,
    )
    evidence_type = models.CharField(
        max_length=10,
        choices=EvidenceType.choices,
        default=EvidenceType.PHOTO,
    )
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    caption = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ticket_proofs",
    )

    class Meta:
        ordering = ("created_at", "id")
