from django.db import transaction

from .models import AuditLog
from .security import get_client_ip, sanitize_mapping


def get_actor_role(actor):
    if not actor or not getattr(actor, "is_authenticated", False):
        return ""

    try:
        profile = actor.agent_profile
    except Exception:
        return ""

    return str(getattr(profile, "role", "") or "")


def create_audit_log(
    *,
    actor=None,
    action,
    instance=None,
    request=None,
    payload=None,
    success=True,
    commit_on_success=True,
):
    actor_value = (
        actor
        if actor and getattr(actor, "is_authenticated", False)
        else None
    )

    app_label = ""
    model_name = ""
    object_id = ""
    object_repr = ""

    if instance is not None:
        meta = getattr(instance, "_meta", None)
        if meta is not None:
            app_label = str(meta.app_label)
            model_name = str(meta.model_name)

        pk = getattr(instance, "pk", None)
        object_id = str(pk) if pk is not None else ""
        object_repr = str(instance)[:255]

    request_id = ""
    request_method = ""
    request_path = ""
    ip_address = None
    user_agent = ""

    if request is not None:
        request_id = str(
            getattr(request, "request_id", "") or ""
        )[:64]
        request_method = str(
            getattr(request, "method", "") or ""
        )[:12]
        request_path = str(
            getattr(request, "path", "") or ""
        )[:500]
        ip_address = get_client_ip(request)
        user_agent = str(
            request.META.get("HTTP_USER_AGENT", "") or ""
        )[:500]

    values = {
        "actor": actor_value,
        "actor_email_snapshot": str(
            getattr(actor_value, "email", "") or ""
        ),
        "actor_role_snapshot": get_actor_role(actor_value),
        "action": action,
        "app_label": app_label,
        "model_name": model_name,
        "object_id": object_id,
        "object_repr": object_repr,
        "request_id": request_id,
        "request_method": request_method,
        "request_path": request_path,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "success": bool(success),
        "payload": sanitize_mapping(payload or {}),
    }

    def persist():
        return AuditLog.objects.create(**values)

    if commit_on_success:
        holder = {}

        def callback():
            holder["audit"] = persist()

        transaction.on_commit(callback)
        return holder

    return persist()


def log_action(
    user,
    instance,
    action,
    payload=None,
    request=None,
    success=True,
):
    """Compatibilité avec l'ancienne fonction `log_action`."""
    return create_audit_log(
        actor=user,
        instance=instance,
        action=action,
        request=request,
        payload=payload,
        success=success,
        commit_on_success=False,
    )
