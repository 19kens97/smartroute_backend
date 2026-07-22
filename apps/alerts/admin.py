from django.contrib import admin

from .models import Alert, AlertEvidence, AlertReceipt


class AlertEvidenceInline(admin.TabularInline):
    model = AlertEvidence
    extra = 0
    can_delete = False
    readonly_fields = (
        "evidence_type",
        "file",
        "mime_type",
        "size_bytes",
        "duration_seconds",
        "checksum_sha256",
        "created_by",
        "created_at",
    )


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    inlines = [AlertEvidenceInline]
    list_display = (
        "id",
        "category",
        "alert_type",
        "severity",
        "status",
        "source",
        "plate_number",
        "created_by",
        "expires_at",
        "created_at",
    )
    list_filter = (
        "category",
        "alert_type",
        "severity",
        "status",
        "source",
        "created_at",
    )
    search_fields = (
        "plate_number",
        "subject_nif",
        "description",
        "resolution_note",
        "deduplication_key",
    )
    readonly_fields = (
        "category",
        "source",
        "severity",
        "deduplication_key",
        "system_reasons",
        "resolved_at",
        "resolved_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = (
        "vehicle",
        "subject_person",
        "created_by",
    )
    ordering = (
        "-created_at",
        "-id",
    )


@admin.register(AlertEvidence)
class AlertEvidenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "alert",
        "evidence_type",
        "mime_type",
        "size_bytes",
        "created_by",
        "created_at",
    )
    readonly_fields = (
        "alert",
        "evidence_type",
        "file",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
        "duration_seconds",
        "created_by",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(AlertReceipt)
class AlertReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "alert",
        "user",
        "opened_at",
    )
    readonly_fields = (
        "alert",
        "user",
        "opened_at",
        "created_at",
        "updated_at",
    )
