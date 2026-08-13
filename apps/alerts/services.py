from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services import log_action
from apps.insurance.models import InsurancePolicy
from apps.tickets.services import get_unpaid_valid_tickets_for_drivers
from apps.vehicles.models import normalize_plate_number

from .models import Alert
from .realtime import broadcast_alert_created


EXPIRY_WARNING_DAYS = 30

REASON_REGISTRATION_EXPIRED = "REGISTRATION_EXPIRED"
REASON_INSURANCE_EXPIRED = "INSURANCE_EXPIRED"
REASON_UNPAID_TICKETS = "MULTIPLE_VALID_UNPAID_TICKETS"
REASON_DRIVER_LICENSE_EXPIRING = "DRIVER_LICENSE_EXPIRING_SOON"
REASON_REGISTRATION_EXPIRING = "REGISTRATION_EXPIRING_SOON"
REASON_INSURANCE_EXPIRING = "INSURANCE_EXPIRING_SOON"

REASON_LABELS = {
    REASON_REGISTRATION_EXPIRED: "Immatriculation expirée",
    REASON_INSURANCE_EXPIRED: "Aucune assurance valide",
    REASON_UNPAID_TICKETS: "Au moins deux tickets valides et non payés",
    REASON_DRIVER_LICENSE_EXPIRING: "Le permis expire dans moins de 30 jours",
    REASON_REGISTRATION_EXPIRING: "L'immatriculation expire dans moins de 30 jours",
    REASON_INSURANCE_EXPIRING: "L'assurance expire dans moins de 30 jours",
}


def _period_bounds(period_start=None, period_end=None):
    today = timezone.localdate()
    start = period_start or today
    end = period_end or start

    if end < start:
        raise ValueError(
            "La fin de la période ne peut pas précéder son début."
        )

    return start, end


def _is_expiring_soon(expiry_date, *, today, days):
    return bool(
        expiry_date
        and today <= expiry_date <= today + timedelta(days=days)
    )


def _owner_nif(vehicle):
    owner = getattr(vehicle, "owner", None)
    if owner is None:
        return ""

    person = getattr(owner, "person", None)
    if person is not None:
        return person.nif or ""

    return getattr(owner, "nif", "") or ""


def expire_field_alerts(*, now=None, actor=None):
    now = now or timezone.now()

    alerts = Alert.objects.filter(
        category=Alert.Category.FIELD_REPORT,
        status=Alert.Status.ACTIVE,
        expires_at__isnull=False,
        expires_at__lte=now,
    )

    updated = 0

    for alert in alerts.iterator():
        alert.status = Alert.Status.EXPIRED
        alert.resolved_at = now
        alert.resolved_by = actor
        alert.resolution_note = (
            "Expiration automatique après six heures."
        )
        alert.save(
            update_fields=(
                "status",
                "resolved_at",
                "resolved_by",
                "resolution_note",
                "updated_at",
            )
        )
        log_action(
            actor,
            alert,
            "EXPIRE_AUTO",
            {"expires_at": alert.expires_at.isoformat()},
        )
        updated += 1

    return updated


def _upsert_system_alert(
    *,
    key,
    alert_type,
    severity,
    description,
    reasons,
    vehicle=None,
    driver=None,
    document_expires_on=None,
    actor=None,
):
    subject_person = getattr(driver, "person", None)
    subject_nif = (
        getattr(subject_person, "nif", "")
        or _owner_nif(vehicle)
    )
    plate_number = normalize_plate_number(
        getattr(vehicle, "plate_number", "")
    )

    if actor is not None:
        key = f"PERSONAL:{actor.pk}:{key}"

    alert, created = Alert.objects.update_or_create(
        deduplication_key=key,
        defaults={
            "created_by": actor,
            "category": Alert.Category.AUTOMATIC,
            "alert_type": alert_type,
            "severity": severity,
            "status": Alert.Status.ACTIVE,
            "source": Alert.Source.SYSTEM,
            "vehicle": vehicle,
            "plate_number": plate_number,
            "subject_person": subject_person,
            "subject_nif": subject_nif,
            "description": description,
            "system_reasons": reasons,
            "document_expires_on": document_expires_on,
            "expires_at": None,
            "resolved_at": None,
            "resolved_by": None,
            "resolution_note": "",
        },
    )

    log_action(
        actor,
        alert,
        "CREATE_AUTO" if created else "UPDATE_AUTO",
        {"reasons": reasons},
    )

    if created and actor is None:
        transaction.on_commit(
            lambda alert_id=alert.pk: broadcast_alert_created(
                Alert.objects.select_related(
                    "created_by",
                    "created_by__person",
                ).get(pk=alert_id)
            )
        )

    return alert, created


