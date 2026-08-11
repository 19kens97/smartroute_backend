from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.accounts.models import AgentProfile, User


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
            return await self._get_user(token), None
        except (InvalidToken, TokenError):
            return AnonymousUser(), "invalid_token"
        except AgentProfile.DoesNotExist:
            return AnonymousUser(), "forbidden"

    def _get_token(self, scope):
        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }

        authorization = headers.get(b"authorization", b"").decode("latin1")
        if authorization.lower().startswith("bearer "):
            return authorization.split(" ", 1)[1].strip()

        protocols = headers.get(
            b"sec-websocket-protocol",
            b"",
        ).decode("latin1")
        for item in (part.strip() for part in protocols.split(",")):
            if item.lower().startswith("bearer."):
                return item.split(".", 1)[1].strip()

        return None

    @database_sync_to_async
    def _get_user(self, raw_token):
        jwt_auth = JWTAuthentication()
        validated = jwt_auth.get_validated_token(raw_token)
        user = jwt_auth.get_user(validated)

        if (
            not user.is_active
            or user.account_type != User.AccountType.PROFESSIONAL
        ):
            raise AgentProfile.DoesNotExist

        profile = user.agent_profile
        if not profile.is_active:
            raise AgentProfile.DoesNotExist

        return user


