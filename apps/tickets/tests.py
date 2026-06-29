import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.infractions.models import Infraction
from .models import Ticket, TicketProof


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
        self.inf = Infraction.objects.create(code="I1", label="Test", amount=100)

    def tearDown(self):
        self.signature_storage._location = self.original_signature_location
        self.signature_storage.__dict__.pop("base_location", None)
        self.signature_storage.__dict__.pop("location", None)
        shutil.rmtree(self.media_root, ignore_errors=True)

    def create_ticket(self):
        return Ticket.objects.create(agent=self.terrain, driver_license="D1", plate_number_snapshot="AA1")

    def test_ticket_create_requires_infraction(self):
        r = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_ids": []}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ticket_create_with_infraction(self):
        r = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_ids": [self.inf.id]}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["driver_license"], "D1")
        self.assertEqual(r.data["plate_number_snapshot"], "AA1")
        self.assertEqual(r.data["infractions"][0]["id"], self.inf.id)

    def test_ticket_create_rejects_invalid_infraction_id(self):
        r = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_ids": [999999]}, format="json")
        self.assertEqual(r.status_code, 400)

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
        response = self.client.post("/api/tickets/", {"driver_license": "D1", "plate_number_snapshot": "AA1", "infraction_ids": [self.inf.id]}, format="json")
        ticket_id = response.data["id"]
        detail = self.client.get(f"/api/tickets/{ticket_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data["agent_detail"]["has_signature"])
        self.assertIn(f"/api/tickets/{ticket_id}/agent-signature/", detail.data["agent_signature_url"])
        signature = self.client.get(f"/api/tickets/{ticket_id}/agent-signature/")
        self.assertEqual(signature.status_code, 200)
        self.assertEqual(signature.get("Content-Type"), "image/png")


