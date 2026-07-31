from django.db.models import F, Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone

from apps.accounts.models import Person
from .models import Driver
from apps.tickets.services import (
    build_unpaid_ticket_summary,
    get_unpaid_valid_tickets_for_drivers,
)


VALIDITY_VALID = "VALID"
VALIDITY_EXPIRED = "EXPIRED"
VALIDITY_NOT_YET_VALID = "NOT_YET_VALID"
VALIDITY_UNKNOWN = "UNKNOWN"


def normalize_dossier_number(value: str) -> str:
    return Driver.normalize_dossier_number(value)


def normalize_dossier_lookup_value(value: str) -> str:
    value = normalize_dossier_number(value)
    return "".join(
        character
        for character in value
        if not character.isspace() and character != "-"
    )


def normalized_dossier_expression(field_name="dossier_number"):
    return Upper(
        Replace(
            Replace(
                Replace(
                    F(field_name),
                    Value("-"),
                    Value(""),
                ),
                Value(" "),
                Value(""),
            ),
            Value("\t"),
            Value(""),
        )
    )


def normalize_nif(value: str) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def normalized_nif_expression(field_name="person__nif"):
    return Upper(
        Replace(
            Replace(
                Replace(
                    F(field_name),
                    Value("-"),
                    Value(""),
                ),
                Value(" "),
                Value(""),
            ),
            Value("\t"),
            Value(""),
        )
    )


def get_license_validity_state(driver, today=None):
    today = today or timezone.localdate()

    if not driver.issue_date or not driver.expires_at:
        return VALIDITY_UNKNOWN

    if driver.issue_date > today:
        return VALIDITY_NOT_YET_VALID

    if driver.expires_at < today:
        return VALIDITY_EXPIRED

    return VALIDITY_VALID


def build_license_search_result(
    drivers,
    serializer_class,
    *,
    period_start=None,
    period_end=None,
):
    """
    Construit une réponse de recherche uniforme.

    Avec Driver.person en OneToOneField, une recherche par NIF ne peut
    normalement retourner qu'un seul dossier conducteur.
    """
    drivers = list(drivers)
    today = timezone.localdate()

    active_drivers = [
        driver
        for driver in drivers
        if get_license_validity_state(driver, today) == VALIDITY_VALID
    ]

    unpaid_tickets = get_unpaid_valid_tickets_for_drivers(
        drivers=drivers,
        period_start=period_start,
        period_end=period_end,
    )

    return (
        "Permis trouvé." if len(drivers) == 1 else "Permis trouvés.",
        {
            "count": len(drivers),
            "active_count": len(active_drivers),
            "has_conflict": False,
            "alert": None,
            "overlapping_license_ids": [],
            "licenses": serializer_class(
                drivers,
                many=True,
            ).data,
            "unpaid_tickets": build_unpaid_ticket_summary(
                unpaid_tickets
            ),
        },
    )



