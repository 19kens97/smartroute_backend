from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = await self._authenticate(scope)
        return await self.app(scope, receive, send)

    async def _authenticate(self, scope):
        token = self._get_token(scope)
        if not token:
            return AnonymousUser()
        try:
            return await self._get_user(token)
        except (AuthenticationFailed, InvalidToken, TokenError):
            return AnonymousUser()

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
        return jwt_auth.get_user(validated)