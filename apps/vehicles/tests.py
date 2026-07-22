from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.core.models import AuditLog
from apps.owners.models import Owner

from .models import Vehicle

def create_owner(*, nif, first_name, last_name, created_by=None):
    User = get_user_model()
    person = Person.objects.create(
        nif=nif,
        first_name=first_name,
        last_name=last_name,
    )
    if created_by is None:
        creator_person = Person.objects.create(
            nif=f"CREATOR-{nif}",
            first_name="Agent",
            last_name="Createur",
        )
        created_by = User.objects.create_user(
            person=creator_person,
            account_type=User.AccountType.PROFESSIONAL,
            email=f"creator-{nif.lower()}@example.com",
            password="Pass1234!Secure",
        )
    return Owner.objects.create(person=person, created_by=created_by)

from .serializers import (
    VehicleReadSerializer,
    VehicleWriteSerializer,
)


class VehicleModelAndSerializerTests(TestCase):
    def setUp(self):
        self.owner = create_owner(
            nif="OWNER-001",
            first_name="Marie",
            last_name="Jean",
        )

    def test_year_before_1900_is_rejected(self):
        vehicle = Vehicle(
            plate_number="AA-100",
            year=1899,
        )

        with self.assertRaises(ValidationError):
            vehicle.full_clean()

    def test_future_year_is_rejected(self):
        vehicle = Vehicle(
            plate_number="AA-101",
            year=timezone.localdate().year + 1,
        )

        with self.assertRaises(ValidationError):
            vehicle.full_clean()

    def test_current_year_is_accepted(self):
        vehicle = Vehicle(
            plate_number="AA-102",
            year=timezone.localdate().year,
        )
        vehicle.full_clean()

    def test_plate_and_engine_number_are_normalized_on_save(self):
        vehicle = Vehicle.objects.create(
            plate_number="  ab - 123  ",
            engine_number="  eng   42-x ",
        )

        self.assertEqual(
            vehicle.plate_number,
            "AB123",
        )
        self.assertEqual(
            vehicle.engine_number,
            "ENG 42-X",
        )

    def test_read_serializer_exposes_owner_name(self):
        vehicle = Vehicle.objects.create(
            plate_number="CC-333",
            owner=self.owner,
            year=2020,
            engine_number="engine-9",
        )

        data = VehicleReadSerializer(vehicle).data

        self.assertEqual(
            data["owner_name"],
            "Marie Jean",
        )
        self.assertEqual(data["year"], 2020)
        self.assertEqual(
            data["engine_number"],
            "ENGINE-9",
        )

    def test_write_serializer_rejects_legacy_plate_duplicate(self):
        Vehicle.objects.create(
            plate_number="DD-444"
        )

        serializer = VehicleWriteSerializer(
            data={
                "plate_number": "  ee - 555 ",
            }
        )
        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )
        self.assertEqual(
            serializer.validated_data[
                "plate_number"
            ],
            "EE555",
        )

        duplicate = VehicleWriteSerializer(
            data={
                "plate_number": " dd444 ",
            }
        )
        self.assertFalse(
            duplicate.is_valid()
        )
        self.assertIn(
            "plate_number",
            duplicate.errors,
        )


