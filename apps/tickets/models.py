import uuid
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel
from apps.infractions.models import Infraction
from apps.media_storage.services import ticket_proof_upload_path
from apps.vehicles.models import Vehicle

proof_upload_path = ticket_proof_upload_path

class Ticket(TimeStampedModel):
    STATUS_CHOICES=[("DRAFT","DRAFT"),("PENDING_SYNC","PENDING_SYNC"),("ISSUED","ISSUED"),("VALIDATED","VALIDATED"),("CANCELLED","CANCELLED"),("PAID","PAID")]
    client_uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets")
    driver_license = models.CharField(max_length=80)
    plate_number_snapshot = models.CharField(max_length=20)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    note = models.TextField(blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    location_label = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    ticket_number = models.CharField(max_length=8, unique=True, db_index=True, editable=False)
    barcode_image = models.ImageField(upload_to="barcodes/", blank=True)

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            from .services import generate_unique_ticket_number

            self.ticket_number = generate_unique_ticket_number()
        super().save(*args, **kwargs)

class TicketInfraction(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ticket_infractions")
    infraction = models.ForeignKey(Infraction, on_delete=models.PROTECT)
    amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2)

class TicketProof(TimeStampedModel):
    EVIDENCE_PHOTO = "PHOTO"
    EVIDENCE_VIDEO = "VIDEO"
    EVIDENCE_AUDIO = "AUDIO"
    EVIDENCE_TYPE_CHOICES = [
        (EVIDENCE_PHOTO, "Photo"),
        (EVIDENCE_VIDEO, "Video"),
        (EVIDENCE_AUDIO, "Audio"),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="proofs")
    file = models.FileField(upload_to=proof_upload_path)
    evidence_type = models.CharField(max_length=10, choices=EVIDENCE_TYPE_CHOICES, default=EVIDENCE_PHOTO)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    caption = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket_proofs")