from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

from apps.accounts.models import AgentProfile, User
from .consumers import user_alert_group


def professional_alert_recipients():
    return (
        get_user_model().objects.filter(
            is_active=True,
            account_type=User.AccountType.PROFESSIONAL,
            agent_profile__is_active=True,
            agent_profile__role__in={
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_TERRAIN,
                AgentProfile.Role.AGENT_SAISIE,
            },
        ).distinct()
    )


def get_alert_recipient_users(alert, creator=None):
    users = professional_alert_recipients()
    if creator is not None:
        users = users.exclude(pk=creator.pk)
    return users


def _display_name(user):
    if user is None:
        return None
    person = getattr(user, "person", None)
    return getattr(person, "full_name", "") or user.email or user.username


def build_alert_created_event(alert):
    return {
        "type": "alert.created",
        "version": 2,
        "data": {
            "id": alert.pk,
            "alert_type": alert.alert_type,
            "alert_type_display": alert.get_alert_type_display(),
            "plate_number": alert.plate_number,
            "severity": alert.severity,
            "status": alert.status,
            "source": alert.source,
            "description_preview": (alert.description or "").strip()[:180],
            "created_by_name": _display_name(alert.created_by),
            "created_at": alert.created_at.isoformat(),
        },
    }


def broadcast_alert_created(alert):
    recipient_ids = list(
        get_alert_recipient_users(
            alert,
            alert.created_by,
        ).values_list("id", flat=True)
    )

    channel_layer = get_channel_layer()
    if not recipient_ids or channel_layer is None:
        return

    payload = build_alert_created_event(alert)

    for user_id in recipient_ids:
        async_to_sync(channel_layer.group_send)(
            user_alert_group(user_id),
            {"type": "alert.created", "payload": payload},
        )
