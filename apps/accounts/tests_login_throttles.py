from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.throttles import LoginIdentifierRateThrottle, LoginIpRateThrottle


class LoginThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.original_ip_rate = getattr(LoginIpRateThrottle, "rate", None)
        self.original_identifier_rate = getattr(LoginIdentifierRateThrottle, "rate", None)
        LoginIpRateThrottle.rate = "2/min"
        LoginIdentifierRateThrottle.rate = "2/min"

    def tearDown(self):
        if self.original_ip_rate is None:
            delattr(LoginIpRateThrottle, "rate")
        else:
            LoginIpRateThrottle.rate = self.original_ip_rate
        if self.original_identifier_rate is None:
            delattr(LoginIdentifierRateThrottle, "rate")
        else:
            LoginIdentifierRateThrottle.rate = self.original_identifier_rate
        cache.clear()

    def post_mobile_login(self, email="missing@example.com", ip="127.0.0.1"):
        return self.client.post(
            "/api/auth/mobile/login/",
            {"email": email, "password": "wrong-password"},
            format="json",
            REMOTE_ADDR=ip,
        )

    def test_login_ip_throttle_blocks_repeated_attempts_from_same_ip(self):
        self.assertEqual(self.post_mobile_login("one@example.com").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.post_mobile_login("two@example.com").status_code, status.HTTP_401_UNAUTHORIZED)

        blocked = self.post_mobile_login("three@example.com")

        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_identifier_throttle_blocks_same_identifier_across_ips(self):
        self.assertEqual(self.post_mobile_login("same@example.com", "10.0.0.1").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.post_mobile_login("same@example.com", "10.0.0.2").status_code, status.HTTP_401_UNAUTHORIZED)

        blocked = self.post_mobile_login("same@example.com", "10.0.0.3")

        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_different_ip_and_identifier_remain_under_threshold(self):
        first = self.post_mobile_login("first@example.com", "10.0.1.1")
        second = self.post_mobile_login("second@example.com", "10.0.1.2")

        self.assertEqual(first.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(second.status_code, status.HTTP_401_UNAUTHORIZED)

