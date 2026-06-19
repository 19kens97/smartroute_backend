from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.models import AuditLog
from apps.owners.models import Owner

from .models import Vehicle
from .serializers import VehicleSerializer


class VehicleModelAndSerializerTests(TestCase):
    def setUp(self):
        self.owner = Owner.objects.create(
            full_name="Marie Jean",
            national_id="OWNER-001",
        )

    def test_year_before_1900_is_rejected(self):
        vehicle = Vehicle(plate_number="AA-100", year=1899)
        with self.assertRaises(ValidationError):
            vehicle.full_clean()

    def test_future_year_is_rejected(self):
        vehicle = Vehicle(plate_number="AA-101", year=timezone.localdate().year + 1)
        with self.assertRaises(ValidationError):
            vehicle.full_clean()

    def test_current_year_is_accepted(self):
        vehicle = Vehicle(plate_number="AA-102", year=timezone.localdate().year)
        vehicle.full_clean()

    def test_plate_and_engine_number_are_normalized_on_save(self):
        vehicle = Vehicle.objects.create(
            plate_number="  ab - 123  ",
            engine_number="  eng   42-x ",
        )
        self.assertEqual(vehicle.plate_number, "AB-123")
        self.assertEqual(vehicle.engine_number, "ENG 42-X")

    def test_serializer_exposes_stable_vehicle_contract_and_owner_name(self):
        vehicle = Vehicle.objects.create(
            plate_number="CC-333",
            owner=self.owner,
            year=2020,
            engine_number="engine-9",
        )
        data = VehicleSerializer(vehicle).data
        self.assertEqual(data["owner_name"], "Marie Jean")
        self.assertEqual(data["year"], 2020)
        self.assertEqual(data["engine_number"], "ENGINE-9")
        self.assertEqual(
            set(data),
            {
                "id", "plate_number", "brand", "model", "color", "year",
                "engine_number", "registration_valid_until", "is_wanted", "owner", "owner_name",
                "created_at", "updated_at",
            },
        )

    def test_serializer_normalizes_plate_and_rejects_case_insensitive_duplicate(self):
        Vehicle.objects.create(plate_number="DD-444")
        serializer = VehicleSerializer(data={"plate_number": "  ee - 555 "})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["plate_number"], "EE-555")

        duplicate = VehicleSerializer(data={"plate_number": " dd-444 "})
        self.assertFalse(duplicate.is_valid())
        self.assertIn("plate_number", duplicate.errors)


class VehicleApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.entry = User.objects.create_user(username="vehicle_entry", password="Pass1234!", role="AGENT_SAISIE")
        self.admin = User.objects.create_user(username="vehicle_admin", password="Pass1234!", role="ADMIN")
        self.field = User.objects.create_user(username="vehicle_field", password="Pass1234!", role="AGENT_TERRAIN")
        # Legacy database values remain readable but SUPERVISEUR is no longer a declared role.
        self.supervisor = User.objects.create_user(username="vehicle_supervisor", password="Pass1234!", role="SUPERVISEUR")
        self.owner = Owner.objects.create(full_name="Paul Pierre", national_id="OWNER-API-001")
        self.vehicle = Vehicle.objects.create(
            plate_number="HT-12345",
            owner=self.owner,
            brand="Toyota",
            model="RAV4",
            color="Gris",
            year=2021,
            engine_number="MOT-123",
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_only_entry_agent_can_create(self):
        payload = {"plate_number": "NEW-100", "year": timezone.localdate().year}
        self.authenticate(self.entry)
        response = self.client.post("/api/vehicles/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(object_id=str(response.data["id"]), action="CREATE").exists())

        for user in (self.admin, self.field, self.supervisor):
            self.authenticate(user)
            denied = self.client.post("/api/vehicles/", {"plate_number": f"DENIED-{user.id}"}, format="json")
            self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(user=None)
        unauthenticated = self.client.post("/api/vehicles/", {"plate_number": "ANON-1"}, format="json")
        self.assertEqual(unauthenticated.status_code, 401)

    def test_all_authenticated_roles_can_list_retrieve_and_search(self):
        for user in (self.entry, self.admin, self.field, self.supervisor):
            self.authenticate(user)
            self.assertEqual(self.client.get("/api/vehicles/").status_code, 200)
            self.assertEqual(self.client.get(f"/api/vehicles/{self.vehicle.pk}/").status_code, 200)
            self.assertEqual(self.client.get("/api/vehicles/by-plate/ht-12345/").status_code, 200)

        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/vehicles/").status_code, 401)
        self.assertEqual(self.client.get("/api/vehicles/by-plate/HT-12345/").status_code, 401)

    def test_admin_and_entry_agent_can_put_and_patch(self):
        for user in (self.entry, self.admin):
            self.authenticate(user)
            patch_response = self.client.patch(
                f"/api/vehicles/{self.vehicle.pk}/",
                {"color": f"Color-{user.id}"},
                format="json",
            )
            self.assertEqual(patch_response.status_code, 200)

            put_response = self.client.put(
                f"/api/vehicles/{self.vehicle.pk}/",
                {"plate_number": "HT-12345", "brand": "Toyota", "model": "RAV4"},
                format="json",
            )
            self.assertEqual(put_response.status_code, 200)

        self.assertGreaterEqual(
            AuditLog.objects.filter(object_id=str(self.vehicle.pk), action="UPDATE").count(),
            4,
        )

    def test_field_supervisor_and_anonymous_cannot_update(self):
        for user in (self.field, self.supervisor):
            self.authenticate(user)
            self.assertEqual(
                self.client.patch(f"/api/vehicles/{self.vehicle.pk}/", {"color": "Noir"}, format="json").status_code,
                403,
            )
            self.assertEqual(
                self.client.put(f"/api/vehicles/{self.vehicle.pk}/", {"plate_number": "HT-12345"}, format="json").status_code,
                403,
            )
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.patch(f"/api/vehicles/{self.vehicle.pk}/", {"color": "Noir"}, format="json").status_code,
            401,
        )

    def test_delete_is_method_not_allowed_for_every_authenticated_role(self):
        for user in (self.entry, self.admin, self.field, self.supervisor):
            self.authenticate(user)
            response = self.client.delete(f"/api/vehicles/{self.vehicle.pk}/")
            self.assertEqual(response.status_code, 405)

    def test_exact_plate_search_normalizes_case_spaces_and_preserves_hyphen(self):
        self.authenticate(self.field)
        response = self.client.get("/api/vehicles/by-plate/%20ht-%2012345%20/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["plate_number"], "HT-12345")
        self.assertIsInstance(response.data["data"], dict)
        self.assertEqual(response.data["data"]["owner_name"], "Paul Pierre")
        self.assertIn("year", response.data["data"])
        self.assertIn("engine_number", response.data["data"])

    def test_exact_plate_search_returns_clear_404(self):
        self.authenticate(self.field)
        response = self.client.get("/api/vehicles/by-plate/UNKNOWN-9/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.data["errors"])

    def test_exact_plate_search_uses_select_related_owner(self):
        self.authenticate(self.field)
        with self.assertNumQueries(1):
            response = self.client.get("/api/vehicles/by-plate/HT-12345/")
        self.assertEqual(response.status_code, 200)