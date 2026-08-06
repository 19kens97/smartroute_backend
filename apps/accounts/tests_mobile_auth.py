from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person, User


class MobileAuthTests(APITestCase):
    password = "Passw0rd!123"

    def make_person(self, index):
        return Person.objects.create(
            nif=f"200-000-{index:03d}-{index % 10}",
            first_name="Agent",
            last_name=str(index),
            birth_date=date(1990, 1, 1),
        )

    def make_professional(self, index, role=AgentProfile.Role.AGENT_TERRAIN, user_active=True, profile_active=True, profile=True):
        user = User.objects.create_user(
            username=f"pro-{index}",
            email=f"agent{index}@example.com",
            password=self.password,
            person=self.make_person(index),
            account_type=User.AccountType.PROFESSIONAL,
            is_active=user_active,
        )
        if profile:
            AgentProfile.objects.create(
                user=user,
                role=role,
                badge_number=f"20-00-00-{index:05d}",
                post="Poste Central",
                is_active=profile_active,
            )
        return user


    def post_login(self, email, password=None):
        return self.client.post(
            "/api/auth/mobile/login/",
            {"email": email, "password": password or self.password},
            format="json",
        )

    def test_mobile_login_accepts_active_field_agent_only(self):
        user = self.make_professional(1)
        response = self.post_login(user.email)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(data["access_token"])
        self.assertTrue(data["refresh_token"])
        self.assertEqual(data["user"]["account_type"], User.AccountType.PROFESSIONAL)
        self.assertEqual(data["user"]["agent_profile"]["role"], AgentProfile.Role.AGENT_TERRAIN)

    def test_mobile_login_rejects_wrong_credentials_without_tokens(self):
        user = self.make_professional(2)
        response = self.post_login(user.email, "bad-password")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access_token", response.data.get("data") or {})
        self.assertNotIn("refresh_token", response.data.get("data") or {})

    def test_mobile_login_rejects_non_field_professional_roles(self):
        for index, role in enumerate([AgentProfile.Role.AGENT_SAISIE, AgentProfile.Role.ADMIN], start=3):
            user = self.make_professional(index, role=role)
            response = self.post_login(user.email)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertNotIn("access_token", response.data.get("data") or {})

    def test_mobile_login_rejects_inactive_missing_profile_and_personal_accounts(self):
        inactive_user = self.make_professional(5)
        User.objects.filter(pk=inactive_user.pk).update(is_active=False)
        inactive_profile = self.make_professional(6, profile_active=False)
        no_profile = self.make_professional(7, profile=False)

        for email in [inactive_user.email, inactive_profile.email, no_profile.email]:
            response = self.post_login(email)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertNotIn("access_token", response.data.get("data") or {})

    def test_mobile_refresh_revalidates_current_role_and_profile_state(self):
        user = self.make_professional(9)
        login = self.post_login(user.email)
        refresh = login.data["data"]["refresh_token"]

        ok_response = self.client.post("/api/auth/mobile/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(ok_response.status_code, status.HTTP_200_OK)
        self.assertTrue(ok_response.data["data"]["access_token"])
        self.assertEqual(ok_response.data["data"]["role"], AgentProfile.Role.AGENT_TERRAIN)

        changed_user = self.make_professional(10)
        changed_login = self.post_login(changed_user.email)
        changed_refresh = changed_login.data["data"]["refresh_token"]
        AgentProfile.objects.filter(user=changed_user).update(role=AgentProfile.Role.AGENT_SAISIE)
        denied = self.client.post("/api/auth/mobile/token/refresh/", {"refresh": changed_refresh}, format="json")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("access_token", denied.data.get("data") or {})