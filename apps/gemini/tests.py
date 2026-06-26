from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from google.api_core import exceptions
from rest_framework.test import APITestCase

from apps.gemini import views
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner
from apps.scans.models import GeminiScan
from apps.vehicles.models import Vehicle


class GeminiHelpersTests(TestCase):
    def test_normalize_plate_candidate_removes_noise(self):
        self.assertEqual(views.normalize_plate_candidate(" tp-16921 "), "TP16921")
        self.assertEqual(views.normalize_plate_candidate(""), "")

    def test_is_usable_plate_requires_letters_and_digits(self):
        self.assertTrue(views.is_usable_plate("TP16921"))
        self.assertFalse(views.is_usable_plate("123456"))
        self.assertFalse(views.is_usable_plate("ABCDEFG"))
        self.assertFalse(views.is_usable_plate("T1"))

    def test_format_plate_display_inserts_hyphen_before_last_five_characters(self):
        self.assertEqual(views.format_plate_display("TP16921"), "TP-16921")
        self.assertEqual(views.format_plate_display("TP-16921"), "TP-16921")

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-primary", GEMINI_FALLBACK_MODELS=["gemini-fallback"])
    @patch("google.genai.Client")
    def test_generate_with_fallbacks_uses_next_model_when_first_output_is_not_usable(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.side_effect = [
            SimpleNamespace(text="bonjour"),
            SimpleNamespace(text="tp-16921"),
        ]

        response, model_used, plate, raw_text = views.generate_with_fallbacks(contents=["image", "prompt"])

        self.assertEqual(model_used, "gemini-fallback")
        self.assertEqual(plate, "TP16921")
        self.assertEqual(raw_text, "tp-16921")
        self.assertEqual(response.text, "tp-16921")
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-primary", GEMINI_FALLBACK_MODELS=["gemini-fallback"])
    @patch("google.genai.Client")
    def test_generate_with_fallbacks_raises_last_error_when_all_models_fail(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.side_effect = [
            exceptions.ServiceUnavailable("busy"),
            RuntimeError("network down"),
        ]

        with self.assertRaises(RuntimeError) as context:
            views.generate_with_fallbacks(contents=["image", "prompt"])

        self.assertIn("network down", str(context.exception))


class GeminiScanIntegrationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.agent = User.objects.create_user(username="agent.gemini", password="StrongPass123!", role="AGENT_TERRAIN")
        self.client.force_authenticate(user=self.agent)
        self.owner = Owner.objects.create(full_name="Jean Pierre", national_id="NIF-TEST-001", phone="50937000000", address="Port-au-Prince")
        self.vehicle = Vehicle.objects.create(
            owner=self.owner,
            plate_number="TP16921",
            brand="Toyota",
            model="Corolla",
            color="Blanc",
            year=2020,
        )
        InsurancePolicy.objects.create(vehicle=self.vehicle, insurer="AssurHaiti", policy_number="POL-16921", valid_until="2026-12-31", status=InsurancePolicy.STATUS_VALID)

    @override_settings(GEMINI_API_KEY="test-key")
    def test_scan_endpoint_calls_gemini_module_and_persists_scan(self):
        image = SimpleUploadedFile("plate.jpg", b"fake-image", content_type="image/jpeg")

        with patch("apps.gemini.views.types.Part.from_bytes", return_value="mocked-part"), patch(
            "apps.gemini.views.generate_with_fallbacks",
            return_value=(SimpleNamespace(text="TP-16921"), "gemini-2.5-flash", "TP16921", "TP-16921"),
        ) as mocked_generate:
            response = self.client.post("/api/scans/scan-plate/", {"image": image}, format="multipart")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["plate_number"], "TP-16921")
        self.assertEqual(payload["model_used"], "gemini-2.5-flash")
        self.assertEqual(payload["vehicle"]["plate_number"], "TP16921")
        self.assertEqual(payload["documents"]["assurance"]["numero_police"], "POL-16921")
        mocked_generate.assert_called_once()

        scan = GeminiScan.objects.get()
        self.assertEqual(scan.agent, self.agent)
        self.assertEqual(scan.vehicle, self.vehicle)
        self.assertEqual(scan.raw_response, "TP-16921")
        self.assertTrue(scan.plate_detected)

    def test_scan_endpoint_requires_image(self):
        response = self.client.post("/api/scans/scan-plate/", {}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Une image est requise.")

    @override_settings(GEMINI_API_KEY="test-key")
    def test_scan_endpoint_maps_gemini_unavailable(self):
        image = SimpleUploadedFile("plate.jpg", b"fake-image", content_type="image/jpeg")

        with patch("apps.gemini.views.types.Part.from_bytes", return_value="mocked-part"), patch(
            "apps.gemini.views.generate_with_fallbacks",
            side_effect=exceptions.ServiceUnavailable("busy"),
        ):
            response = self.client.post("/api/scans/scan-plate/", {"image": image}, format="multipart")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")