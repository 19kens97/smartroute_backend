from django.contrib import admin

from .models import Driver


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = (
        "dossier_number",
        "person",
        "license_type",
        "issue_date",
        "expires_at",
    )
    list_filter = (
        "license_type",
        "sex",
        "blood_group",
        "expires_at",
    )
    search_fields = (
        "dossier_number",
        "person__nif",
        "person__first_name",
        "person__last_name",
    )
    autocomplete_fields = ("person",)
    readonly_fields = ("created_at", "updated_at")
    ordering = (
        "person__last_name",
        "person__first_name",
        "dossier_number",
    )
