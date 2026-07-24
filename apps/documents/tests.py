from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.vehicles.models import Vehicle

from .models import Document


class DocumentApiTests(APITestCase):
    password = "Pass1234!Secure"

    def setUp(self):
        self.admin = self._create_professional_user(
            "admin.documents@example.com",
            AgentProfile.Role.ADMIN,
            "DOC-ADMIN-001",
        )
        self.terrain = self._create_professional_user(
            "terrain.documents@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "DOC-TERRAIN-001",
        )
        self.saisie = self._create_professional_user(
            "saisie.documents@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "DOC-SAISIE-001",
        )
        self.personal = self._create_personal_user()

        # Adapter cette création aux champs obligatoires réels de Vehicle.
        self.vehicle = Vehicle.objects.create(
            plate_number="HT-TEST-001",
        )

        self.document = Document.objects.create(
            vehicle=self.vehicle,
            uploaded_by=self.saisie,
            document_type=Document.DocumentType.VEHICLE_PHOTO,
            title="Photo avant",
            file=SimpleUploadedFile(
                "photo.png",
                b"fake-png-content",
                content_type="image/png",
            ),
        )

    def _create_professional_user(
        self,
        email,
        role,
        badge_number,
    ):
        User = get_user_model()
        person = Person.objects.create(
            nif=badge_number,
            first_name=role,
            last_name="Documents",
        )
        user = User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email=email,
            password=self.password,
        )
        AgentProfile.objects.create(
            user=user,
            role=role,
            badge_number=badge_number,
            is_active=True,
        )
        return user

    def _create_personal_user(self):
        User = get_user_model()
        person = Person.objects.create(
            nif="DOC-PERSONAL-001",
            first_name="Personal",
            last_name="Documents",
        )
        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PERSONAL,
            email="",
            password=self.password,
        )

    def force_auth(self, user):
        self.client.force_authenticate(user=user)

    def test_professional_roles_can_list_documents(self):
        for user in (
            self.admin,
            self.terrain,
            self.saisie,
        ):
            self.force_auth(user)
            response = self.client.get("/api/documents/")
            self.assertEqual(response.status_code, 200)

    def test_personal_account_cannot_list_documents(self):
        self.force_auth(self.personal)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, 403)

    def test_agent_saisie_can_create_document(self):
        self.force_auth(self.saisie)

        response = self.client.post(
            "/api/documents/",
            {
                "vehicle": self.vehicle.pk,
                "document_type": (
                    Document.DocumentType.SUPPORTING_DOCUMENT
                ),
                "title": "Justificatif",
                "description": "Document de contrôle",
                "file": SimpleUploadedFile(
                    "justificatif.pdf",
                    b"%PDF-1.4 fake",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        created = Document.objects.get(title="Justificatif")
        self.assertEqual(created.uploaded_by, self.saisie)

    def test_admin_and_terrain_cannot_create_document(self):
        for user in (self.admin, self.terrain):
            self.force_auth(user)
            response = self.client.post(
                "/api/documents/",
                {
                    "vehicle": self.vehicle.pk,
                    "title": "Interdit",
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 403)

    def test_agent_saisie_can_patch_metadata(self):
        self.force_auth(self.saisie)

        response = self.client.patch(
            f"/api/documents/{self.document.pk}/",
            {"title": "Photo avant mise à jour"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(
            self.document.title,
            "Photo avant mise à jour",
        )

    def test_put_and_delete_are_not_available(self):
        self.force_auth(self.saisie)

        put_response = self.client.put(
            f"/api/documents/{self.document.pk}/",
            {},
            format="json",
        )
        delete_response = self.client.delete(
            f"/api/documents/{self.document.pk}/"
        )

        self.assertEqual(put_response.status_code, 405)
        self.assertEqual(delete_response.status_code, 405)

    def test_read_serializer_does_not_expose_storage_url(self):
        self.force_auth(self.terrain)

        response = self.client.get(
            f"/api/documents/{self.document.pk}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("file", response.data)
        self.assertIn("download_url", response.data)
        self.assertTrue(response.data["download_url"].endswith(f"/api/documents/{self.document.pk}/download/"))
        self.assertNotIn(settings.MEDIA_URL, response.data["download_url"])

    def test_document_file_uses_private_storage(self):
        self.assertEqual(
            str(self.document.file.storage.location),
            str(settings.PRIVATE_DOCUMENT_ROOT),
        )
        with self.assertRaises(ValueError):
            self.document.file.url

    def test_unauthenticated_user_cannot_download_document(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/documents/{self.document.pk}/download/")
        self.assertEqual(response.status_code, 401)

    def test_professional_roles_can_download_document(self):
        for user in (self.admin, self.terrain, self.saisie):
            self.force_auth(user)
            response = self.client.get(f"/api/documents/{self.document.pk}/download/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(response.streaming_content), b"fake-png-content")

    def test_missing_document_file_returns_404(self):
        self.force_auth(self.terrain)
        self.document.file.delete(save=False)
        response = self.client.get(f"/api/documents/{self.document.pk}/download/")
        self.assertEqual(response.status_code, 404)

    def test_disguised_document_files_are_rejected(self):
        self.force_auth(self.saisie)
        for upload in (
            SimpleUploadedFile("fake.pdf", b"MZ executable", content_type="application/pdf"),
            SimpleUploadedFile("fake.jpg", b"<script>", content_type="image/jpeg"),
            SimpleUploadedFile("fake.png", b"not-a-png", content_type="image/png"),
            SimpleUploadedFile("proof.pdf.exe", b"%PDF-1.4", content_type="application/pdf"),
        ):
            response = self.client.post(
                "/api/documents/",
                {
                    "vehicle": self.vehicle.pk,
                    "document_type": Document.DocumentType.SUPPORTING_DOCUMENT,
                    "title": f"Rejected {upload.name}",
                    "file": upload,
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 400)
