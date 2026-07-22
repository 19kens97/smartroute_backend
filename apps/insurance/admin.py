from django.contrib import admin

from .models import InsurancePolicy


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "vehicle",
        "insurer",
        "valid_from",
        "valid_until",
        "status",
        "is_currently_valid",
    )
    search_fields = (
        "policy_number",
        "insurer",
        "vehicle__plate_number",
        "vehicle__owner__full_name",
    )
    list_filter = (
        "status",
        "valid_until",
        "insurer",
    )
    autocomplete_fields = ("vehicle",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = (
        "-valid_until",
        "-id",
    )
