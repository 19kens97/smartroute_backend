import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils.dateparse import parse_datetime
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from unittest.mock import patch
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.infractions.models import Infraction
from .models import Ticket, TicketInfraction, TicketProof
from .services import TICKET_NUMBER_MAX_ATTEMPTS, generate_unique_ticket_number


class TicketApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.media_root = tempfile.mkdtemp()
        self.signature_storage = User._meta.get_field("signature_file").storage
        self.original_signature_location = self.signature_storage._location
        self.signature_storage._location = self.media_root
        self.signature_storage.__dict__.pop("base_location", None)
        self.signature_storage.__dict__.pop("location", None)
        self.terrain = User.objects.create_user(username="terrain", password="Pass1234!", role="AGENT_TERRAIN", first_name="Agent", last_name="Terrain", badge_number="AGT-1")
        self.other_terrain = User.objects.create_user(username="terrain2", password="Pass1234!", role="AGENT_TERRAIN")
        self.saisie = User.objects.create_user(username="saisie", password="Pass1234!", role="AGENT_SAISIE")
        token = self.client.post("/api/auth/token/", {"username": "terrain", "password": "Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.inf = Infraction.objects.create(code="I001", label="Test", amount=100)

    def tearDown(self):
        self.signature_storage._location = self.original_signature_location
        self.signature_storage.__dict__.pop("base_location", None)
        self.signature_storage.__dict__.pop("location", None)
        shutil.rmtree(self.media_root, ignore_errors=True)

    def create_ticket(self):
        return Ticket.objects.create(agent=self.terrain, driver_license="D1", plate_number_snapshot="AA1")

    def test_ticket_create_requires_infraction(self):
        r = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": []}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ticket_create_with_infraction(self):
        r = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": [self.inf.code]}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["driver_license"], "D1")
        self.assertEqual(r.data["plate_number_snapshot"], "AA1")
        self.assertEqual(r.data["infractions"][0]["id"], self.inf.id)
        self.assertRegex(r.data["ticket_number"], r"^[0-9A-F]{8}$")
        self.assertTrue(Ticket.objects.filter(id=r.data["id"], ticket_number=r.data["ticket_number"], agent=self.terrain).exists())
        self.assertTrue(TicketInfraction.objects.filter(ticket_id=r.data["id"], infraction=self.inf).exists())

    def test_ticket_number_is_unique_and_read_only(self):
        first = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": [self.inf.code], "ticket_number": "ABCDEF12"}, format="json")
        second = self.client.post("/api/tickets/", {"driver_license": "D2", "plate_number_snapshot": "BB2", "infraction_codes": [self.inf.code]}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["ticket_number"], "ABCDEF12")
        self.assertNotEqual(first.data["ticket_number"], second.data["ticket_number"])
        patch_response = self.client.patch(f"/api/tickets/{first.data['id']}/", {"ticket_number": "ABCDEF12"}, format="json")
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["ticket_number"], first.data["ticket_number"])

    def test_ticket_number_collision_retry(self):
        existing = Ticket.objects.create(agent=self.terrain, driver_license="D0", plate_number_snapshot="AA0", ticket_number="ABCDEF12")
        with patch("apps.tickets.services.secrets.token_hex", side_effect=["abcdef12", "0001a9cf"]):
            value = generate_unique_ticket_number()
        self.assertEqual(existing.ticket_number, "ABCDEF12")
        self.assertEqual(value, "0001A9CF")

    def test_ticket_number_generation_stops_after_max_attempts(self):
        Ticket.objects.create(agent=self.terrain, driver_license="D0", plate_number_snapshot="AA0", ticket_number="ABCDEF12")
        with patch("apps.tickets.services.secrets.token_hex", return_value="abcdef12"):
            with self.assertRaises(RuntimeError):
                generate_unique_ticket_number()
        self.assertEqual(TICKET_NUMBER_MAX_ATTEMPTS, 10)

    def test_ticket_create_rejects_invalid_infraction_id(self):
        r = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": ["I999"]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ticket_create_persists_control_context_and_barcode(self):
        occurred_at = "2026-07-01T14:35:22-04:00"
        response = self.client.post(
            "/api/tickets/",
            {
                "driver_license": "D1",
                "plate_number_snapshot": "AA1",
                "infraction_codes": [self.inf.code],
                "occurred_at": occurred_at,
                "location_label": "Delmas 33",
                "latitude": "18.543210",
                "longitude": "-72.321000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertRegex(response.data["ticket_number"], r"^[0-9A-F]{8}$")
        self.assertEqual(response.data["location_label"], "Delmas 33")
        self.assertEqual(parse_datetime(response.data["occurred_at"]).isoformat(), parse_datetime(occurred_at).isoformat())

    def test_ticket_receipt_without_proofs_returns_empty_list(self):
        response = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": [self.inf.code]}, format="json")
        detail = self.client.get(f"/api/tickets/{response.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["proofs"], [])

    def test_receipt_agent_without_signature_uses_full_name_metadata(self):
        response = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": [self.inf.code]}, format="json")
        detail = self.client.get(f"/api/tickets/{response.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["agent_detail"]["full_name"], "Agent Terrain")
        self.assertFalse(detail.data["agent_detail"]["has_signature"])
        self.assertIsNone(detail.data["agent_signature_url"])

    def test_ticket_proof_accepts_png_photo(self):
        ticket = self.create_ticket()
        upload = SimpleUploadedFile("photo.png", b"photo", content_type="image/png")
        response = self.client.post(f"/api/tickets/{ticket.id}/proofs/", {"file": upload, "evidence_type": "PHOTO"}, format="multipart")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        proof = TicketProof.objects.get(ticket=ticket)
        self.assertEqual(data["mime_type"], "image/png")
        self.assertEqual(data["size_bytes"], 5)
        self.assertEqual(len(data["checksum_sha256"]), 64)
        self.assertNotIn("file", data)
        self.assertIn(f"/api/tickets/{ticket.id}/proofs/{proof.id}/download/", data["url"])
        self.assertTrue(proof.file.name.startswith(f"tickets/{ticket.ticket_number}/photos/"))
        self.assertNotIn("photo.png", proof.file.name)
        self.assertEqual(proof.created_by, self.terrain)
        download = self.client.get(f"/api/tickets/{ticket.id}/proofs/{proof.id}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.get("Cache-Control"), "private, no-store")

    def test_ticket_proof_rejects_empty_file(self):
        ticket = self.create_ticket()
        upload = SimpleUploadedFile("photo.jpg", b"", content_type="image/jpeg")
        response = self.client.post(f"/api/tickets/{ticket.id}/proofs/", {"file": upload, "evidence_type": "PHOTO"}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_agent_terrain_cannot_update_other_agent_ticket(self):
        ticket = Ticket.objects.create(agent=self.other_terrain, driver_license="DX", plate_number_snapshot="BB2")
        r = self.client.patch(f"/api/tickets/{ticket.id}/", {"status": "ISSUED"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_agent_saisie_can_patch_ticket(self):
        ticket = Ticket.objects.create(agent=self.terrain, driver_license="D1", plate_number_snapshot="AA1")
        token = self.client.post("/api/auth/token/", {"username": "saisie", "password": "Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        r = self.client.patch(f"/api/tickets/{ticket.id}/", {"status": "PENDING_SYNC"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_ticket_accepts_photo_video_and_audio_proofs(self):
        ticket = self.create_ticket()
        cases = [
            ("PHOTO", "photo.jpg", "image/jpeg", b"photo"),
            ("VIDEO", "video.mp4", "video/mp4", b"video"),
            ("AUDIO", "audio.m4a", "audio/mp4", b"audio"),
        ]
        for evidence_type, name, content_type, content in cases:
            upload = SimpleUploadedFile(name, content, content_type=content_type)
            response = self.client.post(
                f"/api/tickets/{ticket.id}/proofs/",
                {"file": upload, "evidence_type": evidence_type, "duration_seconds": 5},
                format="multipart",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["data"]["evidence_type"], evidence_type)
        self.assertEqual(TicketProof.objects.filter(ticket=ticket).count(), 3)

    def test_ticket_proof_rejects_invalid_mime(self):
        ticket = self.create_ticket()
        upload = SimpleUploadedFile("photo.jpg", b"not-photo", content_type="application/pdf")
        response = self.client.post(f"/api/tickets/{ticket.id}/proofs/", {"file": upload, "evidence_type": "PHOTO"}, format="multipart")
        self.assertEqual(response.status_code, 400)

    @override_settings(SECURE_UPLOAD_MAX_MB=0)
    def test_ticket_proof_rejects_too_large_photo(self):
        ticket = self.create_ticket()
        upload = SimpleUploadedFile("photo.jpg", b"x", content_type="image/jpeg")
        response = self.client.post(f"/api/tickets/{ticket.id}/proofs/", {"file": upload, "evidence_type": "PHOTO"}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_receipt_detail_exposes_agent_signature_url_and_signature_file(self):
        self.terrain.signature_file.save("signature.png", ContentFile(b"signature"), save=False)
        self.terrain.signature_updated_at = timezone.now()
        self.terrain.save(update_fields=["signature_file", "signature_updated_at"])
        response = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_codes": [self.inf.code]}, format="json")
        ticket_id = response.data["id"]
        detail = self.client.get(f"/api/tickets/{ticket_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data["agent_detail"]["has_signature"])
        self.assertIn(f"/api/tickets/{ticket_id}/agent-signature/", detail.data["agent_signature_url"])
        signature = self.client.get(f"/api/tickets/{ticket_id}/agent-signature/")
        self.assertEqual(signature.status_code, 200)
        self.assertEqual(signature.get("Content-Type"), "image/png")



