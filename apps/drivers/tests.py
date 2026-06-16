from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Driver


class DriverApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.saisie = User.objects.create_user(username="saisie_driver", password="Pass1234!", role="AGENT_SAISIE")
        self.terrain = User.objects.create_user(username="terrain_driver", password="Pass1234!", role="AGENT_TERRAIN")
        self.admin = User.objects.create_user(username="admin_driver", password="Pass1234!", role="ADMIN")
        self.driver = Driver.objects.create(
            dossier_number="DOS-001",
            nif="NIF-001",
            full_name="Jean Permis",
            address="Delmas",
            birth_date="1990-01-10",
            sex="M",
            blood_group="O+",
            license_type="B",
            issue_place="Port-au-Prince",
            issue_date="2024-01-01",
            expires_at="2029-01-01",
        )

    def auth(self, username):
        token = self.client.post(
            "/api/auth/token/",
            {"username": username, "password": "Pass1234!"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_authenticated_users_can_search_driver_by_dossier_number(self):
        self.auth("terrain_driver")
        response = self.client.get("/api/drivers/search/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["dossier_number"], "DOS-001")
        self.assertEqual(response.data["data"]["nif"], "NIF-001")

    def test_entry_agent_can_create_driver(self):
        self.auth("saisie_driver")
        response = self.client.post(
            "/api/drivers/",
            {
                "dossier_number": "DOS-002",
                "nif": "NIF-002",
                "full_name": "Marie Permis",
                "address": "Petion-Ville",
                "birth_date": "1992-05-20",
                "sex": "F",
                "blood_group": "A+",
                "license_type": "B",
                "issue_place": "Port-au-Prince",
                "issue_date": "2024-02-01",
                "expires_at": "2029-02-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Driver.objects.filter(dossier_number="DOS-002").exists())

    def test_non_entry_agent_cannot_create_driver(self):
        self.auth("terrain_driver")
        response = self.client.post(
            "/api/drivers/",
            {"dossier_number": "DOS-003", "full_name": "Blocked", "license_type": "B"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_create_driver(self):
        self.auth("admin_driver")
        response = self.client.post(
            "/api/drivers/",
            {"dossier_number": "DOS-004", "full_name": "Admin Blocked", "license_type": "B"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_delete_driver_is_not_available(self):
        self.auth("saisie_driver")
        response = self.client.delete(f"/api/drivers/{self.driver.id}/")

        self.assertEqual(response.status_code, 405)
