from datetime import date

from django.contrib.auth.tokens import default_token_generator
from django.core import cache, mail
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AgentProfile, Person, User
from apps.accounts.serializers_password_reset import (
    PASSWORD_RESET_EMAIL_NOT_FOUND_MESSAGE,
    PASSWORD_RESET_EMAIL_SENT_MESSAGE,
)
from apps.accounts.throttles import ForgotPasswordThrottle


FORGOT_URL = "/api/auth/forgot-password/"
RESET_URL = "/api/auth/reset-password/"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_MOBILE_URL="smartroutemobile://reset-password",
)
class PasswordResetTests(APITestCase):
    password = "OldPass123!"

    def setUp(self):
        cache.cache.clear()
        mail.outbox = []

    def make_person(self, index):
        return Person.objects.create(
            nif=f"300-000-{index:03d}-{index % 10}",
            first_name="Reset",
            last_name=str(index),
            birth_date=date(1990, 1, 1),
        )

    def make_professional(self, index, *, email=None, user_active=True, profile_active=True, role=AgentProfile.Role.AGENT_TERRAIN):
        user = User.objects.create_user(
            username=f"reset-pro-{index}",
            email=email or f"reset{index}@example.com",
            password=self.password,
            person=self.make_person(index),
            account_type=User.AccountType.PROFESSIONAL,
            is_active=user_active,
        )
        AgentProfile.objects.create(
            user=user,
            role=role,
            badge_number=f"30-00-00-{index:05d}",
            is_active=profile_active,
        )
        return user

    def make_personal(self, index):
        return User.objects.create_user(
            username=f"reset-personal-{index}",
            email="",
            password=self.password,
            person=self.make_person(index),
            account_type=User.AccountType.PERSONAL,
        )

    def post_forgot(self, email):
        return self.client.post(FORGOT_URL, {"email": email}, format="json")

    def reset_payload(self, user, password="NewPass123!"):
        return {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
            "new_password": password,
            "confirm_password": password,
        }

    def assert_public_forgot_response(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn(response.data["message"], {PASSWORD_RESET_EMAIL_SENT_MESSAGE, PASSWORD_RESET_EMAIL_NOT_FOUND_MESSAGE})

    def test_forgot_password_sends_one_email_for_active_professional(self):
        user = self.make_professional(1, email="Agent.Reset@Example.com")

        response = self.post_forgot(" agent.reset@example.com ")

        self.assert_public_forgot_response(response)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("smartroutemobile://reset-password", body)
        self.assertIn("uid=", body)
        self.assertIn("token=", body)
        self.assertNotIn(self.password, body)
        self.assertNotIn(user.agent_profile.role, body)

    def test_forgot_password_does_not_send_for_unknown_personal_or_inactive(self):
        self.make_personal(2)
        inactive = self.make_professional(3, email="inactive@example.com")
        User.objects.filter(pk=inactive.pk).update(is_active=False)

        for email in ["unknown@example.com", "", "personal@example.com", "inactive@example.com"]:
            payload = {"email": email} if email else {}
            response = self.client.post(FORGOT_URL, payload, format="json")
            if email:
                self.assert_public_forgot_response(response)
            else:
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_allows_suspended_agent_profile_if_user_is_active(self):
        user = self.make_professional(4, email="suspended@example.com", profile_active=False)

        response = self.post_forgot(user.email)

        self.assert_public_forgot_response(response)
        self.assertEqual(len(mail.outbox), 1)

    def test_forgot_password_rejects_invalid_email_syntax(self):
        response = self.post_forgot("bad-email")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["errors"])
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_success_changes_password_and_revokes_refresh_token(self):
        user = self.make_professional(5)
        refresh = RefreshToken.for_user(user)

        response = self.client.post(RESET_URL, self.reset_payload(user), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("access_token", response.data["data"])
        self.assertNotIn("refresh_token", response.data["data"])
        user.refresh_from_db()
        self.assertFalse(user.check_password(self.password))
        self.assertTrue(user.check_password("NewPass123!"))
        denied = self.client.post("/api/auth/mobile/token/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertNotEqual(denied.status_code, status.HTTP_200_OK)

    def test_reset_password_rejects_reused_token(self):
        user = self.make_professional(6)
        payload = self.reset_payload(user)

        ok = self.client.post(RESET_URL, payload, format="json")
        reused = self.client.post(RESET_URL, payload, format="json")

        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(reused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", reused.data["errors"])

    def test_reset_password_rejects_invalid_uid_token_mismatch_inactive_and_personal(self):
        user = self.make_professional(7)
        other = self.make_professional(8)
        inactive = self.make_professional(9)
        User.objects.filter(pk=inactive.pk).update(is_active=False)
        personal = self.make_personal(10)

        cases = [
            {"uid": "bad", "token": "bad", "new_password": "NewPass123!", "confirm_password": "NewPass123!"},
            {**self.reset_payload(user), "token": default_token_generator.make_token(other)},
            self.reset_payload(inactive),
            self.reset_payload(personal),
        ]
        for payload in cases:
            response = self.client.post(RESET_URL, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("token", response.data["errors"])

    def test_reset_password_rejects_weak_password_and_confirmation_mismatch(self):
        user = self.make_professional(11)

        mismatch = self.client.post(
            RESET_URL,
            {**self.reset_payload(user), "confirm_password": "OtherPass123!"},
            format="json",
        )
        weak = self.client.post(RESET_URL, self.reset_payload(user, password="123"), format="json")

        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirm_password", mismatch.data["errors"])
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PasswordResetThrottleTests(APITestCase):
    password = "OldPass123!"

    def setUp(self):
        cache.cache.clear()
        mail.outbox = []
        self.previous_rate = getattr(ForgotPasswordThrottle, "rate", None)
        ForgotPasswordThrottle.rate = "2/hour"

    def tearDown(self):
        if self.previous_rate is None:
            delattr(ForgotPasswordThrottle, "rate")
        else:
            ForgotPasswordThrottle.rate = self.previous_rate

    def make_person(self, index):
        return Person.objects.create(
            nif=f"300-000-{index:03d}-{index % 10}",
            first_name="Reset",
            last_name=str(index),
            birth_date=date(1990, 1, 1),
        )

    def make_professional(self, index, *, email=None):
        user = User.objects.create_user(
            username=f"reset-throttle-{index}",
            email=email or f"reset-throttle{index}@example.com",
            password=self.password,
            person=self.make_person(index),
            account_type=User.AccountType.PROFESSIONAL,
        )
        AgentProfile.objects.create(
            user=user,
            role=AgentProfile.Role.AGENT_TERRAIN,
            badge_number=f"31-00-00-{index:05d}",
        )
        return user

    def post_forgot(self, email):
        return self.client.post(FORGOT_URL, {"email": email}, format="json")
    def test_forgot_password_uses_specific_throttle(self):
        self.make_professional(20, email="throttle@example.com")

        first = self.post_forgot("throttle@example.com")
        second = self.post_forgot("throttle@example.com")
        third = self.post_forgot("throttle@example.com")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
