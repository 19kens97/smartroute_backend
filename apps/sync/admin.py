from django.contrib import admin

from .models import SyncDevice, SyncItemLog, SyncSession


@admin.register(SyncDevice)
class SyncDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "device_uuid",
        "user",
        "device_name",
        "platform",
        "app_version",
        "is_active",
        "last_seen_at",
    )
    list_filter = (
        "platform",
        "is_active",
        "last_seen_at",
    )
    search_fields = (
        "device_uuid",
        "device_name",
        "user__email",
    )
    readonly_fields = (
        "device_uuid",
        "user",
        "last_seen_at",
        "revoked_at",
        "revoked_by",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SyncItemLogInline(admin.TabularInline):
    model = SyncItemLog
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "entity_type",
        "operation",
        "client_uuid",
        "server_id",
        "status",
        "error_code",
        "processed_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SyncSession)
class SyncSessionAdmin(admin.ModelAdmin):
    inlines = [SyncItemLogInline]
    list_display = (
        "request_uuid",
        "user",
        "device",
        "direction",
        "status",
        "item_count",
        "success_count",
        "failure_count",
        "conflict_count",
        "created_at",
    )
    list_filter = (
        "direction",
        "status",
        "created_at",
    )
    search_fields = (
        "request_uuid",
        "device__device_uuid",
        "user__email",
    )
    readonly_fields = (
        "request_uuid",
        "device",
        "user",
        "direction",
        "status",
        "cursor",
        "next_cursor",
        "item_count",
        "success_count",
        "failure_count",
        "conflict_count",
        "started_at",
        "completed_at",
        "error_code",
        "error_message",
        "payload_hash",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SyncItemLog)
class SyncItemLogAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "entity_type",
        "operation",
        "client_uuid",
        "server_id",
        "status",
        "error_code",
        "processed_at",
    )
    list_filter = (
        "entity_type",
        "operation",
        "status",
        "processed_at",
    )
    search_fields = (
        "session__request_uuid",
        "client_uuid",
        "server_id",
    )
    readonly_fields = (
        "session",
        "entity_type",
        "operation",
        "client_uuid",
        "server_id",
        "status",
        "base_version",
        "server_version",
        "error_code",
        "error_message",
        "payload_hash",
        "processed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
