from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person


class ReportsPermissionTests(APITestCase):
    password = "Pass1234!Secure"

    def create_professional(self, email, role, badge):
        User = get_user_model()
        person = Person.objects.create(
            nif="88" + "".join(ch for ch in badge if ch.isdigit())[-8:].zfill(8),
            first_name=role,
            last_name="Reports",
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
            badge_number=badge,
            is_active=True,
        )
        return user

    def create_personal(self):
        User = get_user_model()
        person = Person.objects.create(
            nif="8700000004",
            first_name="Personal",
            last_name="Reports",
        )
        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PERSONAL,
            email="",
            password=self.password,
        )

    def setUp(self):
        self.admin = self.create_professional(
            "reports.admin@example.com",
            AgentProfile.Role.ADMIN,
            "87-00-00-00001",
        )
        self.entry = self.create_professional(
            "reports.entry@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "87-00-00-00002",
        )
        self.field = self.create_professional(
            "reports.field@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "87-00-00-00003",
        )
        self.personal = self.create_personal()

    def test_admin_can_access_summary(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/reports/summary/")
        self.assertEqual(response.status_code, 200)

    def test_entry_agent_can_access_reports(self):
        self.client.force_authenticate(self.entry)
        response = self.client.get("/api/reports/tickets/")
        self.assertEqual(response.status_code, 200)

    def test_field_agent_cannot_access_global_reports(self):
        self.client.force_authenticate(self.field)
        response = self.client.get("/api/reports/tickets/")
        self.assertEqual(response.status_code, 403)

    def test_personal_account_cannot_access_reports(self):
        self.client.force_authenticate(self.personal)
        response = self.client.get("/api/reports/tickets/")
        self.assertEqual(response.status_code, 403)

    def test_reports_are_read_only(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reports/tickets/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 405)

    def test_invalid_date_filter_returns_400(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            "/api/reports/tickets/?opened_from=invalid"
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_range_returns_400(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            "/api/reports/tickets/"
            "?opened_from=2026-07-31"
            "&opened_to=2026-07-01"
        )
        self.assertEqual(response.status_code, 400)
