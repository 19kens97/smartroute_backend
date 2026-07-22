from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "actor",
        "actor_role_snapshot",
        "action",
        "app_label",
        "model_name",
        "object_id",
        "success",
        "created_at",
    )
    list_filter = (
        "action",
        "success",
        "app_label",
        "model_name",
        "created_at",
    )
    search_fields = (
        "actor__email",
        "actor_email_snapshot",
        "request_id",
        "object_id",
        "object_repr",
    )
    date_hierarchy = "created_at"
    readonly_fields = (
        "actor",
        "actor_email_snapshot",
        "actor_role_snapshot",
        "action",
        "app_label",
        "model_name",
        "object_id",
        "object_repr",
        "request_id",
        "request_method",
        "request_path",
        "ip_address",
        "user_agent",
        "success",
        "payload",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
