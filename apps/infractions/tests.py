from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import (
    AgentProfile,
    Person,
)

from .catalog import OFFICIAL_INFRACTIONS
from .models import Infraction
from .services import (
    parse_penalty,
    seed_official_infractions,
)


class InfractionPenaltyTests(TestCase):
    def test_fixed_penalty(self):
        parsed = parse_penalty(
            {
                "amount": "1000",
                "penalty_text": "1000",
            }
        )
        self.assertEqual(
            parsed["penalty_type"],
            Infraction.PenaltyType.FIXED,
        )
        self.assertEqual(
            str(parsed["amount"]),
            "1000",
        )

    def test_range_penalty(self):
        parsed = parse_penalty(
            {
                "amount": None,
                "penalty_text": "5000 - 10000",
            }
        )
        self.assertEqual(
            parsed["penalty_type"],
            Infraction.PenaltyType.RANGE,
        )
        self.assertEqual(
            str(parsed["minimum_amount"]),
            "5000",
        )
        self.assertEqual(
            str(parsed["maximum_amount"]),
            "10000",
        )

    def test_multiple_penalty(self):
        parsed = parse_penalty(
            {
                "amount": None,
                "penalty_text": "500 / 1000",
            }
        )
        self.assertEqual(
            parsed["penalty_type"],
            Infraction.PenaltyType.MULTIPLE,
        )
        self.assertEqual(
            parsed["amount_options"],
            ["500", "1000"],
        )

    def test_text_only_and_none_penalties(self):
        text_only = parse_penalty(
            {
                "amount": None,
                "penalty_text": (
                    "500 + frais de remorquage"
                ),
            }
        )
        none_value = parse_penalty(
            {
                "amount": None,
                "penalty_text": "",
            }
        )

        self.assertEqual(
            text_only["penalty_type"],
            Infraction.PenaltyType.TEXT_ONLY,
        )
        self.assertEqual(
            none_value["penalty_type"],
            Infraction.PenaltyType.NONE,
        )


class InfractionSeedTests(TestCase):
    def test_seed_imports_and_is_idempotent(self):
        first = seed_official_infractions()

        self.assertEqual(
            first["created"],
            len(OFFICIAL_INFRACTIONS),
        )
        self.assertEqual(
            first["active_count"],
            74,
        )

        second = seed_official_infractions()

        self.assertEqual(
            second["created"],
            0,
        )
        self.assertEqual(
            second["updated"],
            0,
        )
        self.assertEqual(
            second["unchanged"],
            74,
        )

    def test_seed_structures_range_and_multiple_amounts(self):
        seed_official_infractions()

        range_infraction = Infraction.objects.get(
            code="I021"
        )
        multiple_infraction = (
            Infraction.objects.get(
                code="I040"
            )
        )

        self.assertEqual(
            range_infraction.penalty_type,
            Infraction.PenaltyType.RANGE,
        )
        self.assertEqual(
            multiple_infraction.penalty_type,
            Infraction.PenaltyType.MULTIPLE,
        )

    def test_review_candidates_are_not_confirmed_as_offenses(self):
        seed_official_infractions()

        candidate = Infraction.objects.get(
            code="I021"
        )

        self.assertEqual(
            candidate.legal_classification,
            (
                Infraction.LegalClassification
                .POSSIBLE_OFFENSE
            ),
        )
        self.assertTrue(
            candidate.requires_authority_review
        )
        self.assertNotEqual(
            candidate.legal_classification,
            Infraction.LegalClassification.OFFENSE,
        )

    def test_command_runs(self):
        call_command(
            "seed_infractions",
            verbosity=0,
        )

        self.assertEqual(
            Infraction.objects.filter(
                active=True
            ).count(),
            74,
        )


class InfractionCatalogApiTests(APITestCase):
    password = "Pass1234!Secure"

    def setUp(self):
        self.field = self._professional(
            "infractions.field@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "INF-TER-001",
        )
        self.entry = self._professional(
            "infractions.entry@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "INF-SAI-001",
        )
        self.admin = self._professional(
            "infractions.admin@example.com",
            AgentProfile.Role.ADMIN,
            "INF-ADM-001",
        )
        self.personal = self._personal()

        seed_official_infractions()

    def _professional(
        self,
        email,
        role,
        badge,
    ):
        User = get_user_model()

        person = Person.objects.create(
            nif=badge,
            first_name=role,
            last_name="Infractions",
        )

        user = User.objects.create_user(
            person=person,
            account_type=(
                User.AccountType.PROFESSIONAL
            ),
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

    def _personal(self):
        User = get_user_model()

        person = Person.objects.create(
            nif="INF-PERSONAL-001",
            first_name="Personal",
            last_name="Infractions",
        )

        return User.objects.create_user(
            person=person,
            account_type=(
                User.AccountType.PERSONAL
            ),
            email="",
            password=self.password,
        )

    def test_professional_roles_can_read_catalog(self):
        for user in (
            self.field,
            self.entry,
            self.admin,
        ):
            self.client.force_authenticate(
                user=user
            )

            response = self.client.get(
                "/api/infractions/"
            )

            self.assertEqual(
                response.status_code,
                200,
            )
            self.assertEqual(
                response.data["data"]["count"],
                74,
            )
            self.assertEqual(
                response.data["data"]["currency"],
                "HTG",
            )

    def test_personal_account_cannot_read(self):
        self.client.force_authenticate(
            user=self.personal
        )

        response = self.client.get(
            "/api/infractions/"
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_api_is_read_only(self):
        self.client.force_authenticate(
            user=self.admin
        )

        create_response = self.client.post(
            "/api/infractions/",
            {
                "code": "I999",
                "number": 999,
                "label": "Test",
            },
            format="json",
        )
        delete_response = self.client.delete(
            "/api/infractions/1/"
        )

        self.assertEqual(
            create_response.status_code,
            405,
        )
        self.assertEqual(
            delete_response.status_code,
            405,
        )

    def test_inactive_detail_is_hidden(self):
        infraction = Infraction.objects.get(
            code="I005"
        )
        infraction.active = False
        infraction.save()

        self.client.force_authenticate(
            user=self.field
        )

        response = self.client.get(
            f"/api/infractions/{infraction.pk}/"
        )

        self.assertEqual(
            response.status_code,
            404,
        )
