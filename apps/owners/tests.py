from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.vehicles.models import Vehicle

from .models import Owner, VehicleOwnership


class OwnersApiTests(APITestCase):
    password = "Pass1234!Secure"

    def create_professional(self, email, role, badge):
        User = get_user_model()
        person = Person.objects.create(
            nif=f"NIF-{badge}",
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
                person__nif="0012345678"
            ).exists()
        )

    def test_existing_person_can_be_reused(self):
        person = Person.objects.create(
            nif="00998877",
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
                    "nif": "00887766",
                    "first_name": "Test",
                    "last_name": "Terrain",
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_put_and_delete_are_not_allowed(self):
        person = Person.objects.create(
            nif="00445566",
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
