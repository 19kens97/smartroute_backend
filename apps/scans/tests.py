from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from unittest.mock import patch, MagicMock


class GeminiScanAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")
        self.client.force_authenticate(user=self.user)

    @patch("google.genai.Client")
    def test_scan_plate_success(self, mock_client_class):
        mock_client = MagicMock()
        # Simulate a Gemini response with text containing a plate
        mock_response = MagicMock()
        mock_response.text = "AA12345"
        mock_client.models.generate_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        image = SimpleUploadedFile("plate.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        resp = self.client.post("/api/gemini/scan-plate/", {"image": image}, format="multipart")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("plate_number", data)

    def test_scan_plate_no_image(self):
        resp = self.client.post("/api/gemini/scan-plate/", {})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data.get("status"), "error")

    @patch("google.genai.Client")
    def test_scan_plate_fallback_model(self, mock_client_class):
        mock_client = MagicMock()
        # First model returns empty text, second fallback model returns a plate
        mock_response_primary = MagicMock()
        mock_response_primary.text = ""
        mock_response_fallback = MagicMock()
        mock_response_fallback.text = "ZZ99999"
        mock_client.models.generate_content.side_effect = [mock_response_primary, mock_response_fallback]
        mock_client_class.return_value = mock_client

        image = SimpleUploadedFile("plate.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        with patch("django.conf.settings.GEMINI_FALLBACK_MODELS", ["gemini-2.5-mini"]):
            resp = self.client.post("/api/gemini/scan-plate/", {"image": image}, format="multipart")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("plate_number"), "ZZ-99999")

    @patch("google.genai.Client")
    def test_scan_plate_persists_gemini_scan(self, mock_client_class):
        from apps.scans.models import GeminiScan

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "BB22222"
        mock_client.models.generate_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        image = SimpleUploadedFile("plate.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        resp = self.client.post("/api/gemini/scan-plate/", {"image": image}, format="multipart")
        self.assertEqual(resp.status_code, 200)

        scan = GeminiScan.objects.first()
        self.assertIsNotNone(scan)
        self.assertEqual(scan.plate_number, "BB-22222")
        self.assertTrue(scan.plate_detected)

    @patch("google.genai.Client")
    def test_scan_plate_matches_existing_vehicle(self, mock_client_class):
        from apps.vehicles.models import Vehicle
        from apps.scans.models import GeminiScan

        Vehicle.objects.create(plate_number="CC-33333")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "CC33333"
        mock_client.models.generate_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        image = SimpleUploadedFile("plate.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        resp = self.client.post("/api/gemini/scan-plate/", {"image": image}, format="multipart")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("plate_number"), "CC-33333")
        self.assertIsNotNone(data.get("vehicle"))
        self.assertEqual(data["vehicle"]["plate_number"], "CC-33333")

        scan = GeminiScan.objects.first()
        self.assertEqual(scan.vehicle.plate_number, "CC-33333")

    def test_search_plate_returns_scan_result_payload(self):
        from apps.scans.models import Scan
        from apps.vehicles.models import Vehicle

        Vehicle.objects.create(plate_number="AA12345", brand="Toyota", model="Corolla", color="Blanc")

        resp = self.client.get("/api/scans/search/?plate_number=AA-12345")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("plate_number"), "AA-12345")
        self.assertTrue(data.get("plate_detected"))
        self.assertIsNotNone(data.get("vehicle"))
        self.assertEqual(data["vehicle"]["brand"], "Toyota")
        self.assertIn("documents", data)
        self.assertIn("scanned_at", data)
        self.assertTrue(Scan.objects.filter(agent=self.user, plate_number="AA-12345", source="MANUAL").exists())

    def test_search_plate_unknown_vehicle_still_returns_success_payload(self):
        resp = self.client.get("/api/scans/search/?plate_number=ZZ99999")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("plate_number"), "ZZ-99999")
        self.assertTrue(data.get("plate_detected"))
        self.assertIsNone(data.get("vehicle"))
        self.assertEqual(data["tickets"]["summary"]["total"], 0)

    @patch("google.genai.Client")
    def test_scan_plate_returns_owner_insurance_agent_and_model(self, mock_client_class):
        from datetime import timedelta
        from django.utils import timezone
        from apps.insurance.models import InsurancePolicy
        from apps.owners.models import Owner
        from apps.scans.models import GeminiScan
        from apps.vehicles.models import Vehicle

        owner = Owner.objects.create(full_name="Marie Jean", national_id="NIF-001", phone="37000000", address="Delmas")
        vehicle = Vehicle.objects.create(plate_number="DD44444", owner=owner, brand="Nissan", model="Patrol", color="Noir", year=2020)
        InsurancePolicy.objects.create(
            vehicle=vehicle,
            insurer="AssurHaiti",
            policy_number="POL-444",
            valid_until=timezone.localdate() + timedelta(days=30),
            status=InsurancePolicy.STATUS_VALID,
        )
        mock_client = MagicMock()
        mock_response = MagicMock(text="DD44444")
        mock_client.models.generate_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        image = SimpleUploadedFile("plate.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        resp = self.client.post("/api/gemini/scan-plate/", {"image": image}, format="multipart")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["model_used"], "gemini-2.5-flash")
        self.assertEqual(data["documents"]["proprietaire"]["nom"], "Marie Jean")
        self.assertEqual(data["documents"]["assurance"]["numero_police"], "POL-444")
        scan = GeminiScan.objects.get()
        self.assertEqual(scan.agent, self.user)
        self.assertEqual(scan.model_used, "gemini-2.5-flash")
        self.assertEqual(scan.vehicle, vehicle)

    def test_search_plate_returns_real_tickets(self):
        from apps.tickets.models import Ticket
        from apps.vehicles.models import Vehicle

        vehicle = Vehicle.objects.create(plate_number="TT55555", brand="Kia")
        Ticket.objects.create(agent=self.user, vehicle=vehicle, driver_license="DRV-1", plate_number_snapshot="TT-55555", status="PENDING_SYNC")
        Ticket.objects.create(agent=self.user, vehicle=vehicle, driver_license="DRV-2", plate_number_snapshot="TT-55555", status="VALIDATED")

        resp = self.client.get("/api/scans/search/?plate_number=TT-55555")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["tickets"]["summary"], {"total": 2, "en_cours": 1, "regle": 1})
        self.assertEqual(len(data["tickets"]["items"]), 2)

    def test_last_scan_is_scoped_to_authenticated_user_and_ordered(self):
        from apps.scans.models import GeminiScan

        User = get_user_model()
        other = User.objects.create_user(username="other", password="pass")
        GeminiScan.objects.create(agent=other, plate_number="OTHER-1", model_used="gemini-test", plate_detected=True)
        GeminiScan.objects.create(agent=self.user, plate_number="FIRST-1", model_used="gemini-test", plate_detected=True)
        latest = GeminiScan.objects.create(agent=self.user, plate_number="LATEST-1", model_used="gemini-test", plate_detected=True)

        resp = self.client.get("/api/scans/last-scan/")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["plate_number"], latest.plate_number)

    def test_scan_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)

        image = SimpleUploadedFile("plate.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        scan = self.client.post("/api/gemini/scan-plate/", {"image": image}, format="multipart")
        search = self.client.get("/api/scans/search/?plate_number=AA12345")

        self.assertEqual(scan.status_code, 401)
        self.assertEqual(search.status_code, 401)
