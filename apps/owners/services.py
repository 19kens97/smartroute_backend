from django.db.models import Count, Q

from .models import Owner, VehicleOwnership


def owners_queryset():
    return (
        Owner.objects
        .select_related("person", "created_by")
        .annotate(
            current_vehicle_count=Count(
                "vehicle_ownerships",
                filter=Q(
                    vehicle_ownerships__is_current=True
                ),
                distinct=True,
            )
        )
    )


def filter_owners(queryset, params):
    if nif := params.get("nif"):
        queryset = queryset.filter(
            person__nif__icontains=nif.strip()
        )

    if name := params.get("name"):
        queryset = queryset.filter(
            Q(person__first_name__icontains=name.strip())
            | Q(person__last_name__icontains=name.strip())
        )

    if phone := params.get("phone"):
        queryset = queryset.filter(phone__icontains=phone.strip())

    if active := params.get("is_active"):
        normalized = active.strip().lower()
        if normalized in {"true", "1", "yes"}:
            queryset = queryset.filter(is_active=True)
        elif normalized in {"false", "0", "no"}:
            queryset = queryset.filter(is_active=False)

    if vehicle := params.get("vehicle"):
        queryset = queryset.filter(
            vehicle_ownerships__vehicle_id=vehicle,
            vehicle_ownerships__is_current=True,
        )

    if plate := params.get("plate_number"):
        queryset = queryset.filter(
            vehicle_ownerships__vehicle__plate_number__icontains=plate.strip(),
            vehicle_ownerships__is_current=True,
        )

    return queryset.distinct().order_by(
        "person__last_name",
        "person__first_name",
        "id",
    )


def ownerships_queryset():
    return (
        VehicleOwnership.objects
        .select_related(
            "vehicle",
            "owner",
            "owner__person",
            "created_by",
            "ended_by",
        )
    )


def filter_ownerships(queryset, params):
    if owner := params.get("owner"):
        queryset = queryset.filter(owner_id=owner)

    if vehicle := params.get("vehicle"):
        queryset = queryset.filter(vehicle_id=vehicle)

    if current := params.get("is_current"):
        normalized = current.strip().lower()
        if normalized in {"true", "1", "yes"}:
            queryset = queryset.filter(is_current=True)
        elif normalized in {"false", "0", "no"}:
            queryset = queryset.filter(is_current=False)

    if ownership_type := params.get("ownership_type"):
        queryset = queryset.filter(
            ownership_type=ownership_type.strip().upper()
        )

    return queryset.order_by("-is_current", "-start_date", "-id")
