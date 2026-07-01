import logging
import secrets

from django.db.models import Count, Sum
from django.db.models.functions import Upper
from django.utils import timezone

from .models import Ticket

logger = logging.getLogger(__name__)
TICKET_NUMBER_MAX_ATTEMPTS = 10
TICKET_NUMBER_LENGTH = 8

VALID_UNPAID_TICKET_STATUSES = ("ISSUED", "VALIDATED")


def generate_unique_ticket_number():
    for attempt in range(1, TICKET_NUMBER_MAX_ATTEMPTS + 1):
        value = secrets.token_hex(4).upper()
        if not Ticket.objects.filter(ticket_number=value).exists():
            return value
        logger.warning("event=ticket_number_collision_retry attempt=%s ticket_number=%s", attempt, value)
    raise RuntimeError("Impossible de generer un numero de PV unique.")


def is_valid_ticket_number(value):
    return isinstance(value, str) and len(value) == TICKET_NUMBER_LENGTH and all(char in "0123456789ABCDEF" for char in value)


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
            "ticket_number": ticket.ticket_number,
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