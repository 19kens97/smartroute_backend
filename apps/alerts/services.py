from django.db import transaction
from django.utils import timezone

from apps.core.services import log_action
from apps.drivers.models import Driver
from apps.drivers.services import normalize_nif, normalized_nif_expression
from apps.tickets.services import get_unpaid_valid_tickets_for_drivers
from apps.vehicles.models import normalize_plate_number

from .models import Alert

REASON_REGISTRATION_EXPIRED = "REGISTRATION_EXPIRED"
REASON_INSURANCE_EXPIRED = "INSURANCE_EXPIRED"
REASON_UNPAID_TICKETS = "MULTIPLE_VALID_UNPAID_TICKETS"
REASON_MULTIPLE_LICENSES = "MULTIPLE_VALID_LICENSES"

REASON_LABELS = {
    REASON_REGISTRATION_EXPIRED: "Immatriculation expirée",
    REASON_INSURANCE_EXPIRED: "Police d'assurance expirée",
    REASON_UNPAID_TICKETS: "Au moins deux tickets valides et non payés pendant la période de contrôle",
    REASON_MULTIPLE_LICENSES: "Au moins deux permis valides associés au même NIF pendant la période de contrôle",
}


def _period_bounds(period_start=None, period_end=None):
    today = timezone.localdate()
    start = period_start or today
    end = period_end or start
    if end < start:
        raise ValueError("La fin de la période de contrôle ne peut pas précéder son début.")
    return start, end


def _get_subject_nif(vehicle, nif):
    if nif:
        return normalize_nif(nif)
    owner = getattr(vehicle, "owner", None)
    return normalize_nif(getattr(owner, "national_id", ""))


def _build_key(plate_number, subject_nif, period_start, period_end):
    subject = f"PLATE:{plate_number}" if plate_number else f"NIF:{subject_nif}"
    return f"JUDICIAL:{subject}:{period_start.isoformat()}:{period_end.isoformat()}"


@transaction.atomic
def evaluate_judicial_alert(
    *,
    vehicle=None,
    nif="",
    period_start=None,
    period_end=None,
    actor=None,
    unpaid_ticket_count=None,
):
    start, end = _period_bounds(period_start, period_end)
    plate_number = normalize_plate_number(getattr(vehicle, "plate_number", ""))
    subject_nif = _get_subject_nif(vehicle, nif)
    reasons = []
    subject_drivers = []

    if subject_nif:
        subject_drivers = list(
            Driver.objects.annotate(normalized_nif=normalized_nif_expression())
            .filter(normalized_nif=subject_nif)
            .only("id", "dossier_number", "issue_date", "expires_at")
        )

    if vehicle is not None:
        if vehicle.registration_valid_until and vehicle.registration_valid_until < end:
            reasons.append(REASON_REGISTRATION_EXPIRED)

        latest_policy = vehicle.insurance_policies.order_by("-valid_until").first()
        if latest_policy and latest_policy.valid_until < end:
            reasons.append(REASON_INSURANCE_EXPIRED)

    if unpaid_ticket_count is None:
        unpaid_ticket_count = get_unpaid_valid_tickets_for_drivers(
            vehicle=vehicle,
            drivers=subject_drivers,
            period_start=start,
            period_end=end,
        ).count()
    if unpaid_ticket_count >= 2:
        reasons.append(REASON_UNPAID_TICKETS)

    valid_license_count = sum(
        1
        for driver in subject_drivers
        if driver.issue_date
        and driver.expires_at
        and driver.issue_date <= end
        and driver.expires_at >= start
    )
    if valid_license_count >= 2:
        reasons.append(REASON_MULTIPLE_LICENSES)

    if not reasons:
        return None, False

    key = _build_key(plate_number, subject_nif, start, end)
    description = " ; ".join(REASON_LABELS[reason] for reason in reasons)
    alert, created = Alert.objects.update_or_create(
        deduplication_key=key,
        defaults={
            "created_by": None,
            "alert_type": Alert.TYPE_JUDICIAL,
            "plate_number": plate_number,
            "description": description,
            "source": Alert.SOURCE_SYSTEM,
            "subject_nif": subject_nif,
            "system_reasons": reasons,
            "control_period_start": start,
            "control_period_end": end,
        },
    )
    log_action(actor, alert, "CREATE_AUTO" if created else "UPDATE_AUTO", {"reasons": reasons})
    return alert, created