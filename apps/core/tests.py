from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(API_RESPONSE_LOGGING_ENABLED=True, API_RESPONSE_LOGGING_MAX_CHARS=1200)
class APIResponseLoggingMiddlewareTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_logs_api_request_and_response_with_request_id(self):
        request_id = "test-request-123"
        with self.assertLogs("apps.http", level="INFO") as captured:
            response = self.client.get(
                "/api/auth/me/",
                HTTP_USER_AGENT="SmartRouteMobile/test",
                HTTP_X_REQUEST_ID=request_id,
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["X-Request-ID"], request_id)
        log_line = "\n".join(captured.output)
        self.assertIn("event=request_started", log_line)
        self.assertIn("event=request_completed", log_line)
        self.assertIn(f"request_id={request_id}", log_line)
        self.assertIn("method=GET", log_line)
        self.assertIn("path=/api/auth/me/", log_line)
        self.assertIn("status=401", log_line)
        self.assertIn("SmartRouteMobile/test", log_line)
        self.assertIn("response=", log_line)

    def test_redacts_tokens_from_logged_response(self):
        user_model = get_user_model()
        user_model.objects.create_user(username="agent", password="Pass12345!", role="AGENT_TERRAIN")

        with self.assertLogs("apps.http", level="INFO") as captured:
            response = self.client.post("/api/auth/token/", {"username": "agent", "password": "Pass12345!"}, format="json")

        self.assertEqual(response.status_code, 200)
        token_payload = response.data.get("data", response.data)
        access = token_payload["access"]
        refresh = token_payload["refresh"]
        log_line = "\n".join(captured.output)
        self.assertIn('"access":"<redacted>"', log_line)
        self.assertIn('"refresh":"<redacted>"', log_line)
        self.assertNotIn(access, log_line)
        self.assertNotIn(refresh, log_line)
        self.assertNotIn("Pass12345!", log_line)

    def test_redacts_sensitive_query_parameters(self):
        with self.assertLogs("apps.http", level="INFO") as captured:
            self.client.get("/api/auth/me/?token=secret-token&plate_number=AA12345")

        log_line = "\n".join(captured.output)
        self.assertIn("token=%3Credacted%3E", log_line)
        self.assertNotIn("secret-token", log_line)
        self.assertIn("plate_number=AA%2A%2A%2A45", log_line)
        self.assertNotIn("plate_number=AA12345", log_line)

    def test_masks_pii_fields_from_logged_response(self):
        from apps.core.middleware import APIResponseLoggingMiddleware

        middleware = APIResponseLoggingMiddleware(lambda request: None)
        preview = middleware.serialize_preview({
            "email": "agent@example.com",
            "phone": "+50937123456",
            "nif": "NIF-001",
            "plate_number": "AA12345",
            "raw_response": "AA12345",
        })

        self.assertIn('"email":"a***@example.com"', preview)
        self.assertIn('"phone":"+509****3456"', preview)
        self.assertIn('"nif":"NI***01"', preview)
        self.assertIn('"plate_number":"AA***45"', preview)
        self.assertIn('"raw_response":"<redacted>"', preview)
        self.assertNotIn("agent@example.com", preview)
        self.assertNotIn("+50937123456", preview)
        self.assertNotIn("AA12345", preview)
    @override_settings(API_RESPONSE_LOGGING_ENABLED=False)
    def test_can_disable_api_response_logging(self):
        with self.assertNoLogs("apps.http", level="INFO"):
            response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)


