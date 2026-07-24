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

def set_current_vehicle_owner(
    *,
    vehicle,
    owner,
    ownership_type=None,
    start_date=None,
    source_document_reference="",
    note="",
    created_by=None,
):
    """Set the official current owner and keep Vehicle.owner in sync."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.utils import timezone

    if vehicle is None:
        raise ValidationError({"vehicle": "Le vehicule est obligatoire."})
    if owner is None:
        raise ValidationError({"owner": "Le proprietaire est obligatoire."})
    if not owner.is_active:
        raise ValidationError({"owner": "Le proprietaire doit etre actif."})

    start_date = start_date or timezone.localdate()
    ownership_type = ownership_type or VehicleOwnership.OwnershipType.FULL_OWNER
    source_document_reference = VehicleOwnership.normalize_text(source_document_reference)
    note = str(note or "").strip()

    with transaction.atomic():
        vehicle_model = vehicle.__class__
        locked_vehicle = vehicle_model.objects.select_for_update().get(pk=vehicle.pk)
        current = (
            VehicleOwnership.objects
            .select_for_update()
            .filter(vehicle=locked_vehicle, is_current=True)
            .first()
        )

        if current and current.owner_id == owner.id:
            if locked_vehicle.owner_id != owner.id:
                locked_vehicle.owner = owner
                locked_vehicle.save(update_fields=("owner", "updated_at"))
            return current

        if current:
            if start_date < current.start_date:
                raise ValidationError(
                    {
                        "start_date": (
                            "La nouvelle propriete ne peut pas commencer "
                            "avant la propriete actuelle."
                        )
                    }
                )
            current.is_current = False
            current.end_date = start_date
            current.ended_by = created_by
            current.save()

        ownership = VehicleOwnership.objects.create(
            vehicle=locked_vehicle,
            owner=owner,
            ownership_type=ownership_type,
            start_date=start_date,
            end_date=None,
            is_current=True,
            source_document_reference=source_document_reference,
            note=note,
            created_by=created_by,
        )

        if locked_vehicle.owner_id != owner.id:
            locked_vehicle.owner = owner
            locked_vehicle.save(update_fields=("owner", "updated_at"))

        return ownership

