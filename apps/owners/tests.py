from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.vehicles.models import Vehicle

from .models import Owner, VehicleOwnership
from .services import set_current_vehicle_owner


class OwnersApiTests(APITestCase):
    password = "Pass1234!Secure"

    def create_professional(self, email, role, badge):
        User = get_user_model()
        person = Person.objects.create(
            nif={"OWN-SAI-001": "910-000-001-0", "OWN-TER-001": "910-000-002-0"}[badge],
            first_name=role,
            last_name="OwnerTest",
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

    def setUp(self):
        self.entry = self.create_professional(
            "entry.owner@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "OWN-SAI-001",
        )
        self.field = self.create_professional(
            "field.owner@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "OWN-TER-001",
        )

    def test_entry_agent_can_create_owner_with_new_person(self):
        self.client.force_authenticate(self.entry)
        response = self.client.post(
            "/api/owners/",
            {
                "person_data": {
                    "nif": "001-234-567-8",
                    "first_name": "Jean",
                    "last_name": "Pierre",
                },
                "phone": "37123456",
                "address": "Delmas 33",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Owner.objects.filter(
                person__nif="001-234-567-8"
            ).exists()
        )

    def test_existing_person_can_be_reused(self):
        person = Person.objects.create(
            nif="910-000-003-0",
            first_name="Marie",
            last_name="Louis",
        )
        self.client.force_authenticate(self.entry)
        response = self.client.post(
            "/api/owners/",
            {"person_id": person.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_field_agent_cannot_create_owner(self):
        self.client.force_authenticate(self.field)
        response = self.client.post(
            "/api/owners/",
            {
                "person_data": {
                    "nif": "910-000-004-0",
                    "first_name": "Test",
                    "last_name": "Terrain",
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_put_and_delete_are_not_allowed(self):
        person = Person.objects.create(
            nif="910-000-005-0",
            first_name="Owner",
            last_name="Locked",
        )
        owner = Owner.objects.create(
            person=person,
            created_by=self.entry,
        )
        self.client.force_authenticate(self.entry)
        self.assertEqual(
            self.client.put(
                f"/api/owners/{owner.id}/",
                {},
                format="json",
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/owners/{owner.id}/"
            ).status_code,
            405,
        )

class VehicleOwnershipConsistencyTests(APITestCase):
    password = "Pass1234!Secure"

    def setUp(self):
        User = get_user_model()
        person = Person.objects.create(nif="910-000-006-0", first_name="Agent", last_name="Saisie")
        self.entry = User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email="ownership.consistency@example.com",
            password=self.password,
        )
        AgentProfile.objects.create(
            user=self.entry,
            role=AgentProfile.Role.AGENT_SAISIE,
            badge_number="OWN-CONS-001",
            is_active=True,
        )
        self.owner_a = self._owner("910-000-007-0", "Owner", "A")
        self.owner_b = self._owner("910-000-008-0", "Owner", "B")
        self.vehicle = Vehicle.objects.create(plate_number="OWN-500")

    def _owner(self, nif, first_name, last_name):
        person = Person.objects.create(nif=nif, first_name=first_name, last_name=last_name)
        return Owner.objects.create(person=person, created_by=self.entry)

    def test_service_creates_current_ownership_and_syncs_vehicle_owner(self):
        ownership = set_current_vehicle_owner(
            vehicle=self.vehicle,
            owner=self.owner_a,
            start_date=date(2026, 1, 1),
            created_by=self.entry,
        )

        self.vehicle.refresh_from_db()
        self.assertTrue(ownership.is_current)
        self.assertEqual(self.vehicle.owner, self.owner_a)
        self.assertEqual(
            VehicleOwnership.objects.filter(vehicle=self.vehicle, is_current=True).count(),
            1,
        )

    def test_service_changes_owner_and_ends_previous_ownership(self):
        first = set_current_vehicle_owner(
            vehicle=self.vehicle,
            owner=self.owner_a,
            start_date=date(2026, 1, 1),
            created_by=self.entry,
        )
        second = set_current_vehicle_owner(
            vehicle=self.vehicle,
            owner=self.owner_b,
            start_date=date(2026, 2, 1),
            created_by=self.entry,
        )

        first.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertEqual(first.end_date, date(2026, 2, 1))
        self.assertTrue(second.is_current)
        self.assertEqual(self.vehicle.owner, self.owner_b)
        self.assertEqual(
            VehicleOwnership.objects.filter(vehicle=self.vehicle, is_current=True).count(),
            1,
        )

    def test_service_reassigning_same_owner_does_not_duplicate(self):
        first = set_current_vehicle_owner(
            vehicle=self.vehicle,
            owner=self.owner_a,
            start_date=date(2026, 1, 1),
            created_by=self.entry,
        )
        second = set_current_vehicle_owner(
            vehicle=self.vehicle,
            owner=self.owner_a,
            start_date=date(2026, 2, 1),
            created_by=self.entry,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(VehicleOwnership.objects.filter(vehicle=self.vehicle).count(), 1)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.owner, self.owner_a)

    def test_vehicle_ownership_api_syncs_vehicle_owner(self):
        self.client.force_authenticate(self.entry)
        first = set_current_vehicle_owner(
            vehicle=self.vehicle,
            owner=self.owner_a,
            start_date=date(2026, 1, 1),
            created_by=self.entry,
        )

        response = self.client.post(
            "/api/owners/vehicle-ownerships/",
            {
                "vehicle": self.vehicle.pk,
                "owner": self.owner_b.pk,
                "ownership_type": VehicleOwnership.OwnershipType.FULL_OWNER,
                "start_date": "2026-03-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        first.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertEqual(first.end_date, date(2026, 3, 1))
        self.assertEqual(self.vehicle.owner, self.owner_b)
        self.assertEqual(response.data["owner"], self.owner_b.pk)
        self.assertEqual(
            VehicleOwnership.objects.filter(vehicle=self.vehicle, is_current=True).count(),
            1,
        )


