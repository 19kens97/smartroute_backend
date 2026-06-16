from .models import AuditLog

def log_action(user, instance, action, payload=None):
    AuditLog.objects.create(actor=user if getattr(user, "is_authenticated", False) else None, model_name=instance.__class__.__name__, object_id=str(instance.pk), action=action, payload=payload or {})
