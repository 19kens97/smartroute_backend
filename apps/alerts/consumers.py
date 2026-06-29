import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_SERVER_ERROR = 4500


def user_alert_group(user_id):
    return f"alerts.user.{user_id}"


class AlertConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        logger.info("event=websocket_connect_started path=%s", self.scope.get("path", ""))
        if not user or not user.is_authenticated:
            reason = self.scope.get("auth_error_reason") or "missing_token"
            logger.info("event=websocket_rejected reason=%s", reason)
            await self.close(code=WS_CLOSE_UNAUTHORIZED)
            return
        if not user.is_active:
            logger.info("event=websocket_rejected reason=inactive_user user_id=%s", user.pk)
            await self.close(code=WS_CLOSE_FORBIDDEN)
            return

        try:
            self.group_name = user_alert_group(user.pk)
            logger.info("event=websocket_authenticated user_id=%s", user.pk)
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info("event=websocket_connected user_id=%s", user.pk)
        except Exception:
            logger.exception("event=websocket_rejected reason=server_error user_id=%s", getattr(user, "pk", None))
            await self.close(code=WS_CLOSE_SERVER_ERROR)

    async def disconnect(self, close_code):
        user = self.scope.get("user")
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)
        logger.info("event=websocket_disconnected user_id=%s code=%s", getattr(user, "pk", None), close_code)

    async def receive_json(self, content, **kwargs):
        if len(str(content)) > 4096:
            await self.close(code=1009)
            return
        logger.debug("Ignoring unsupported alert websocket client message.")

    async def alert_created(self, event):
        alert_id = event.get("payload", {}).get("data", {}).get("id")
        logger.info("event=alert_event_sent alert_id=%s", alert_id)
        await self.send_json(event["payload"])