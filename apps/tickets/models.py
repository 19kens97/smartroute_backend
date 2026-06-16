import uuid
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel
from apps.infractions.models import Infraction
from apps.vehicles.models import Vehicle

def proof_upload_path(instance, filename):
    return f"tickets/{instance.ticket_id}/proofs/{filename}"

class Ticket(TimeStampedModel):
    STATUS_CHOICES=[("DRAFT","DRAFT"),("PENDING_SYNC","PENDING_SYNC"),("ISSUED","ISSUED"),("VALIDATED","VALIDATED"),("CANCELLED","CANCELLED"),("PAID","PAID")]
    client_uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets")
    driver_license = models.CharField(max_length=80)
    plate_number_snapshot = models.CharField(max_length=20)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    note = models.TextField(blank=True)
    barcode_value = models.CharField(max_length=64, blank=True)
    barcode_image = models.ImageField(upload_to="barcodes/", blank=True)

class TicketInfraction(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ticket_infractions")
    infraction = models.ForeignKey(Infraction, on_delete=models.PROTECT)
    amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2)

class TicketProof(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="proofs")
    file = models.FileField(upload_to=proof_upload_path)
    caption = models.CharField(max_length=200, blank=True)
