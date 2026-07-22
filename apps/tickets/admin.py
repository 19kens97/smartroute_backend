from django.contrib import admin

from .models import Ticket, TicketInfraction, TicketProof, TicketVerbalization


class TicketVerbalizationInline(admin.TabularInline):
    model = TicketVerbalization
    extra = 0
    can_delete = False
    readonly_fields = (
        "sequence_number",
        "agent",
        "vehicle",
        "plate_number_snapshot",
        "occurred_at",
        "location_label",
        "latitude",
        "longitude",
        "note",
        "status",
        "cancelled_at",
        "cancelled_by",
        "cancellation_reason",
        "created_at",
    )


class TicketInfractionInline(admin.TabularInline):
    model = TicketInfraction
    extra = 0
    can_delete = False
    readonly_fields = (
        "infraction",
        "code_snapshot",
        "label_snapshot",
        "article_snapshot",
        "penalty_type_snapshot",
        "amount_snapshot",
        "minimum_amount_snapshot",
        "maximum_amount_snapshot",
        "amount_options_snapshot",
        "penalty_text_snapshot",
        "currency_snapshot",
    )


class TicketProofInline(admin.TabularInline):
    model = TicketProof
    extra = 0
    can_delete = False
    readonly_fields = (
        "file",
        "evidence_type",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
        "duration_seconds",
        "caption",
        "created_by",
        "created_at",
    )


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    inlines = [TicketVerbalizationInline]
    list_display = (
        "ticket_number",
        "driver_dossier_snapshot",
        "driver_name_snapshot",
        "status",
        "pricing_status",
        "sync_status",
        "opened_by",
        "opened_at",
    )
    list_filter = (
        "status",
        "pricing_status",
        "sync_status",
        "opened_at",
    )
    search_fields = (
        "ticket_number",
        "barcode_value",
        "driver_dossier_snapshot",
        "driver_name_snapshot",
        "driver_nif_snapshot",
        "verbalizations__plate_number_snapshot",
    )
    readonly_fields = (
        "ticket_number",
        "barcode_value",
        "client_uuid",
        "opened_by",
        "opened_at",
        "closed_at",
        "closed_by",
        "cancelled_at",
        "cancelled_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("driver",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketVerbalization)
class TicketVerbalizationAdmin(admin.ModelAdmin):
    inlines = [TicketInfractionInline, TicketProofInline]
    list_display = (
        "ticket",
        "sequence_number",
        "agent",
        "plate_number_snapshot",
        "status",
        "occurred_at",
    )
    list_filter = ("status", "occurred_at")
    search_fields = (
        "ticket__ticket_number",
        "plate_number_snapshot",
        "location_label",
    )
    readonly_fields = (
        "ticket",
        "sequence_number",
        "agent",
        "client_uuid",
        "cancelled_at",
        "cancelled_by",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketInfraction)
class TicketInfractionAdmin(admin.ModelAdmin):
    list_display = (
        "verbalization",
        "code_snapshot",
        "penalty_type_snapshot",
        "currency_snapshot",
    )
    readonly_fields = (
        "verbalization",
        "infraction",
        "code_snapshot",
        "label_snapshot",
        "article_snapshot",
        "penalty_type_snapshot",
        "amount_snapshot",
        "minimum_amount_snapshot",
        "maximum_amount_snapshot",
        "amount_options_snapshot",
        "penalty_text_snapshot",
        "currency_snapshot",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketProof)
class TicketProofAdmin(admin.ModelAdmin):
    list_display = (
        "verbalization",
        "evidence_type",
        "mime_type",
        "size_bytes",
        "created_by",
        "created_at",
    )
    readonly_fields = (
        "verbalization",
        "file",
        "evidence_type",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
        "duration_seconds",
        "caption",
        "created_by",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False
