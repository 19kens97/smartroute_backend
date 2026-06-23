from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.owners.models import Owner
from apps.vehicles.models import Vehicle

from .models import InsurancePolicy
from .serializers import InsurancePolicySerializer


class InsurancePolicySerializerTests(TestCase):
    def test_exposes_database_fields_and_computed_validity(self):
        owner = Owner.objects.create(full_name="Marie Joseph", national_id="INS-OWNER-1")
        vehicle = Vehicle.objects.create(plate_number="AA-10001", owner=owner)
        policy = InsurancePolicy.objects.create(
            vehicle=vehicle,
            insurer="OAVCT",
            policy_number="POL-100",
            valid_until=timezone.localdate() + timedelta(days=30),
            status=InsurancePolicy.STATUS_VALID,
        )
        data = InsurancePolicySerializer(policy).data
        self.assertEqual(data["plate_number"], "AA-10001")
        self.assertEqual(data["owner_name"], "Marie Joseph")
        self.assertTrue(data["is_currently_valid"])


class InsurancePolicyApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="insurance_agent", password="Pass1234!", role="AGENT_TERRAIN")
        owner = Owner.objects.create(full_name="Jean Pierre", national_id="INS-OWNER-2")
        self.vehicle = Vehicle.objects.create(plate_number="HT-24680", owner=owner)
        today = timezone.localdate()
        self.expired = InsurancePolicy.objects.create(
            vehicle=self.vehicle, insurer="Ancienne Assurance", policy_number="POL-OLD",
            valid_until=today - timedelta(days=10), status=InsurancePolicy.STATUS_EXPIRED,
        )
        self.active = InsurancePolicy.objects.create(
            vehicle=self.vehicle, insurer="Assurance Active", policy_number="POL-ACTIVE",
            valid_until=today + timedelta(days=90), status=InsurancePolicy.STATUS_VALID,
        )

    def test_requires_authentication(self):
        response = self.client.get("/api/insurance/", {"policy_number": "POL-ACTIVE"})
        self.assertEqual(response.status_code, 401)

    def test_searches_policy_number_case_insensitively(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/insurance/", {"policy_number": "  pol-active  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["owner_name"], "Jean Pierre")
        self.assertTrue(response.data[0]["is_currently_valid"])

    def test_plate_search_normalizes_and_orders_active_policy_first(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/insurance/", {"plate_number": " ht- 24680 "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.active.id, self.expired.id])

    def test_returns_empty_list_when_no_policy_matches(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/insurance/", {"policy_number": "UNKNOWN"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_expired_policy_is_not_currently_valid(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/insurance/", {"policy_number": "POL-OLD"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data[0]["is_currently_valid"])

    def test_search_uses_select_related_vehicle_and_owner(self):
        self.client.force_authenticate(self.user)
        with self.assertNumQueries(1):
            response = self.client.get("/api/insurance/", {"policy_number": "POL-ACTIVE"})
        self.assertEqual(response.status_code, 200)
