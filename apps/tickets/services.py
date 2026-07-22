import logging
import secrets

from django.db import transaction
from django.db.models import Count, Max, Q

from .models import Ticket, TicketVerbalization


logger = logging.getLogger(__name__)
TICKET_NUMBER_MAX_ATTEMPTS = 10
TICKET_NUMBER_LENGTH = 8


def generate_unique_ticket_number():
    for attempt in range(1, TICKET_NUMBER_MAX_ATTEMPTS + 1):
        value = secrets.token_hex(4).upper()
        if not Ticket.objects.filter(ticket_number=value).exists():
            return value
        logger.warning(
            "event=ticket_number_collision_retry attempt=%s ticket_number=%s",
            attempt,
            value,
        )
    raise RuntimeError("Impossible de générer un numéro de PV unique.")


def is_valid_ticket_number(value):
    return (
        isinstance(value, str)
        and len(value) == TICKET_NUMBER_LENGTH
        and all(character in "0123456789ABCDEF" for character in value)
    )


def find_open_ticket(*, driver=None, dossier_number=None, nif=None, ticket_number=None):
    queryset = Ticket.objects.filter(status=Ticket.Status.OPEN)

    if ticket_number:
        return queryset.filter(ticket_number=str(ticket_number).strip().upper()).first()
    if driver is not None:
        return queryset.filter(driver=driver).order_by("-opened_at", "-id").first()
    if dossier_number:
        return queryset.filter(
            driver_dossier_snapshot__iexact=str(dossier_number).strip()
        ).order_by("-opened_at", "-id").first()
    if nif:
        return queryset.filter(
            driver_nif_snapshot__iexact=str(nif).strip()
        ).order_by("-opened_at", "-id").first()
    return None


@transaction.atomic
def next_verbalization_sequence(ticket):
    locked_ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if locked_ticket.status != Ticket.Status.OPEN:
        raise ValueError("Le PV n'est plus en cours.")
    current = (
        TicketVerbalization.objects.filter(ticket=locked_ticket)
        .aggregate(maximum=Max("sequence_number"))["maximum"]
        or 0
    )
    return current + 1


def get_open_tickets_for_drivers(*, drivers=None, vehicle=None, period_start=None, period_end=None):
    if period_start and period_end and period_end < period_start:
        raise ValueError("La fin de la période ne peut pas précéder son début.")

    queryset = (
        Ticket.objects
        .filter(status=Ticket.Status.OPEN)
        .annotate(
            verbalization_count_annotation=Count(
                "verbalizations",
                filter=Q(verbalizations__status=TicketVerbalization.Status.ACTIVE),
                distinct=True,
            )
        )
        .order_by("-opened_at", "-id")
    )

    if vehicle is not None:
        return queryset.filter(verbalizations__vehicle=vehicle).distinct()

    driver_ids = {driver.pk for driver in (drivers or []) if getattr(driver, "pk", None)}
    dossier_numbers = {
        str(getattr(driver, "dossier_number", "") or "").strip().upper()
        for driver in (drivers or [])
        if getattr(driver, "dossier_number", None)
    }
    if driver_ids:
        return queryset.filter(driver_id__in=driver_ids)
    if dossier_numbers:
        return queryset.filter(driver_dossier_snapshot__in=dossier_numbers)
    return queryset.none()


def get_unpaid_valid_tickets_for_drivers(**kwargs):
    """Compatibilité avec le service d'alertes existant.

    Dans la nouvelle logique, un PV OPEN représente une fiche de verbalisation
    encore en cours. Aucun montant n'est calculé localement.
    """
    return get_open_tickets_for_drivers(**kwargs)


def build_open_ticket_summary(tickets):
    items = [
        {
            "id": ticket.id,
            "ticket_number": ticket.ticket_number,
            "barcode_value": ticket.barcode_value,
            "opened_at": ticket.opened_at,
            "status": ticket.status,
            "verbalization_count": getattr(
                ticket,
                "verbalization_count_annotation",
                ticket.verbalization_count,
            ),
            "pricing_status": ticket.pricing_status,
        }
        for ticket in tickets
    ]
    count = len(items)
    return {
        "count": count,
        "has_open_tickets": count > 0,
        "alert": (
            {
                "code": "OPEN_TICKETS",
                "level": "WARNING",
                "message": (
                    "Ce conducteur possède une fiche de verbalisation en cours."
                    if count == 1
                    else f"Ce conducteur possède {count} fiches de verbalisation en cours."
                ),
            }
            if count
            else None
        ),
        "items": items,
    }


def build_unpaid_ticket_summary(tickets):
    """Alias temporaire pour ne pas casser les imports existants d'alerts."""
    summary = build_open_ticket_summary(tickets)
    return {
        "count": summary["count"],
        "has_unpaid_tickets": summary["has_open_tickets"],
        "alert": summary["alert"],
        "items": summary["items"],
    }
