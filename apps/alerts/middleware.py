import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        user, reason = await self._authenticate(scope)
        scope["user"] = user
        scope["auth_error_reason"] = reason
        return await self.app(scope, receive, send)

    async def _authenticate(self, scope):
        token = self._get_token(scope)
        if not token:
            return AnonymousUser(), "missing_token"
        try:
            user = await self._get_user(token)
            return user, None
        except (InvalidToken, TokenError) as exc:
            reason = "expired_token" if "expired" in str(exc).lower() else "invalid_token"
            logger.info("event=websocket_auth_failed reason=%s", reason)
            return AnonymousUser(), reason
        except get_user_model().DoesNotExist:
            logger.info("event=websocket_auth_failed reason=user_not_found")
            return AnonymousUser(), "invalid_token"

    def _get_token(self, scope):
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin1")
        if authorization.lower().startswith("bearer "):
            return authorization.split(" ", 1)[1].strip()

        protocols = headers.get(b"sec-websocket-protocol", b"").decode("latin1")
        for item in [part.strip() for part in protocols.split(",")]:
            if item.lower().startswith("bearer."):
                return item.split(".", 1)[1].strip()

        query = parse_qs(scope.get("query_string", b"").decode("utf-8", errors="ignore"))
        token_values = query.get("token")
        return token_values[0] if token_values else None

    @database_sync_to_async
    def _get_user(self, raw_token):
        jwt_auth = JWTAuthentication()
        validated = jwt_auth.get_validated_token(raw_token)
        user_id = validated[api_settings.USER_ID_CLAIM]
        return get_user_model().objects.get(**{api_settings.USER_ID_FIELD: user_id})