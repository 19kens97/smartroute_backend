import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

from .consumers import user_alert_group
from .models import Alert
from .serializers import ALERT_SEVERITIES, ALERT_TYPE_LABELS

logger = logging.getLogger(__name__)


def get_alert_recipient_users(alert, creator=None):
    if alert.source != Alert.SOURCE_MANUAL or alert.alert_type == Alert.TYPE_JUDICIAL:
        return get_user_model().objects.none()

    users = get_user_model().objects.filter(is_active=True)
    if creator is not None:
        users = users.exclude(pk=creator.pk)
    return users.distinct()


def build_alert_created_event(alert):
    created_by = alert.created_by
    description = (alert.description or "").strip()
    return {
        "type": "alert.created",
        "version": 1,
        "data": {
            "id": alert.pk,
            "alert_type": alert.alert_type,
            "alert_type_display": ALERT_TYPE_LABELS.get(alert.alert_type, alert.alert_type),
            "plate_number": alert.plate_number,
            "severity": ALERT_SEVERITIES.get(alert.alert_type, "INFO"),
            "source": alert.source,
            "description_preview": description[:180],
            "created_by_name": (
                (created_by.get_full_name().strip() or created_by.username)
                if created_by is not None
                else None
            ),
            "created_at": alert.created_at.isoformat(),
        },
    }


def broadcast_alert_created(alert):
    recipients = get_alert_recipient_users(alert, alert.created_by)
    recipient_ids = list(recipients.values_list("id", flat=True))
    if not recipient_ids:
        logger.info("event=alert_event_skipped alert_id=%s recipient_count=0", alert.pk)
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.info("event=alert_event_skipped alert_id=%s reason=no_channel_layer", alert.pk)
        return

    payload = build_alert_created_event(alert)
    logger.info("event=alert_event_broadcast alert_id=%s recipient_count=%s", alert.pk, len(recipient_ids))
    for user_id in recipient_ids:
        async_to_sync(channel_layer.group_send)(
            user_alert_group(user_id),
            {"type": "alert.created", "payload": payload},
        )