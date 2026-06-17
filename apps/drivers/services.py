from itertools import combinations

from django.db.models import F, Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone


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


def periods_overlap(start_a, end_a, start_b, end_b):
    """
    Return False when a boundary is missing: an incomplete period is unknown,
    so it is not treated as an administratively proven overlap.
    """
    if not all((start_a, end_a, start_b, end_b)):
        return False
    return start_a <= end_b and start_b <= end_a


def get_overlapping_license_ids(drivers):
    overlapping_ids = set()
    for first, second in combinations(drivers, 2):
        if periods_overlap(first.issue_date, first.expires_at, second.issue_date, second.expires_at):
            overlapping_ids.update((first.id, second.id))
    return sorted(overlapping_ids)


def build_license_search_result(drivers, serializer_class):
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
    message = "Permis trouve." if len(drivers) == 1 else "Permis trouves."
    if has_business_alert:
        message = "Plusieurs permis actifs ou superposes ont ete detectes."
        alert = {
            "code": "MULTIPLE_ACTIVE_LICENSES",
            "level": "WARNING",
            "message": (
                "Plusieurs permis utilisables simultanement sont associes a ce NIF. "
                "Une verification administrative est requise."
            ),
        }

    return message, {
        "count": len(drivers),
        "active_count": len(active_drivers),
        "has_conflict": has_conflict,
        "alert": alert,
        "overlapping_license_ids": overlapping_license_ids,
        "licenses": serializer_class(drivers, many=True).data,
    }