@transaction.atomic
def evaluate_document_expiry_warnings(
    *,
    driver=None,
    vehicle=None,
    actor=None,
    today=None,
    warning_days=EXPIRY_WARNING_DAYS,
):
    today = today or timezone.localdate()
    warnings = []

    if driver and _is_expiring_soon(
        driver.expires_at,
        today=today,
        days=warning_days,
    ):
        warnings.append(
            _upsert_system_alert(
                key=(
                    f"EXPIRY:DRIVER:{driver.pk}:"
                    f"{driver.expires_at.isoformat()}"
                ),
                alert_type=Alert.AlertType.DOCUMENT_EXPIRY_WARNING,
                severity=Alert.Severity.WARNING,
                description=(
                    "Le permis de conduire arrive bientôt à expiration "
                    f"le {driver.expires_at.isoformat()}."
                ),
                reasons=[REASON_DRIVER_LICENSE_EXPIRING],
                driver=driver,
                document_expires_on=driver.expires_at,
                actor=actor,
            )[0]
        )

    if vehicle and _is_expiring_soon(
        vehicle.registration_valid_until,
        today=today,
        days=warning_days,
    ):
        warnings.append(
            _upsert_system_alert(
                key=(
                    f"EXPIRY:REGISTRATION:{vehicle.pk}:"
                    f"{vehicle.registration_valid_until.isoformat()}"
                ),
                alert_type=Alert.AlertType.DOCUMENT_EXPIRY_WARNING,
                severity=Alert.Severity.WARNING,
                description=(
                    "L'immatriculation arrive bientôt à expiration "
                    f"le {vehicle.registration_valid_until.isoformat()}."
                ),
                reasons=[REASON_REGISTRATION_EXPIRING],
                vehicle=vehicle,
                document_expires_on=vehicle.registration_valid_until,
                actor=actor,
            )[0]
        )

    if vehicle:
        active_policy = (
            vehicle.insurance_policies.filter(
                status=InsurancePolicy.Status.VALID,
                valid_until__gte=today,
            )
            .filter(
                Q(valid_from__isnull=True)
                | Q(valid_from__lte=today)
            )
            .order_by("-valid_until", "-id")
            .first()
        )

        if active_policy and _is_expiring_soon(
            active_policy.valid_until,
            today=today,
            days=warning_days,
        ):
            warnings.append(
                _upsert_system_alert(
                    key=(
                        f"EXPIRY:INSURANCE:{active_policy.pk}:"
                        f"{active_policy.valid_until.isoformat()}"
                    ),
                    alert_type=Alert.AlertType.DOCUMENT_EXPIRY_WARNING,
                    severity=Alert.Severity.WARNING,
                    description=(
                        f"La police {active_policy.policy_number} arrive "
                        f"bientôt à expiration le "
                        f"{active_policy.valid_until.isoformat()}."
                    ),
                    reasons=[REASON_INSURANCE_EXPIRING],
                    vehicle=vehicle,
                    document_expires_on=active_policy.valid_until,
                    actor=actor,
                )[0]
            )

    return warnings


@transaction.atomic
def evaluate_judicial_alert(
    *,
    vehicle=None,
    driver=None,
    period_start=None,
    period_end=None,
    actor=None,
    unpaid_ticket_count=None,
):
    start, end = _period_bounds(period_start, period_end)
    reasons = []
    drivers = [driver] if driver else []

    if vehicle is not None:
        if (
            vehicle.registration_valid_until
            and vehicle.registration_valid_until < end
        ):
            reasons.append(REASON_REGISTRATION_EXPIRED)

        has_valid_policy = (
            vehicle.insurance_policies.filter(
                status=InsurancePolicy.Status.VALID,
                valid_until__gte=end,
            )
            .filter(
                Q(valid_from__isnull=True)
                | Q(valid_from__lte=start)
            )
            .exists()
        )

        if not has_valid_policy:
            reasons.append(REASON_INSURANCE_EXPIRED)

    if unpaid_ticket_count is None:
        unpaid_ticket_count = get_unpaid_valid_tickets_for_drivers(
            vehicle=vehicle,
            drivers=drivers,
            period_start=start,
            period_end=end,
        ).count()

    if unpaid_ticket_count >= 2:
        reasons.append(REASON_UNPAID_TICKETS)

    if not reasons:
        return None, False

    subject = (
        f"VEHICLE:{vehicle.pk}"
        if vehicle
        else f"DRIVER:{driver.pk}"
        if driver
        else "UNKNOWN"
    )
    key = (
        f"JUDICIAL:{subject}:"
        f"{start.isoformat()}:{end.isoformat()}"
    )

    if actor is not None:
        key = f"PERSONAL:{actor.pk}:{key}"

    alert, created = Alert.objects.update_or_create(
        deduplication_key=key,
        defaults={
            "created_by": actor,
            "category": Alert.Category.AUTOMATIC,
            "alert_type": Alert.AlertType.JUDICIAL,
            "severity": Alert.Severity.CRITICAL,
            "status": Alert.Status.ACTIVE,
            "source": Alert.Source.SYSTEM,
            "vehicle": vehicle,
            "plate_number": normalize_plate_number(
                getattr(vehicle, "plate_number", "")
            ),
            "subject_person": getattr(driver, "person", None),
            "subject_nif": (
                getattr(
                    getattr(driver, "person", None),
                    "nif",
                    "",
                )
                or _owner_nif(vehicle)
            ),
            "description": " ; ".join(
                REASON_LABELS[reason]
                for reason in reasons
            ),
            "system_reasons": reasons,
            "control_period_start": start,
            "control_period_end": end,
            "document_expires_on": None,
            "expires_at": None,
        },
    )

    log_action(
        actor,
        alert,
        "CREATE_AUTO" if created else "UPDATE_AUTO",
        {"reasons": reasons},
    )

    return alert, created
