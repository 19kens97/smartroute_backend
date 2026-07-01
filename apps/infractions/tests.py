from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from .catalog import OFFICIAL_INFRACTIONS
from .models import Infraction
from .services import INFRACTION_CATALOG_CACHE_KEY, seed_official_infractions


class InfractionSeedTests(TestCase):
    def test_seed_imports_74_official_infractions_and_is_idempotent(self):
        first = seed_official_infractions()
        self.assertEqual(first["created"], 74)
        self.assertEqual(first["active_count"], 74)
        self.assertEqual(Infraction.objects.filter(active=True).count(), 74)
        self.assertTrue(Infraction.objects.filter(code="I001", number=1).exists())
        self.assertTrue(Infraction.objects.filter(code="I005", number=5).exists())
        self.assertTrue(Infraction.objects.filter(code="I074", number=74).exists())

        second = seed_official_infractions()
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(second["unchanged"], 74)
        self.assertEqual(Infraction.objects.filter(active=True).count(), 74)

    def test_seed_command_reports_counts(self):
        call_command("seed_infractions", verbosity=0)
        self.assertEqual(Infraction.objects.filter(active=True).count(), len(OFFICIAL_INFRACTIONS))

    def test_codes_are_unique_and_uppercase(self):
        seed_official_infractions()
        codes = list(Infraction.objects.values_list("code", flat=True))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(code == code.upper() for code in codes))


class InfractionCatalogApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="agent", password="Pass1234!", role="AGENT_TERRAIN")
        token = self.client.post("/api/auth/token/", {"username": "agent", "password": "Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        cache.clear()

    def test_catalog_lists_only_active_infractions_without_pagination(self):
        seed_official_infractions()
        Infraction.objects.filter(code="I005").update(active=False)
        response = self.client.get("/api/infractions/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["count"], 73)
        self.assertIsNone(data.get("next"))
        codes = [item["code"] for item in data["items"]]
        self.assertIn("I001", codes)
        self.assertIn("I074", codes)
        self.assertNotIn("I005", codes)

    def test_catalog_uses_cache_and_invalidates(self):
        seed_official_infractions()
        first = self.client.get("/api/infractions/")
        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(cache.get(INFRACTION_CATALOG_CACHE_KEY))
        Infraction.objects.filter(code="I001").update(active=False)
        cached = self.client.get("/api/infractions/")
        self.assertEqual(cached.data["data"]["count"], 74)
        cache.delete(INFRACTION_CATALOG_CACHE_KEY)
        fresh = self.client.get("/api/infractions/")
        self.assertEqual(fresh.data["data"]["count"], 73)
