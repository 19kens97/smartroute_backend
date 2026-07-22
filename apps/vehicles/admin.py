from django.contrib import admin

from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "plate_number",
        "owner",
        "brand",
        "model",
        "year",
        "registration_valid_until",
        "is_wanted",
    )
    list_filter = (
        "is_wanted",
        "brand",
        "year",
        "registration_valid_until",
    )
    search_fields = (
        "plate_number",
        "engine_number",
        "brand",
        "model",
        "owner__full_name",
    )
    autocomplete_fields = ("owner",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = (
        "-created_at",
        "-id",
    )
