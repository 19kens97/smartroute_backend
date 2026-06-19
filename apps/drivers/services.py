from itertools import combinations

from django.db.models import F, Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone

from apps.tickets.services import build_unpaid_ticket_summary, get_unpaid_valid_tickets_for_drivers


VALIDITY_VALID = "VALID"
VALIDITY_EXPIRED = "EXPIRED"
VALIDITY_NOT_YET_VALID = "NOT_YET_VALID"
VALIDITY_UNKNOWN = "UNKNOWN"


def normalize_dossier_number(value: str) -> str:
    return str(value or "").strip()


def normalize_nif(value: str) -> str:
    value = str(value or "").strip()
    return "".join(char for char in value if not char.isspace() and char != "-").upper()


def normalized_nif_expression(field_name="nif"):
    return Upper(
        Replace(
            Replace(
                Replace(F(field_name), Value("-"), Value("")),
                Value(" "),
                Value(""),
            ),
            Value("	"),
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


def periods_overlap(start_a, end_a, start_b, end_b):
    if not all((start_a, end_a, start_b, end_b)):
        return False
    return start_a <= end_b and start_b <= end_a


def get_overlapping_license_ids(drivers):
    overlapping_ids = set()
    for first, second in combinations(drivers, 2):
        if periods_overlap(first.issue_date, first.expires_at, second.issue_date, second.expires_at):
            overlapping_ids.update((first.id, second.id))
    return sorted(overlapping_ids)


def build_license_search_result(drivers, serializer_class, period_start=None, period_end=None):
    drivers = list(drivers)
    today = timezone.localdate()
    active_drivers = [
        driver for driver in drivers if get_license_validity_state(driver, today) == VALIDITY_VALID
    ]
    overlapping_license_ids = get_overlapping_license_ids(drivers)
    active_overlapping_ids = get_overlapping_license_ids(active_drivers)
    has_conflict = bool(overlapping_license_ids)
    has_business_alert = has_conflict or len(active_overlapping_ids) >= 2

    alert = None
    message = "Permis trouvé." if len(drivers) == 1 else "Permis trouvés."
    if has_business_alert:
        message = "Plusieurs permis actifs ou superposés ont été détectés."
        alert = {
            "code": "MULTIPLE_ACTIVE_LICENSES",
            "level": "WARNING",
            "message": (
                "Plusieurs permis utilisables simultanément sont associés à ce NIF. "
                "Une vérification administrative est requise."
            ),
        }

    unpaid_tickets = get_unpaid_valid_tickets_for_drivers(
        drivers=drivers,
        period_start=period_start,
        period_end=period_end,
    )

    return message, {
        "count": len(drivers),
        "active_count": len(active_drivers),
        "has_conflict": has_conflict,
        "alert": alert,
        "overlapping_license_ids": overlapping_license_ids,
        "licenses": serializer_class(drivers, many=True).data,
        "unpaid_tickets": build_unpaid_ticket_summary(unpaid_tickets),
    }