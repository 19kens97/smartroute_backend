from datetime import datetime, time

from django.db.models import (
    CharField,
    Count,
    DateTimeField,
    F,
    Max,
    Min,
    OuterRef,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.models import AgentProfile, User
from apps.delits.models import DelitAction, DelitCase
from apps.tickets.models import (
    Ticket,
    TicketInfraction,
    TicketProof,
    TicketVerbalization,
)


def parse_date_range(params, *, start_key, end_key):
    start_value = params.get(start_key)
    end_value = params.get(end_key)

    start_date = parse_date(start_value) if start_value else None
    end_date = parse_date(end_value) if end_value else None

    if start_value and start_date is None:
        raise ValueError(f"{start_key} doit être une date au format YYYY-MM-DD.")

    if end_value and end_date is None:
        raise ValueError(f"{end_key} doit être une date au format YYYY-MM-DD.")

    if start_date and end_date and end_date < start_date:
        raise ValueError("La date de fin ne peut pas précéder la date de début.")

    current_tz = timezone.get_current_timezone()

    start_dt = (
        timezone.make_aware(datetime.combine(start_date, time.min), current_tz)
        if start_date
        else None
    )
    end_dt = (
        timezone.make_aware(datetime.combine(end_date, time.max), current_tz)
        if end_date
        else None
    )
    return start_dt, end_dt


def user_full_name_expression(prefix):
    return Coalesce(
        Concat(
            F(f"{prefix}__person__first_name"),
            Value(" "),
            F(f"{prefix}__person__last_name"),
            output_field=CharField(),
        ),
        F(f"{prefix}__email"),
        Value(""),
        output_field=CharField(),
    )


def get_ticket_report_queryset(params):
    latest_verbalization = (
        TicketVerbalization.objects
        .filter(ticket_id=OuterRef("pk"))
        .order_by("-sequence_number", "-id")
    )

    queryset = (
        Ticket.objects
        .select_related("driver", "opened_by", "opened_by__person")
        .annotate(
            verbalization_count=Count(
                "verbalizations",
                filter=Q(
                    verbalizations__status=TicketVerbalization.Status.ACTIVE
                ),
                distinct=True,
            ),
            first_verbalization_at=Min(
                "verbalizations__occurred_at",
                filter=Q(
                    verbalizations__status=TicketVerbalization.Status.ACTIVE
                ),
            ),
            last_verbalization_at=Max(
                "verbalizations__occurred_at",
                filter=Q(
                    verbalizations__status=TicketVerbalization.Status.ACTIVE
                ),
            ),
            last_plate_number=Coalesce(
                Subquery(
                    latest_verbalization.values("plate_number_snapshot")[:1],
                    output_field=CharField(),
                ),
                Value(""),
            ),
            last_location_label=Coalesce(
                Subquery(
                    latest_verbalization.values("location_label")[:1],
                    output_field=CharField(),
                ),
                Value(""),
            ),
            opened_by_name=user_full_name_expression("opened_by"),
        )
        .order_by("-opened_at", "-id")
    )

    if status := params.get("status"):
        queryset = queryset.filter(status=status.strip().upper())

    if pricing_status := params.get("pricing_status"):
        queryset = queryset.filter(
            pricing_status=pricing_status.strip().upper()
        )

    if ticket_number := params.get("ticket_number"):
        queryset = queryset.filter(
            ticket_number__icontains=ticket_number.strip()
        )

    if dossier_number := params.get("dossier_number"):
        queryset = queryset.filter(
            driver_dossier_snapshot__icontains=dossier_number.strip()
        )

    if nif := params.get("nif"):
        queryset = queryset.filter(
            driver_nif_snapshot__icontains=nif.strip()
        )

    if driver := params.get("driver"):
        queryset = queryset.filter(driver_id=driver)

    if opened_by := params.get("opened_by"):
        queryset = queryset.filter(opened_by_id=opened_by)

    if plate_number := params.get("plate_number"):
        queryset = queryset.filter(
            verbalizations__plate_number_snapshot__icontains=plate_number.strip()
        ).distinct()

    start_dt, end_dt = parse_date_range(
        params,
        start_key="opened_from",
        end_key="opened_to",
    )
    if start_dt:
        queryset = queryset.filter(opened_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(opened_at__lte=end_dt)

    return queryset


def serialize_ticket_row(ticket):
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "barcode_value": ticket.barcode_value,
        "driver_id": ticket.driver_id,
        "driver_dossier_snapshot": ticket.driver_dossier_snapshot,
        "driver_name_snapshot": ticket.driver_name_snapshot,
        "driver_nif_snapshot": ticket.driver_nif_snapshot,
        "status": ticket.status,
        "sync_status": ticket.sync_status,
        "pricing_status": ticket.pricing_status,
        "opened_at": ticket.opened_at,
        "opened_by_id": ticket.opened_by_id,
        "opened_by_name": ticket.opened_by_name.strip(),
        "verbalization_count": ticket.verbalization_count,
        "first_verbalization_at": ticket.first_verbalization_at,
        "last_verbalization_at": ticket.last_verbalization_at,
        "last_plate_number": ticket.last_plate_number,
        "last_location_label": ticket.last_location_label,
    }


def get_verbalization_report_queryset(params):
    queryset = (
        TicketVerbalization.objects
        .select_related(
            "ticket",
            "agent",
            "agent__person",
            "agent__agent_profile",
            "vehicle",
        )
        .annotate(
            infraction_count=Count("infractions", distinct=True),
            proof_count=Count("proofs", distinct=True),
            agent_name=user_full_name_expression("agent"),
        )
        .order_by("-occurred_at", "-id")
    )

    if ticket_number := params.get("ticket_number"):
        queryset = queryset.filter(
            ticket__ticket_number__icontains=ticket_number.strip()
        )

    if agent := params.get("agent"):
        queryset = queryset.filter(agent_id=agent)

    if status := params.get("status"):
        queryset = queryset.filter(status=status.strip().upper())

    if dossier_number := params.get("dossier_number"):
        queryset = queryset.filter(
            ticket__driver_dossier_snapshot__icontains=dossier_number.strip()
        )

    if plate_number := params.get("plate_number"):
        queryset = queryset.filter(
            plate_number_snapshot__icontains=plate_number.strip()
        )

    if location := params.get("location"):
        queryset = queryset.filter(location_label__icontains=location.strip())

    start_dt, end_dt = parse_date_range(
        params,
        start_key="occurred_from",
        end_key="occurred_to",
    )
    if start_dt:
        queryset = queryset.filter(occurred_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(occurred_at__lte=end_dt)

    return queryset


def serialize_verbalization_row(item):
    profile = getattr(item.agent, "agent_profile", None)
    return {
        "id": item.id,
        "ticket_id": item.ticket_id,
        "ticket_number": item.ticket.ticket_number,
        "sequence_number": item.sequence_number,
        "agent_id": item.agent_id,
        "agent_name": item.agent_name.strip(),
        "agent_badge_number": getattr(profile, "badge_number", "") or "",
        "driver_dossier_snapshot": item.ticket.driver_dossier_snapshot,
        "driver_name_snapshot": item.ticket.driver_name_snapshot,
        "vehicle_id": item.vehicle_id,
        "plate_number_snapshot": item.plate_number_snapshot,
        "occurred_at": item.occurred_at,
        "location_label": item.location_label,
        "status": item.status,
        "infraction_count": item.infraction_count,
        "proof_count": item.proof_count,
    }


def get_infraction_report_queryset(params):
    queryset = (
        TicketInfraction.objects
        .values(
            "code_snapshot",
            "label_snapshot",
            "article_snapshot",
            "penalty_type_snapshot",
            "currency_snapshot",
        )
        .annotate(
            observation_count=Count("id"),
            ticket_count=Count("verbalization__ticket_id", distinct=True),
            verbalization_count=Count("verbalization_id", distinct=True),
            last_observed_at=Max("verbalization__occurred_at"),
        )
        .order_by("-observation_count", "code_snapshot")
    )

    if code := params.get("code"):
        queryset = queryset.filter(code_snapshot__icontains=code.strip())

    if penalty_type := params.get("penalty_type"):
        queryset = queryset.filter(
            penalty_type_snapshot=penalty_type.strip().upper()
        )

    if ticket_number := params.get("ticket_number"):
        queryset = queryset.filter(
            verbalization__ticket__ticket_number__icontains=ticket_number.strip()
        )

    if agent := params.get("agent"):
        queryset = queryset.filter(verbalization__agent_id=agent)

    start_dt, end_dt = parse_date_range(
        params,
        start_key="observed_from",
        end_key="observed_to",
    )
    if start_dt:
        queryset = queryset.filter(
            verbalization__occurred_at__gte=start_dt
        )
    if end_dt:
        queryset = queryset.filter(
            verbalization__occurred_at__lte=end_dt
        )

    return queryset


def serialize_infraction_row(item):
    return {
        "code": item["code_snapshot"],
        "label": item["label_snapshot"],
        "article": item["article_snapshot"],
        "penalty_type": item["penalty_type_snapshot"],
        "currency": item["currency_snapshot"],
        "observation_count": item["observation_count"],
        "ticket_count": item["ticket_count"],
        "verbalization_count": item["verbalization_count"],
        "last_observed_at": item["last_observed_at"],
    }


def get_delit_report_queryset(params):
    queryset = (
        DelitCase.objects
        .select_related(
            "delit_type",
            "detected_by",
            "detected_by__person",
        )
        .annotate(
            evidence_count=Count("evidence", distinct=True),
            action_count=Count("actions", distinct=True),
            detected_by_name=user_full_name_expression("detected_by"),
        )
        .order_by("-detected_at", "-id")
    )

    if qualification_status := params.get("qualification_status"):
        queryset = queryset.filter(
            qualification_status=qualification_status.strip().upper()
        )

    if procedure_status := params.get("procedure_status"):
        queryset = queryset.filter(
            procedure_status=procedure_status.strip().upper()
        )

    if source_type := params.get("source_type"):
        queryset = queryset.filter(source_type=source_type.strip().upper())

    if delit_type := params.get("delit_type"):
        queryset = queryset.filter(delit_type_id=delit_type)

    if detected_by := params.get("detected_by"):
        queryset = queryset.filter(detected_by_id=detected_by)

    if driver := params.get("driver"):
        queryset = queryset.filter(driver_id=driver)

    if vehicle := params.get("vehicle"):
        queryset = queryset.filter(vehicle_id=vehicle)

    if ticket := params.get("ticket"):
        queryset = queryset.filter(ticket_id=ticket)

    start_dt, end_dt = parse_date_range(
        params,
        start_key="detected_from",
        end_key="detected_to",
    )
    if start_dt:
        queryset = queryset.filter(detected_at__gte=start_dt)
    if end_dt:
        queryset = queryset.filter(detected_at__lte=end_dt)

    return queryset


def serialize_delit_row(item):
    return {
        "id": item.id,
        "case_number": item.case_number,
        "delit_type_code": item.delit_type.code,
        "delit_type_label": item.delit_type.label,
        "source_type": item.source_type,
        "qualification_status": item.qualification_status,
        "procedure_status": item.procedure_status,
        "driver_id": item.driver_id,
        "vehicle_id": item.vehicle_id,
        "ticket_id": item.ticket_id,
        "verbalization_id": item.verbalization_id,
        "scan_id": item.scan_id,
        "detected_at": item.detected_at,
        "detected_by_id": item.detected_by_id,
        "detected_by_name": item.detected_by_name.strip(),
        "location_label": item.location_label,
        "evidence_count": item.evidence_count,
        "action_count": item.action_count,
    }


def get_agent_report_queryset(params):
    queryset = (
        User.objects
        .filter(
            account_type=User.AccountType.PROFESSIONAL,
            agent_profile__isnull=False,
        )
        .select_related("person", "agent_profile")
        .annotate(
            tickets_opened=Count("opened_tickets", distinct=True),
            verbalizations_created=Count(
                "ticket_verbalizations",
                distinct=True,
            ),
            proofs_added=Count("ticket_proofs", distinct=True),
            delit_cases_created=Count(
                "detected_delit_cases",
                distinct=True,
            ),
            delit_actions_recorded=Count(
                "delit_actions",
                distinct=True,
            ),
        )
        .order_by(
            "-verbalizations_created",
            "-delit_cases_created",
            "id",
        )
    )

    if role := params.get("role"):
        queryset = queryset.filter(
            agent_profile__role=role.strip().upper()
        )

    if badge_number := params.get("badge_number"):
        queryset = queryset.filter(
            agent_profile__badge_number__icontains=badge_number.strip()
        )

    if active := params.get("active"):
        normalized = active.strip().lower()
        if normalized in {"true", "1", "yes"}:
            queryset = queryset.filter(
                is_active=True,
                agent_profile__is_active=True,
            )
        elif normalized in {"false", "0", "no"}:
            queryset = queryset.filter(
                Q(is_active=False)
                | Q(agent_profile__is_active=False)
            )

    return queryset


def serialize_agent_row(user):
    person = getattr(user, "person", None)
    profile = getattr(user, "agent_profile", None)
    full_name = (
        getattr(person, "full_name", "")
        or user.get_full_name()
        or user.email
        or user.username
    )

    return {
        "user_id": user.id,
        "full_name": full_name,
        "email": user.email,
        "badge_number": getattr(profile, "badge_number", "") or "",
        "role": getattr(profile, "role", "") or "",
        "tickets_opened": user.tickets_opened,
        "verbalizations_created": user.verbalizations_created,
        "proofs_added": user.proofs_added,
        "delit_cases_created": user.delit_cases_created,
        "delit_actions_recorded": user.delit_actions_recorded,
    }


def build_summary(params):
    ticket_qs = get_ticket_report_queryset(params)
    verbalization_qs = get_verbalization_report_queryset(params)
    delit_qs = get_delit_report_queryset(params)

    return {
        "tickets": {
            "total": ticket_qs.count(),
            "open": ticket_qs.filter(status=Ticket.Status.OPEN).count(),
            "closed": ticket_qs.filter(status=Ticket.Status.CLOSED).count(),
            "cancelled": ticket_qs.filter(status=Ticket.Status.CANCELLED).count(),
        },
        "verbalizations": {
            "total": verbalization_qs.count(),
            "active": verbalization_qs.filter(
                status=TicketVerbalization.Status.ACTIVE
            ).count(),
            "cancelled": verbalization_qs.filter(
                status=TicketVerbalization.Status.CANCELLED
            ).count(),
        },
        "delits": {
            "total": delit_qs.count(),
            "potential": delit_qs.filter(
                qualification_status=DelitCase.QualificationStatus.POTENTIAL
            ).count(),
            "under_review": delit_qs.filter(
                qualification_status=DelitCase.QualificationStatus.UNDER_REVIEW
            ).count(),
            "confirmed": delit_qs.filter(
                qualification_status=DelitCase.QualificationStatus.CONFIRMED
            ).count(),
            "rejected": delit_qs.filter(
                qualification_status=DelitCase.QualificationStatus.REJECTED
            ).count(),
        },
    }