class VehicleApiTests(APITestCase):
    password = "Pass1234!Secure"

    def setUp(self):
        self.entry = self._create_professional_user(
            email="vehicle.entry@example.com",
            role=AgentProfile.Role.AGENT_SAISIE,
            badge_number="VEH-SAI-001",
        )
        self.admin = self._create_professional_user(
            email="vehicle.admin@example.com",
            role=AgentProfile.Role.ADMIN,
            badge_number="VEH-ADM-001",
        )
        self.field = self._create_professional_user(
            email="vehicle.field@example.com",
            role=AgentProfile.Role.AGENT_TERRAIN,
            badge_number="VEH-TER-001",
        )
        self.personal = self._create_personal_user()

        self.owner = create_owner(
            nif="OWNER-API-001",
            first_name="Paul",
            last_name="Pierre",
            created_by=self.entry,
        )
        self.vehicle = Vehicle.objects.create(
            plate_number="HT-12345",
            owner=self.owner,
            brand="Toyota",
            model="RAV4",
            color="Gris",
            year=2021,
            engine_number="MOT-123",
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
            nif=badge_number,
            first_name=role,
            last_name="Vehicle",
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
            nif="VEH-PERSONAL-001",
            first_name="Personal",
            last_name="Vehicle",
        )

        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PERSONAL,
            email="",
            password=self.password,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_only_entry_agent_can_create(self):
        payload = {
            "plate_number": "NEW-100",
            "year": timezone.localdate().year,
        }

        self.authenticate(self.entry)

        response = self.client.post(
            "/api/vehicles/",
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            201,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(response.data["id"]),
                action="CREATE",
            ).exists()
        )

        for user in (
            self.admin,
            self.field,
            self.personal,
        ):
            self.authenticate(user)

            denied = self.client.post(
                "/api/vehicles/",
                {
                    "plate_number": (
                        f"DENIED-{user.id}"
                    )
                },
                format="json",
            )

            self.assertEqual(
                denied.status_code,
                403,
            )

    def test_professional_roles_can_list_retrieve_and_search(self):
        for user in (
            self.entry,
            self.admin,
            self.field,
        ):
            self.authenticate(user)

            self.assertEqual(
                self.client.get(
                    "/api/vehicles/"
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.get(
                    f"/api/vehicles/{self.vehicle.pk}/"
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.get(
                    "/api/vehicles/by-plate/ht-12345/"
                ).status_code,
                200,
            )

    def test_personal_account_cannot_list_or_search(self):
        self.authenticate(self.personal)

        self.assertEqual(
            self.client.get(
                "/api/vehicles/"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/vehicles/by-plate/HT-12345/"
            ).status_code,
            403,
        )

    def test_only_entry_agent_can_patch(self):
        self.authenticate(self.entry)

        response = self.client.patch(
            f"/api/vehicles/{self.vehicle.pk}/",
            {"color": "Noir"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.vehicle.refresh_from_db()
        self.assertEqual(
            self.vehicle.color,
            "Noir",
        )

        for user in (
            self.admin,
            self.field,
            self.personal,
        ):
            self.authenticate(user)

            denied = self.client.patch(
                f"/api/vehicles/{self.vehicle.pk}/",
                {"color": "Interdit"},
                format="json",
            )

            self.assertEqual(
                denied.status_code,
                403,
            )

    def test_put_and_delete_are_not_available(self):
        self.authenticate(self.entry)

        put_response = self.client.put(
            f"/api/vehicles/{self.vehicle.pk}/",
            {},
            format="json",
        )
        delete_response = self.client.delete(
            f"/api/vehicles/{self.vehicle.pk}/"
        )

        self.assertEqual(
            put_response.status_code,
            405,
        )
        self.assertEqual(
            delete_response.status_code,
            405,
        )

    def test_exact_plate_search_normalizes_input(self):
        self.authenticate(self.field)

        response = self.client.get(
            "/api/vehicles/by-plate/%20ht-%2012345%20/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.data["data"]["plate_number"],
            "HT12345",
        )
        self.assertEqual(
            response.data["data"]["owner_name"],
            "Paul Pierre",
        )

    def test_exact_plate_search_supports_legacy_values(self):
        Vehicle.objects.filter(
            pk=self.vehicle.pk
        ).update(
            plate_number="TT-00030"
        )

        self.authenticate(self.field)

        response = self.client.get(
            "/api/vehicles/by-plate/TT-00030/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.data["data"]["plate_number"],
            "TT-00030",
        )

    def test_exact_plate_search_returns_404(self):
        self.authenticate(self.field)

        response = self.client.get(
            "/api/vehicles/by-plate/UNKNOWN-9/"
        )

        self.assertEqual(
            response.status_code,
            404,
        )
        self.assertTrue(
            response.data["errors"]
        )

    def test_exact_plate_search_uses_select_related_owner(self):
        self.authenticate(self.field)

        with self.assertNumQueries(1):
            response = self.client.get(
                "/api/vehicles/by-plate/HT-12345/"
            )

        self.assertEqual(
            response.status_code,
            200,
        )
