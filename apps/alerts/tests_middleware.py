from django.test import SimpleTestCase

from apps.alerts.middleware import JWTAuthMiddleware


class JWTAuthMiddlewareTokenExtractionTests(SimpleTestCase):
    def middleware(self):
        return JWTAuthMiddleware(lambda scope, receive, send: None)

    def test_authorization_header_token_is_accepted(self):
        scope = {"headers": [(b"authorization", b"Bearer access-token")], "query_string": b""}
        self.assertEqual(self.middleware()._get_token(scope), "access-token")

    def test_websocket_protocol_bearer_token_is_accepted(self):
        scope = {"headers": [(b"sec-websocket-protocol", b"chat, bearer.access-token")], "query_string": b""}
        self.assertEqual(self.middleware()._get_token(scope), "access-token")

    def test_query_string_token_is_rejected(self):
        scope = {"headers": [], "query_string": b"token=access-token"}
        self.assertIsNone(self.middleware()._get_token(scope))

    def test_missing_token_returns_none(self):
        scope = {"headers": [], "query_string": b""}
        self.assertIsNone(self.middleware()._get_token(scope))
