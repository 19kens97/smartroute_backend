import io
import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw
from rest_framework.test import APIClient, APITestCase


User = get_user_model()
SIGNATURE_URL = "/api/auth/profile/signature/"


def make_png(size=(240, 120), draw_signature=True):
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    if draw_signature:
        draw = ImageDraw.Draw(image)
        draw.line([(20, 70), (80, 35), (140, 80), (220, 45)], fill=(7, 20, 45, 255), width=5)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ProfileSignatureTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.signature_storage = User._meta.get_field("signature_file").storage
        self.original_storage_location = self.signature_storage._location
        self.signature_storage._location = self.media_root
        self.signature_storage.__dict__.pop("base_location", None)
        self.signature_storage.__dict__.pop("location", None)
        self.user = User.objects.create_user(username="agent", password="pass")
        self.other_user = User.objects.create_user(username="other", password="pass")
        self.client = APIClient()

    def tearDown(self):
        self.signature_storage._location = self.original_storage_location
        self.signature_storage.__dict__.pop("base_location", None)
        self.signature_storage.__dict__.pop("location", None)
        shutil.rmtree(self.media_root, ignore_errors=True)

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def test_unauthenticated_user_is_rejected(self):
        response = self.client.get(SIGNATURE_URL)
        self.assertEqual(response.status_code, 401)

    def test_agent_can_save_own_signature_file(self):
        self.authenticate()
        upload = io.BytesIO(make_png())
        upload.name = "signature.png"

        response = self.client.put(SIGNATURE_URL, {"signature": upload}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.signature_file.name.startswith(f"{self.user.pk}/"))
        self.assertEqual(len(self.user.signature_sha256), 64)
        self.assertTrue(response.data["data"]["has_signature"])

    def test_agent_cannot_modify_another_agent_signature(self):
        self.other_user.signature_file.save("signature.png", ContentFile(make_png()), save=True)
        previous_name = self.other_user.signature_file.name
        self.authenticate(self.user)
        upload = io.BytesIO(make_png())
        upload.name = "signature.png"

        response = self.client.put(SIGNATURE_URL, {"signature": upload}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.other_user.refresh_from_db()
        self.assertEqual(self.other_user.signature_file.name, previous_name)

    def test_missing_file_or_payload_is_rejected(self):
        self.authenticate()
        response = self.client.put(SIGNATURE_URL, {}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"]["signature"], "MISSING_SIGNATURE")

    def test_invalid_type_is_rejected(self):
        self.authenticate()
        upload = io.BytesIO(b"%PDF-1.4")
        upload.name = "signature.pdf"
        response = self.client.put(SIGNATURE_URL, {"signature": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"]["signature"], "INVALID_IMAGE")

    def test_too_large_file_is_rejected(self):
        self.authenticate()
        upload = io.BytesIO(b"x" * (1024 * 1024 + 1))
        upload.name = "signature.png"
        response = self.client.put(SIGNATURE_URL, {"signature": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"]["signature"], "FILE_TOO_LARGE")

    def test_blank_image_is_rejected(self):
        self.authenticate()
        upload = io.BytesIO(make_png(draw_signature=False))
        upload.name = "signature.png"
        response = self.client.put(SIGNATURE_URL, {"signature": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"]["signature"], "EMPTY_SIGNATURE")

    def test_strokes_payload_is_rendered_as_png(self):
        self.authenticate()
        payload = (
            '{"format":"strokes-v1","canvasWidth":240,"canvasHeight":120,'
            '"strokes":[[{"x":20,"y":70},{"x":90,"y":30},{"x":160,"y":85}]]}'
        )
        response = self.client.put(SIGNATURE_URL, {"signature_payload": payload}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.signature_file.name.endswith(".png"))

    def test_replacing_signature_deletes_old_file(self):
        self.authenticate()
        self.user.signature_file.save("signature.png", ContentFile(make_png()), save=True)
        old_path = self.user.signature_file.path
        upload = io.BytesIO(make_png(size=(260, 130)))
        upload.name = "signature.png"

        response = self.client.put(SIGNATURE_URL, {"signature": upload}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.user.signature_file.storage.exists(os.path.relpath(old_path, self.media_root)))

    def test_status_and_delete_signature(self):
        self.authenticate()
        self.user.signature_file.save("signature.png", ContentFile(make_png()), save=True)
        self.user.refresh_from_db()

        status_response = self.client.get(SIGNATURE_URL)
        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.data["data"]["has_signature"])

        delete_response = self.client.delete(SIGNATURE_URL)
        self.assertEqual(delete_response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.signature_file)


class ProfileContactAndPasswordTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile_agent",
            password="OldPass123!",
            email="agent@example.com",
            first_name="Jean",
            last_name="Agent",
            phone="+50937000000",
            role="AGENT_TERRAIN",
            badge_number="AGT-100",
        )
        self.other = User.objects.create_user(username="other_agent", password="pass", email="used@example.com")
        self.client = APIClient()

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_patch_me_updates_phone_and_normalizes(self):
        self.authenticate()
        response = self.client.patch("/api/auth/me/", {"phone": "509 3712-3456"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+50937123456")
        self.assertEqual(response.data["data"]["phone"], "+50937123456")
        self.assertEqual(self.user.email, "agent@example.com")

    def test_patch_me_rejects_invalid_phone_and_blank_email(self):
        self.authenticate()
        bad_phone = self.client.patch("/api/auth/me/", {"phone": "123"}, format="json")
        self.assertEqual(bad_phone.status_code, 400)
        self.assertIn("phone", bad_phone.data["errors"])

        blank_email = self.client.patch("/api/auth/me/", {"email": ""}, format="json")
        self.assertEqual(blank_email.status_code, 400)
        self.assertIn("email", blank_email.data["errors"])

    def test_patch_me_updates_email_normalizes_and_rejects_duplicate(self):
        self.authenticate()
        response = self.client.patch("/api/auth/me/", {"email": "  NEW@EXAMPLE.COM  "}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.phone, "+50937000000")

        duplicate = self.client.patch("/api/auth/me/", {"email": "used@example.com"}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.data["errors"]["email"][0], "Cette adresse e-mail est deja utilisee.")

    def test_patch_me_requires_auth_and_ignores_forbidden_fields(self):
        anonymous = self.client.patch("/api/auth/me/", {"phone": "+50937123456"}, format="json")
        self.assertEqual(anonymous.status_code, 401)

        self.authenticate()
        response = self.client.patch(
            "/api/auth/me/",
            {"phone": "+50937123456", "role": "ADMIN", "badge_number": "ROOT"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+50937123456")
        self.assertEqual(self.user.role, "AGENT_TERRAIN")
        self.assertEqual(self.user.badge_number, "AGT-100")

    def test_change_password_requires_auth_and_rejects_bad_old_password(self):
        anonymous = self.client.post("/api/auth/change-password/", {}, format="json")
        self.assertEqual(anonymous.status_code, 401)

        self.authenticate()
        response = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "wrong", "new_password": "NewPass123!", "confirm_password": "NewPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("old_password", response.data["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass123!"))

    def test_change_password_rejects_confirmation_mismatch_and_same_password(self):
        self.authenticate()
        mismatch = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "OldPass123!", "new_password": "NewPass123!", "confirm_password": "OtherPass123!"},
            format="json",
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("confirm_password", mismatch.data["errors"])

        same = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "OldPass123!", "new_password": "OldPass123!", "confirm_password": "OldPass123!"},
            format="json",
        )
        self.assertEqual(same.status_code, 400)
        self.assertIn("new_password", same.data["errors"])

    def test_change_password_success_uses_set_password(self):
        self.authenticate()
        response = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "OldPass123!", "new_password": "NewPass123!", "confirm_password": "NewPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("new_password", str(response.data))
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("OldPass123!"))
        self.assertTrue(self.user.check_password("NewPass123!"))
