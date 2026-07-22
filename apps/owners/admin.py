from django.contrib import admin
from django.db.models import Count, Q

from .models import Owner, VehicleOwnership


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "nif",
        "phone",
        "is_active",
        "current_vehicle_count",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = (
        "person__nif",
        "person__first_name",
        "person__last_name",
        "phone",
    )
    readonly_fields = ("created_by", "created_at", "updated_at")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("person", "created_by")
            .annotate(
                _current_vehicle_count=Count(
                    "vehicle_ownerships",
                    filter=Q(
                        vehicle_ownerships__is_current=True
                    ),
                    distinct=True,
                )
            )
        )

    @admin.display(description="Véhicules actuels")
    def current_vehicle_count(self, obj):
        return obj._current_vehicle_count

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VehicleOwnership)
class VehicleOwnershipAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vehicle",
        "owner",
        "ownership_type",
        "start_date",
        "end_date",
        "is_current",
    )
    list_filter = (
        "ownership_type",
        "is_current",
        "start_date",
    )
    search_fields = (
        "owner__person__nif",
        "owner__person__first_name",
        "owner__person__last_name",
        "source_document_reference",
    )
    readonly_fields = (
        "created_by",
        "ended_by",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False
