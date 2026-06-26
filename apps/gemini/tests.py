from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from google.api_core import exceptions

from gemini.models import GeminiScan
from gemini import views
from Documents.models import Owner
from Infractions.models import Infraction
from Tickets.models import Ticket
from Users.models import User
from Vehicles.models import Vehicle


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

    def test_format_plate_display_keeps_same_result_when_hyphen_already_present(self):
        self.assertEqual(views.format_plate_display("TP-16921"), "TP-16921")

    @override_settings(GEMINI_MODEL="gemini-primary", GEMINI_FALLBACK_MODELS=["gemini-fallback"])
    def test_generate_with_fallbacks_uses_next_model_when_first_output_is_not_usable(self):
        with patch.object(
            views.client.models,
            "generate_content",
            side_effect=[
                SimpleNamespace(text="bonjour"),
                SimpleNamespace(text="tp-16921"),
            ],
        ) as mocked_generate:
            response, model_used, plate = views.generate_with_fallbacks(contents=["image", "prompt"])

        self.assertEqual(model_used, "gemini-fallback")
        self.assertEqual(plate, "TP16921")
        self.assertEqual(response.text, "tp-16921")
        self.assertEqual(mocked_generate.call_count, 2)

    @override_settings(GEMINI_MODEL="gemini-primary", GEMINI_FALLBACK_MODELS=["gemini-fallback"])
    def test_generate_with_fallbacks_raises_last_error_when_all_models_fail(self):
        with patch.object(
            views.client.models,
            "generate_content",
            side_effect=[
                exceptions.ServiceUnavailable("busy"),
                RuntimeError("network down"),
            ],
        ):
            with self.assertRaises(RuntimeError) as context:
                views.generate_with_fallbacks(contents=["image", "prompt"])

        self.assertIn("network down", str(context.exception))


class GeminiApiTests(TestCase):
    def setUp(self):
        self.owner = Owner.objects.create(
            nif="NIF-TEST-001",
            nom="Jean",
            prenom="Pierre",
            adresse="Port-au-Prince",
            phone="50937000000",
            email="jean.pierre@example.com",
        )
        self.vehicle = Vehicle.objects.create(
            owner=self.owner,
            plate_number="TP-16921",
            brand="Toyota",
            model="Corolla",
            color="Blanc",
            year=2020,
        )
        self.agent = User.objects.create_user(
            username="agent.gemini",
            password="StrongPass123!",
            role="AGENT_TERRAIN",
            nif="910009999",
        )
        self.infraction = Infraction.objects.create(
            code="SPD-99",
            description="Exces de vitesse",
            penalty="1500.00",
            category="Vitesse",
        )

    def test_extract_license_plate_rejects_invalid_request(self):
        response = self.client.get("/api/gemini/scan-plate/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    def test_extract_license_plate_returns_plate_on_success(self):
        image = SimpleUploadedFile("plate.jpg", b"fake-image", content_type="image/jpeg")

        with patch("gemini.views.types.Part.from_bytes", return_value="mocked-part"), patch(
            "gemini.views.generate_with_fallbacks",
            return_value=(SimpleNamespace(text="TP-16921"), "gemini-2.5-flash", "TP16921"),
        ):
            response = self.client.post("/api/gemini/scan-plate/", {"image": image})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["plate_number"], "TP-16921")
        self.assertEqual(payload["model_used"], "gemini-2.5-flash")
        self.assertEqual(payload["vehicle"]["plate_number"], "TP-16921")
        self.assertEqual(payload["vehicle"]["owner"]["nif"], "NIF-TEST-001")

    def test_extract_license_plate_returns_503_when_service_is_unavailable(self):
        image = SimpleUploadedFile("plate.jpg", b"fake-image", content_type="image/jpeg")

        with patch("gemini.views.types.Part.from_bytes", return_value="mocked-part"), patch(
            "gemini.views.generate_with_fallbacks",
            side_effect=exceptions.ServiceUnavailable("busy"),
        ):
            response = self.client.post("/api/gemini/scan-plate/", {"image": image})

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")

    def test_extract_license_plate_persists_scan_entry(self):
        image = SimpleUploadedFile("plate.jpg", b"fake-image", content_type="image/jpeg")

        with patch("gemini.views.types.Part.from_bytes", return_value="mocked-part"), patch(
            "gemini.views.generate_with_fallbacks",
            return_value=(SimpleNamespace(text="TP16921"), "gemini-2.5-flash", "TP16921"),
        ):
            response = self.client.post("/api/gemini/scan-plate/", {"image": image})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(GeminiScan.objects.count(), 1)
        scan = GeminiScan.objects.first()
        self.assertIsNotNone(scan)
        self.assertEqual(scan.plate_number, "TP-16921")
        self.assertEqual(scan.model_used, "gemini-2.5-flash")
        self.assertEqual(scan.vehicle_id, self.vehicle.id)

    def test_get_last_scan_returns_404_when_no_scan_exists(self):
        response = self.client.get("/api/gemini/last-scan/")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "error")

    def test_get_last_scan_returns_most_recent_scan(self):
        GeminiScan.objects.create(plate_number="AA-12345", model_used="gemini-older")
        GeminiScan.objects.create(
            plate_number="TP-16921",
            model_used="gemini-2.5-flash",
            vehicle=self.vehicle,
        )

        response = self.client.get("/api/gemini/last-scan/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["plate_number"], "TP-16921")
        self.assertEqual(payload["model_used"], "gemini-2.5-flash")
        self.assertEqual(payload["vehicle"]["plate_number"], "TP-16921")
        self.assertEqual(payload["vehicle"]["owner"]["nom"], "Jean")
        self.assertIn("scanned_at", payload)

    def test_search_plate_returns_vehicle_and_owner(self):
        Ticket.objects.create(
            vehicle=self.vehicle,
            infraction=self.infraction,
            agent=self.agent,
            location="Delmas 33",
            photos=[],
            ticket_number="PV-20260428-0001",
            status=Ticket.STATUS_EN_COURS,
        )
        Ticket.objects.create(
            vehicle=self.vehicle,
            infraction=self.infraction,
            agent=self.agent,
            location="Petion-Ville",
            photos=[],
            ticket_number="PV-20260428-0002",
            status=Ticket.STATUS_REGLE,
        )

        response = self.client.get("/api/gemini/search-plate/?plate_number=tp16921")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["plate_number"], "TP-16921")
        self.assertEqual(payload["vehicle"]["brand"], "Toyota")
        self.assertEqual(payload["vehicle"]["owner"]["prenom"], "Pierre")
        self.assertEqual(payload["tickets"]["summary"]["total"], 2)
        self.assertEqual(payload["tickets"]["summary"]["en_cours"], 1)
        self.assertEqual(payload["tickets"]["summary"]["regle"], 1)
        self.assertEqual(len(payload["tickets"]["items"]), 2)

    def test_search_plate_returns_404_when_vehicle_not_found(self):
        response = self.client.get("/api/gemini/search-plate/?plate_number=AA12345")
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
