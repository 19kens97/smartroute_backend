from types import SimpleNamespace

from django.test import RequestFactory, TestCase, override_settings
from rest_framework import status
from rest_framework.response import Response

from .api import api_response
from .middleware import APIResponseLoggingMiddleware
from .renderers import StandardizedJSONRenderer
from .security import normalize_request_id, sanitize_mapping


class APIResponseTests(TestCase):
    def test_api_response_uses_standard_envelope(self):
        response = api_response(
            True,
            "Créé.",
            {"id": 1},
            status_code=status.HTTP_201_CREATED,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data,
            {
                "success": True,
                "message": "Créé.",
                "data": {"id": 1},
                "errors": {},
            },
        )


class StandardizedJSONRendererTests(TestCase):
    def test_renderer_wraps_success_response(self):
        renderer = StandardizedJSONRenderer()
        response = Response({"id": 1}, status=200)
        content = renderer.render(
            {"id": 1},
            renderer_context={"response": response},
        )
        self.assertIn(b'"success":true', content)
        self.assertIn(b'"data":{"id":1}', content)

    def test_renderer_keeps_existing_envelope(self):
        renderer = StandardizedJSONRenderer()
        response = Response(status=400)
        payload = {
            "success": False,
            "message": "Erreur.",
            "data": {},
            "errors": {"field": ["Invalide."]},
        }
        content = renderer.render(
            payload,
            renderer_context={"response": response},
        )
        self.assertEqual(content.count(b'"success"'), 1)

    def test_renderer_returns_empty_body_for_204(self):
        renderer = StandardizedJSONRenderer()
        response = Response(status=204)
        self.assertEqual(
            renderer.render(
                None,
                renderer_context={"response": response},
            ),
            b"",
        )


class SecurityUtilityTests(TestCase):
    def test_normalize_request_id_accepts_safe_value(self):
        self.assertEqual(
            normalize_request_id("mobile-request-001"),
            "mobile-request-001",
        )

    def test_normalize_request_id_replaces_unsafe_value(self):
        generated = normalize_request_id("bad\nrequest")
        self.assertNotEqual(generated, "bad\nrequest")
        self.assertEqual(len(generated), 36)

    def test_sanitize_mapping_masks_sensitive_values(self):
        result = sanitize_mapping(
            {
                "password": "Secret123!",
                "email": "agent@example.com",
                "driver_nif_snapshot": "NIF-001",
                "nested": {
                    "plate_number_snapshot": "AA12345",
                },
            }
        )
        self.assertEqual(result["password"], "<redacted>")
        self.assertEqual(result["email"], "a***@example.com")
        self.assertEqual(
            result["driver_nif_snapshot"],
            "NI***01",
        )
        self.assertEqual(
            result["nested"]["plate_number_snapshot"],
            "AA***45",
        )


@override_settings(
    API_RESPONSE_LOGGING_ENABLED=True,
    API_RESPONSE_LOGGING_INCLUDE_BODY=True,
    API_RESPONSE_LOGGING_MAX_CHARS=1200,
)
class APIResponseLoggingMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def middleware(self, response=None):
        return APIResponseLoggingMiddleware(
            lambda request: response or Response(
                {"success": True},
                status=200,
            )
        )

    def test_adds_request_id_header(self):
        request = self.factory.get(
            "/api/example/",
            HTTP_X_REQUEST_ID="test-request-123",
        )
        response = self.middleware()(request)
        self.assertEqual(
            response["X-Request-ID"],
            "test-request-123",
        )

    def test_rejects_unsafe_request_id(self):
        request = self.factory.get(
            "/api/example/",
            HTTP_X_REQUEST_ID="bad\nrequest",
        )
        response = self.middleware()(request)
        self.assertNotEqual(
            response["X-Request-ID"],
            "bad\nrequest",
        )

    def test_redacts_sensitive_query_parameters(self):
        request = self.factory.get(
            "/api/example/"
            "?token=secret-token"
            "&plate_number=AA12345"
        )
        safe_path = self.middleware().safe_path(request)
        self.assertIn("token=%3Credacted%3E", safe_path)
        self.assertNotIn("secret-token", safe_path)
        self.assertIn(
            "plate_number=AA%2A%2A%2A45",
            safe_path,
        )

    def test_masks_response_preview(self):
        preview = self.middleware().serialize_preview(
            {
                "email": "agent@example.com",
                "phone": "+50937123456",
                "nif": "NIF-001",
                "plate_number": "AA12345",
                "raw_response": "sensitive",
            }
        )
        self.assertIn('"email":"a***@example.com"', preview)
        self.assertIn('"phone":"+509****3456"', preview)
        self.assertIn('"nif":"NI***01"', preview)
        self.assertIn('"plate_number":"AA***45"', preview)
        self.assertIn(
            '"raw_response":"<redacted>"',
            preview,
        )

    @override_settings(API_RESPONSE_LOGGING_ENABLED=False)
    def test_can_disable_logging(self):
        request = self.factory.get("/api/example/")
        self.assertFalse(self.middleware().should_log(request))
