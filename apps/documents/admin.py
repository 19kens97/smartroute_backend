from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "document_type",
        "vehicle",
        "uploaded_by",
        "original_filename",
        "created_at",
    )
    list_filter = ("document_type", "created_at")
    search_fields = (
        "title",
        "description",
        "original_filename",
        "vehicle__plate_number",
        "uploaded_by__email",
        "uploaded_by__person__first_name",
        "uploaded_by__person__last_name",
    )
    autocomplete_fields = ("vehicle", "uploaded_by")
    readonly_fields = (
        "original_filename",
        "mime_type",
        "size_bytes",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at", "-id")
