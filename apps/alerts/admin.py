from django.contrib import admin

from .models import Alert, AlertEvidence


class AlertEvidenceInline(admin.TabularInline):
    model = AlertEvidence
    extra = 0
    readonly_fields = ("evidence_type", "file", "mime_type", "size_bytes", "duration_seconds", "created_by", "created_at")
    can_delete = False


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    inlines = [AlertEvidenceInline]


@admin.register(AlertEvidence)
class AlertEvidenceAdmin(admin.ModelAdmin):
    list_display = ("id", "alert", "evidence_type", "mime_type", "size_bytes", "created_by", "created_at")
    readonly_fields = ("created_at", "updated_at")