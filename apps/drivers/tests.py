from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.tickets.models import Ticket

from .models import Driver


class DriverApiTests(APITestCase):
    password = "Pass1234!Secure"

    def setUp(self):
        self.today = timezone.localdate()

        self.admin = self._create_professional_user(
            email="admin.driver@example.com",
            role=AgentProfile.Role.ADMIN,
            badge_number="ADM-DRIVER-001",
        )
        self.terrain = self._create_professional_user(
            email="terrain.driver@example.com",
            role=AgentProfile.Role.AGENT_TERRAIN,
            badge_number="TER-DRIVER-001",
        )
        self.saisie = self._create_professional_user(
            email="saisie.driver@example.com",
            role=AgentProfile.Role.AGENT_SAISIE,
            badge_number="SAI-DRIVER-001",
        )
        self.personal = self._create_personal_user()

        self.driver_person = Person.objects.create(
            nif="001-234-567-8",
            first_name="Jean",
            last_name="Permis",
            birth_date=self.today.replace(
                year=self.today.year - 30
            ),
        )
        self.driver = Driver.objects.create(
            person=self.driver_person,
            dossier_number="AB-12345-CD",
            address="Delmas",
            sex=Driver.Sex.MALE,
            blood_group="O+",
            license_type="B",
            issue_place="Port-au-Prince",
            issue_date=self.today - timedelta(days=365),
            expires_at=self.today + timedelta(days=365),
        )

    def _create_professional_user(
        self,
        *,
        email,
        role,
        badge_number,
    ):
        User = get_user_model()
        person = Person.objects.create(
            nif={"ADM-DRIVER-001": "900-000-001-0", "TER-DRIVER-001": "900-000-002-0", "SAI-DRIVER-001": "900-000-003-0"}[badge_number],
            first_name=role,
            last_name="Test",
        )
        user = User.objects.create_user(
            email=email,
            password=self.password,
            account_type=User.AccountType.PROFESSIONAL,
            person=person,
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
            nif="900-000-004-0",
            first_name="Compte",
            last_name="Personnel",
        )
        return User.objects.create_user(
            password=self.password,
            account_type=User.AccountType.PERSONAL,
            person=person,
            email="",
        )

    def force_auth(self, user):
        self.client.force_authenticate(user=user)

    def test_professional_roles_can_list_drivers(self):
        for user in (
            self.admin,
            self.terrain,
            self.saisie,
        ):
            self.force_auth(user)
            response = self.client.get("/api/drivers/")
            self.assertEqual(response.status_code, 200)

    def test_personal_account_cannot_list_all_drivers(self):
        self.force_auth(self.personal)
        response = self.client.get("/api/drivers/")
        self.assertEqual(response.status_code, 403)

    def test_agent_saisie_can_create_driver_with_new_person(self):
        self.force_auth(self.saisie)

        response = self.client.post(
            "/api/drivers/",
            {
                "person": {
                    "nif": "009-998-887-7",
                    "first_name": "Marie",
                    "last_name": "Permis",
                    "birth_date": "1992-05-20",
                },
                "dossier_number": "CD-23456-EF",
                "address": "Pétion-Ville",
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
        self.assertTrue(
            Driver.objects.filter(
                dossier_number="CD-23456-EF"
            ).exists()
        )

    def test_agent_saisie_can_create_driver_for_existing_person(self):
        person = Person.objects.create(
            nif="900-000-005-0",
            first_name="Existing",
            last_name="Person",
        )
        self.force_auth(self.saisie)

        response = self.client.post(
            "/api/drivers/",
            {
                "person_id": person.pk,
                "dossier_number": "GH-34567-IJ",
                "license_type": "B",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Driver.objects.get(
                dossier_number="GH-34567-IJ"
            ).person_id,
            person.pk,
        )

    def test_agent_saisie_cannot_create_second_driver_for_person(self):
        self.force_auth(self.saisie)

        response = self.client.post(
            "/api/drivers/",
            {
                "person_id": self.driver_person.pk,
                "dossier_number": "KL-45678-MN",
                "license_type": "B",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_admin_and_terrain_cannot_create_driver(self):
        payload = {
            "person": {
                "nif": "900-000-006-0",
                "first_name": "Blocked",
                "last_name": "Create",
            },
            "dossier_number": "OP-56789-QR",
            "license_type": "B",
        }

        for user in (self.admin, self.terrain):
            self.force_auth(user)
            response = self.client.post(
                "/api/drivers/",
                payload,
                format="json",
            )
            self.assertEqual(response.status_code, 403)

    def test_agent_saisie_can_patch_driver(self):
        self.force_auth(self.saisie)

        response = self.client.patch(
            f"/api/drivers/{self.driver.pk}/",
            {"address": "Carrefour"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.address, "Carrefour")

    def test_admin_and_terrain_cannot_patch_driver(self):
        for user in (self.admin, self.terrain):
            self.force_auth(user)
            response = self.client.patch(
                f"/api/drivers/{self.driver.pk}/",
                {"address": "Interdit"},
                format="json",
            )
            self.assertEqual(response.status_code, 403)

    def test_put_and_delete_are_not_available(self):
        self.force_auth(self.saisie)

        put_response = self.client.put(
            f"/api/drivers/{self.driver.pk}/",
            {},
            format="json",
        )
        delete_response = self.client.delete(
            f"/api/drivers/{self.driver.pk}/"
        )

        self.assertEqual(put_response.status_code, 405)
        self.assertEqual(delete_response.status_code, 405)

    def test_search_by_dossier_ignores_case_spaces_and_hyphens(self):
        self.force_auth(self.terrain)

        response = self.client.get(
            "/api/drivers/search-by-dossier/",
            {"dossier_number": " ab 12345 cd "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"]["licenses"][0]["dossier_number"],
            "AB-12345-CD",
        )

    def test_search_by_nif_uses_person_model(self):
        self.force_auth(self.terrain)

        response = self.client.get(
            "/api/drivers/search-by-nif/",
            {"nif": "001-234 567-8"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(
            response.data["data"]["licenses"][0]["nif"],
            "001-234-567-8",
        )

    def test_response_contains_validity_state(self):
        self.force_auth(self.terrain)

        response = self.client.get(
            "/api/drivers/search-by-dossier/",
            {"dossier_number": "AB-12345-CD"},
        )

        license_data = response.data["data"]["licenses"][0]
        self.assertTrue(license_data["is_currently_valid"])
        self.assertEqual(
            license_data["validity_state"],
            "VALID",
        )

    def test_search_by_dossier_with_multiple_open_tickets_returns_judicial_alert(self):
        self.force_auth(self.terrain)
        Ticket.objects.create(driver=self.driver, opened_by=self.terrain)
        Ticket.objects.create(driver=self.driver, opened_by=self.terrain)

        response = self.client.get(
            "/api/drivers/search-by-dossier/",
            {"dossier_number": "AB-12345-CD"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["unpaid_tickets"]["count"], 2)
        self.assertEqual(
            response.data["data"]["judicial_alert"]["code"],
            "JUDICIAL_ALERT",
        )
    def test_expiration_before_issue_date_is_rejected(self):
        self.force_auth(self.saisie)

        response = self.client.patch(
            f"/api/drivers/{self.driver.pk}/",
            {
                "issue_date": "2028-01-01",
                "expires_at": "2027-01-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)


