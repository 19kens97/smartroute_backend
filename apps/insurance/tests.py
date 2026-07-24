from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.accounts.test_factories import create_agent_saisie_user
from apps.core.models import AuditLog
from apps.owners.models import Owner
from apps.vehicles.models import Vehicle

from .models import InsurancePolicy
from .serializers import (
    InsurancePolicyReadSerializer,
    InsurancePolicyWriteSerializer,
)


class InsurancePolicyModelAndSerializerTests(TestCase):
    def setUp(self):
        self.creator = create_agent_saisie_user(
            email="insurance.model.creator@example.com",
            badge_number="INS-MOD-001",
        )
        owner_person = Person.objects.create(
            nif="INS-OWNER-1",
            first_name="Marie",
            last_name="Joseph",
        )
        self.owner = Owner.objects.create(
            person=owner_person,
            created_by=self.creator,
        )
        self.vehicle = Vehicle.objects.create(
            plate_number="AA-10001",
            owner=self.owner,
        )

    def test_exposes_computed_validity(self):
        policy = InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="OAVCT",
            policy_number="POL-100",
            valid_from=timezone.localdate(),
            valid_until=(
                timezone.localdate()
                + timedelta(days=30)
            ),
            status=InsurancePolicy.Status.VALID,
        )

        data = InsurancePolicyReadSerializer(
            policy
        ).data

        self.assertEqual(
            data["plate_number"],
            "AA10001",
        )
        self.assertEqual(
            data["owner_name"],
            "Marie Joseph",
        )
        self.assertTrue(
            data["is_currently_valid"]
        )

    def test_invalid_period_is_rejected(self):
        policy = InsurancePolicy(
            vehicle=self.vehicle,
            insurer="OAVCT",
            policy_number="POL-INVALID",
            valid_from=timezone.localdate(),
            valid_until=(
                timezone.localdate()
                - timedelta(days=1)
            ),
        )

        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_policy_number_is_normalized(self):
        policy = InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="OAVCT",
            policy_number="  pol  200  ",
            valid_until=(
                timezone.localdate()
                + timedelta(days=10)
            ),
        )

        self.assertEqual(
            policy.policy_number,
            "POL 200",
        )

    def test_write_serializer_rejects_duplicate_policy(self):
        InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="OAVCT",
            policy_number="POL-300",
            valid_until=(
                timezone.localdate()
                + timedelta(days=10)
            ),
        )

        serializer = InsurancePolicyWriteSerializer(
            data={
                "vehicle": self.vehicle.pk,
                "insurer": "Autre",
                "policy_number": " pol-300 ",
                "valid_until": (
                    timezone.localdate()
                    + timedelta(days=20)
                ),
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn(
            "policy_number",
            serializer.errors,
        )


class InsurancePolicyApiTests(APITestCase):
    password = "Pass1234!Secure"

    def setUp(self):
        self.entry = self._create_professional_user(
            email="insurance.entry@example.com",
            role=AgentProfile.Role.AGENT_SAISIE,
            badge_number="INS-SAI-001",
        )
        self.admin = self._create_professional_user(
            email="insurance.admin@example.com",
            role=AgentProfile.Role.ADMIN,
            badge_number="INS-ADM-001",
        )
        self.field = self._create_professional_user(
            email="insurance.field@example.com",
            role=AgentProfile.Role.AGENT_TERRAIN,
            badge_number="INS-TER-001",
        )
        self.personal = self._create_personal_user()

        owner_person = Person.objects.create(
            nif="INS-OWNER-2",
            first_name="Jean",
            last_name="Pierre",
        )
        owner = Owner.objects.create(
            person=owner_person,
            created_by=self.entry,
        )
        self.vehicle = Vehicle.objects.create(
            plate_number="HT-24680",
            owner=owner,
        )

        today = timezone.localdate()

        self.expired = InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="Ancienne Assurance",
            policy_number="POL-OLD",
            valid_from=(
                today - timedelta(days=365)
            ),
            valid_until=(
                today - timedelta(days=10)
            ),
            status=InsurancePolicy.Status.EXPIRED,
        )
        self.active = InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="Assurance Active",
            policy_number="POL-ACTIVE",
            valid_from=today,
            valid_until=(
                today + timedelta(days=90)
            ),
            status=InsurancePolicy.Status.VALID,
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
            last_name="Insurance",
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
            nif="INS-PERSONAL-001",
            first_name="Personal",
            last_name="Insurance",
        )

        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PERSONAL,
            email="",
            password=self.password,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_professional_roles_can_list_and_retrieve(self):
        for user in (
            self.entry,
            self.admin,
            self.field,
        ):
            self.authenticate(user)

            self.assertEqual(
                self.client.get(
                    "/api/insurance/"
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.get(
                    f"/api/insurance/{self.active.pk}/"
                ).status_code,
                200,
            )

    def test_personal_account_cannot_read(self):
        self.authenticate(self.personal)

        response = self.client.get(
            "/api/insurance/"
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_only_entry_agent_can_create(self):
        payload = {
            "vehicle": self.vehicle.pk,
            "insurer": "Nouvelle Assurance",
            "policy_number": "POL-NEW",
            "valid_from": timezone.localdate(),
            "valid_until": (
                timezone.localdate()
                + timedelta(days=365)
            ),
            "status": InsurancePolicy.Status.VALID,
        }

        self.authenticate(self.entry)

        response = self.client.post(
            "/api/insurance/",
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
                "/api/insurance/",
                {
                    **payload,
                    "policy_number": (
                        f"DENIED-{user.pk}"
                    ),
                },
                format="json",
            )

            self.assertEqual(
                denied.status_code,
                403,
            )

    def test_only_entry_agent_can_patch(self):
        self.authenticate(self.entry)

        response = self.client.patch(
            f"/api/insurance/{self.active.pk}/",
            {"insurer": "Assurance Mise à Jour"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for user in (
            self.admin,
            self.field,
            self.personal,
        ):
            self.authenticate(user)

            denied = self.client.patch(
                f"/api/insurance/{self.active.pk}/",
                {"insurer": "Interdit"},
                format="json",
            )

            self.assertEqual(
                denied.status_code,
                403,
            )

    def test_put_and_delete_are_not_available(self):
        self.authenticate(self.entry)

        put_response = self.client.put(
            f"/api/insurance/{self.active.pk}/",
            {},
            format="json",
        )
        delete_response = self.client.delete(
            f"/api/insurance/{self.active.pk}/"
        )

        self.assertEqual(
            put_response.status_code,
            405,
        )
        self.assertEqual(
            delete_response.status_code,
            405,
        )

    def test_searches_policy_number_case_insensitively(self):
        self.authenticate(self.field)

        response = self.client.get(
            "/api/insurance/",
            {
                "policy_number": (
                    "  pol-active  "
                )
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        results = response.data["results"]

        self.assertEqual(
            len(results),
            1,
        )
        self.assertEqual(
            results[0]["owner_name"],
            "Jean Pierre",
        )
        self.assertTrue(
            results[0]["is_currently_valid"]
        )

    def test_plate_search_normalizes_and_orders_active_first(self):
        self.authenticate(self.field)

        response = self.client.get(
            "/api/insurance/",
            {
                "plate_number": (
                    " ht- 24680 "
                )
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        results = response.data["results"]

        self.assertEqual(
            [item["id"] for item in results],
            [
                self.active.id,
                self.expired.id,
            ],
        )

    def test_plate_search_supports_legacy_vehicle_values(self):
        Vehicle.objects.filter(
            pk=self.vehicle.pk
        ).update(
            plate_number="TT-00030"
        )

        self.authenticate(self.field)

        response = self.client.get(
            "/api/insurance/",
            {"plate_number": "TT-00030"},
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            len(response.data["results"]),
            2,
        )

    def test_expired_policy_is_not_currently_valid(self):
        self.authenticate(self.field)

        response = self.client.get(
            "/api/insurance/",
            {"policy_number": "POL-OLD"},
        )

        self.assertFalse(
            response.data["results"][0][
                "is_currently_valid"
            ]
        )

    def test_search_uses_select_related_vehicle_and_owner(self):
        self.authenticate(self.field)

        with self.assertNumQueries(2):
            response = self.client.get(
                "/api/insurance/",
                {"policy_number": "POL-ACTIVE"},
            )

        self.assertEqual(
            response.status_code,
            200,
        )
