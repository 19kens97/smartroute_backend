from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter
from django.core.files.base import ContentFile
from django.db.models import Count, Sum
from django.db.models.functions import Upper
from django.utils import timezone

from .models import Ticket

VALID_UNPAID_TICKET_STATUSES = ("ISSUED", "VALIDATED")


def generate_ticket_barcode(ticket):
    value = f"SMR-{ticket.id:08d}"
    buff = BytesIO()
    Code128(value, writer=ImageWriter()).write(buff)
    ticket.barcode_value = value
    ticket.barcode_image.save(f"{value}.png", ContentFile(buff.getvalue()), save=False)


def get_unpaid_valid_tickets_for_drivers(*, drivers=None, vehicle=None, period_start=None, period_end=None):
    start = period_start or timezone.localdate()
    end = period_end or start
    if end < start:
        raise ValueError("La fin de la période de contrôle ne peut pas précéder son début.")

    queryset = (
        Ticket.objects.select_related("vehicle")
        .annotate(
            normalized_driver_license=Upper("driver_license"),
            infraction_count=Count("ticket_infractions", distinct=True),
            total_amount=Sum("ticket_infractions__amount_snapshot"),
        )
        .filter(
            status__in=VALID_UNPAID_TICKET_STATUSES,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        .order_by("-created_at", "-id")
    )

    if vehicle is not None:
        return queryset.filter(vehicle=vehicle)

    dossier_numbers = {
        str(driver.dossier_number or "").strip().upper()
        for driver in (drivers or [])
        if getattr(driver, "dossier_number", None)
    }
    if not dossier_numbers:
        return queryset.none()
    return queryset.filter(normalized_driver_license__in=dossier_numbers)


def build_unpaid_ticket_summary(tickets):
    items = [
        {
            "id": ticket.id,
            "ticket_number": ticket.barcode_value or f"SMR-{ticket.id:08d}",
            "created_at": ticket.created_at,
            "status": ticket.status,
            "payment_status": "UNPAID",
            "plate_number": ticket.plate_number_snapshot,
            "infraction_count": ticket.infraction_count,
            "total_amount": str(ticket.total_amount) if ticket.total_amount is not None else None,
        }
        for ticket in tickets
    ]
    count = len(items)
    if count == 0:
        alert = None
    else:
        noun = "une verbalisation valide et impayée" if count == 1 else f"{count} verbalisations valides et impayées"
        alert = {
            "code": "UNPAID_TICKETS",
            "level": "WARNING",
            "message": f"Ce conducteur possède {noun}.",
        }
    return {
        "count": count,
        "has_unpaid_tickets": count > 0,
        "alert": alert,
        "items": items,
    }