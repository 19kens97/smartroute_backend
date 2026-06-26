import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


def user_alert_group(user_id):
    return f"alerts.user.{user_id}"


class AlertConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.is_active:
            await self.close(code=4401)
            return

        self.group_name = user_alert_group(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if len(str(content)) > 4096:
            await self.close(code=1009)
            return
        logger.debug("Ignoring unsupported alert websocket client message.")

    async def alert_created(self, event):
        await self.send_json(event["payload"])