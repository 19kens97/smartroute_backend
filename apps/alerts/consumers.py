from channels.generic.websocket import AsyncJsonWebsocketConsumer

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_SERVER_ERROR = 4500


def user_alert_group(user_id):
    return f"alerts.user.{user_id}"


class AlertConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        reason = self.scope.get("auth_error_reason")

        if not user or not user.is_authenticated:
            await self.close(
                code=WS_CLOSE_FORBIDDEN
                if reason == "forbidden"
                else WS_CLOSE_UNAUTHORIZED
            )
            return

        try:
            self.group_name = user_alert_group(user.pk)
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name,
            )
            await self.accept()
        except Exception:
            await self.close(code=WS_CLOSE_SERVER_ERROR)

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(
                group_name,
                self.channel_name,
            )

    async def receive_json(self, content, **kwargs):
        if len(str(content)) > 4096:
            await self.close(code=1009)

    async def alert_created(self, event):
        await self.send_json(event["payload"])
