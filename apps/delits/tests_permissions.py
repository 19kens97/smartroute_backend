from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import AgentProfile, User
from apps.accounts.test_factories import (
    create_admin_user,
    create_agent_saisie_user,
    create_agent_terrain_user,
    create_person,
    create_personal_user,
)
from apps.delits.models import DelitAction, DelitCase, DelitType
from apps.delits.permissions import DelitPermission


class DelitPermissionTestCase(TestCase):
    READ_ACTIONS = ("list", "retrieve", "evidence_download")
    EDIT_ACTIONS = ("partial_update", "add_action", "add_evidence", "submit_review")
    ADMIN_ACTIONS = ("confirm", "reject", "refer", "close", "cancel")

    def setUp(self):
        self.permission = DelitPermission()
        self.factory = APIRequestFactory()
        self.admin = create_admin_user(email="delit.admin@example.com")
        self.agent = create_agent_terrain_user(email="delit.terrain@example.com")
        self.other_agent = create_agent_terrain_user(email="delit.other@example.com")
        self.saisie = create_agent_saisie_user(email="delit.saisie@example.com")
        self.personal = create_personal_user()
        self.professional_without_profile = self._create_professional_without_profile()
        self.inactive_user = create_agent_terrain_user(email="delit.inactive@example.com", is_active=False)
        self.inactive_profile_user = create_agent_terrain_user(email="delit.profile.inactive@example.com")
        self.inactive_profile_user.agent_profile.is_active = False
        self.inactive_profile_user.agent_profile.save()
        self.delit_type = DelitType.objects.create(code="PERM", label="Permission delit")
        self.case = self.make_case(detected_by=self.agent)

    def _create_professional_without_profile(self):
        person = create_person(first_name="No", last_name="Profile")
        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email="delit.no.profile@example.com",
            password="Pass1234!Secure",
        )

    def request_for(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def view_for(self, action):
        return SimpleNamespace(action=action)

    def make_case(
        self,
        *,
        detected_by,
        qualification_status=DelitCase.QualificationStatus.POTENTIAL,
        procedure_status=DelitCase.ProcedureStatus.OPEN,
    ):
        case = DelitCase.objects.create(
            delit_type=self.delit_type,
            detected_by=detected_by,
            facts="Faits suffisamment detailles pour tester les permissions.",
            plate_number_snapshot=f"AA-{DelitCase.objects.count() + 10000}",
            source_type=DelitCase.SourceType.PLATE_SCAN,
            qualification_status=DelitCase.QualificationStatus.POTENTIAL,
            procedure_status=DelitCase.ProcedureStatus.OPEN,
        )
        if (
            qualification_status != DelitCase.QualificationStatus.POTENTIAL
            or procedure_status != DelitCase.ProcedureStatus.OPEN
        ):
            DelitCase.objects.filter(pk=case.pk).update(
                qualification_status=qualification_status,
                procedure_status=procedure_status,
            )
            case.refresh_from_db()
        return case

    def assert_has_permission(self, user, action, expected):
        allowed = self.permission.has_permission(self.request_for(user), self.view_for(action))
        self.assertIs(allowed, expected)

    def assert_has_object_permission(self, user, action, obj, expected):
        allowed = self.permission.has_object_permission(self.request_for(user), self.view_for(action), obj)
        self.assertIs(allowed, expected)


class DelitProfilePermissionTests(DelitPermissionTestCase):
    def test_profile_returns_active_professional_agent_profile(self):
        self.assertEqual(self.permission._profile(self.agent), self.agent.agent_profile)

    def test_profile_returns_none_for_missing_user(self):
        self.assertIsNone(self.permission._profile(None))

    def test_profile_returns_none_for_anonymous_user(self):
        self.assertIsNone(self.permission._profile(AnonymousUser()))

    def test_profile_returns_none_for_inactive_user(self):
        self.assertIsNone(self.permission._profile(self.inactive_user))

    def test_profile_returns_none_for_personal_account(self):
        self.assertIsNone(self.permission._profile(self.personal))

    def test_profile_returns_none_for_professional_without_agent_profile(self):
        self.assertFalse(hasattr(self.professional_without_profile, "agent_profile"))
        self.assertIsNone(self.permission._profile(self.professional_without_profile))

    def test_profile_returns_none_for_inactive_agent_profile(self):
        self.assertIsNone(self.permission._profile(self.inactive_profile_user))


class DelitHasPermissionTests(DelitPermissionTestCase):
    def test_read_actions_allow_all_active_professional_roles(self):
        for action in self.READ_ACTIONS:
            for user in (self.admin, self.agent, self.saisie):
                with self.subTest(action=action, role=user.agent_profile.role):
                    self.assert_has_permission(user, action, True)

    def test_read_actions_reject_invalid_profiles(self):
        invalid_users = (
            self.personal,
            self.professional_without_profile,
            self.inactive_profile_user,
            self.inactive_user,
            AnonymousUser(),
        )
        for action in self.READ_ACTIONS:
            for user in invalid_users:
                with self.subTest(action=action, user=type(user).__name__):
                    self.assert_has_permission(user, action, False)

    def test_create_is_reserved_to_agent_terrain_at_general_permission_level(self):
        expectations = (
            (self.agent, True),
            (self.admin, False),
            (self.saisie, False),
            (self.personal, False),
            (AnonymousUser(), False),
        )
        for user, expected in expectations:
            with self.subTest(user=getattr(user, "email", "anonymous")):
                self.assert_has_permission(user, "create", expected)

    def test_operational_edit_actions_are_general_permission_only_for_professional_roles(self):
        for action in self.EDIT_ACTIONS:
            for user, expected in (
                (self.admin, True),
                (self.agent, True),
                (self.saisie, True),
                (self.personal, False),
                (AnonymousUser(), False),
            ):
                with self.subTest(action=action, user=getattr(user, "email", "anonymous")):
                    self.assert_has_permission(user, action, expected)

    def test_administrative_actions_are_reserved_to_admin_at_general_permission_level(self):
        for action in self.ADMIN_ACTIONS:
            for user, expected in (
                (self.admin, True),
                (self.agent, False),
                (self.saisie, False),
                (self.personal, False),
                (AnonymousUser(), False),
            ):
                with self.subTest(action=action, user=getattr(user, "email", "anonymous")):
                    self.assert_has_permission(user, action, expected)

    def test_unknown_action_is_rejected_for_every_role_including_admin(self):
        for user in (self.admin, self.agent, self.saisie, self.personal, AnonymousUser()):
            with self.subTest(user=getattr(user, "email", "anonymous")):
                self.assert_has_permission(user, "unknown_action", False)

    def test_missing_or_none_action_is_rejected(self):
        request = self.request_for(self.admin)
        self.assertIs(self.permission.has_permission(request, SimpleNamespace()), False)
        self.assertIs(self.permission.has_permission(request, self.view_for(None)), False)


class DelitHasObjectPermissionTests(DelitPermissionTestCase):
    def test_object_permission_rejects_invalid_profiles(self):
        for user in (
            AnonymousUser(),
            self.personal,
            self.professional_without_profile,
            self.inactive_profile_user,
            self.inactive_user,
        ):
            with self.subTest(user=getattr(user, "email", "anonymous")):
                self.assert_has_object_permission(user, "retrieve", self.case, False)

    def test_read_object_actions_allow_all_active_professional_roles(self):
        for action in self.READ_ACTIONS:
            for user in (self.admin, self.agent, self.saisie):
                with self.subTest(action=action, role=user.agent_profile.role):
                    self.assert_has_object_permission(user, action, self.case, True)

    def test_admin_has_object_permission_for_every_action_including_unknown_action(self):
        for action in self.EDIT_ACTIONS + self.ADMIN_ACTIONS + ("unknown_action",):
            with self.subTest(action=action):
                self.assert_has_object_permission(self.admin, action, self.case, True)

    def test_agent_terrain_can_edit_own_potential_open_case(self):
        for action in self.EDIT_ACTIONS:
            with self.subTest(action=action):
                self.assert_has_object_permission(self.agent, action, self.case, True)

    def test_agent_terrain_cannot_edit_case_detected_by_another_agent(self):
        for action in self.EDIT_ACTIONS:
            with self.subTest(action=action):
                self.assert_has_object_permission(self.other_agent, action, self.case, False)

    def test_agent_terrain_cannot_edit_non_potential_cases(self):
        alternatives = (
            DelitCase.QualificationStatus.UNDER_REVIEW,
            DelitCase.QualificationStatus.CONFIRMED,
            DelitCase.QualificationStatus.REJECTED,
        )
        for status in alternatives:
            case = self.make_case(detected_by=self.agent, qualification_status=status)
            with self.subTest(qualification_status=status):
                self.assert_has_object_permission(self.agent, "partial_update", case, False)

    def test_agent_terrain_cannot_edit_non_open_cases(self):
        alternatives = (
            DelitCase.ProcedureStatus.ACTION_TAKEN,
            DelitCase.ProcedureStatus.REFERRED,
            DelitCase.ProcedureStatus.CLOSED,
            DelitCase.ProcedureStatus.CANCELLED,
        )
        for status in alternatives:
            case = self.make_case(detected_by=self.agent, procedure_status=status)
            with self.subTest(procedure_status=status):
                self.assert_has_object_permission(self.agent, "partial_update", case, False)

    def test_agent_saisie_can_edit_cases_that_are_not_closed_or_cancelled(self):
        allowed_statuses = (
            DelitCase.ProcedureStatus.OPEN,
            DelitCase.ProcedureStatus.ACTION_TAKEN,
            DelitCase.ProcedureStatus.REFERRED,
        )
        for status in allowed_statuses:
            case = self.make_case(detected_by=self.agent, procedure_status=status)
            with self.subTest(procedure_status=status):
                self.assert_has_object_permission(self.saisie, "partial_update", case, True)

    def test_agent_saisie_cannot_edit_closed_or_cancelled_cases(self):
        for status in (DelitCase.ProcedureStatus.CLOSED, DelitCase.ProcedureStatus.CANCELLED):
            case = self.make_case(detected_by=self.agent, procedure_status=status)
            with self.subTest(procedure_status=status):
                self.assert_has_object_permission(self.saisie, "partial_update", case, False)

    def test_agent_saisie_cannot_run_administrative_action_at_object_level(self):
        self.assert_has_object_permission(self.saisie, "confirm", self.case, False)

    def test_agent_terrain_cannot_run_administrative_actions_at_object_level(self):
        for action in ("confirm", "reject", "close", "cancel"):
            with self.subTest(action=action):
                self.assert_has_object_permission(self.agent, action, self.case, False)

    def test_unknown_action_is_rejected_for_non_admin_professional_roles(self):
        for user in (self.agent, self.saisie):
            with self.subTest(role=user.agent_profile.role):
                self.assert_has_object_permission(user, "unknown_action", self.case, False)


class DelitPermissionAPITests(DelitPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def create_payload(self, suffix="create"):
        return {
            "delit_type": self.delit_type.pk,
            "facts": f"Faits observes pour le dossier {suffix}.",
            "plate_number_snapshot": f"BB-{DelitCase.objects.count() + 10000}",
        }

    def test_api_list_allows_professional_roles_and_rejects_personal_and_anonymous(self):
        url = reverse("delit-list")
        for user, expected_status in (
            (self.admin, 200),
            (self.agent, 200),
            (self.saisie, 200),
            (self.personal, 403),
        ):
            with self.subTest(user=getattr(user, "email", "anonymous")):
                self.authenticate(user)
                self.assertEqual(self.client.get(url).status_code, expected_status)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_api_create_is_allowed_only_for_agent_terrain(self):
        url = reverse("delit-list")
        for user, expected_status in (
            (self.agent, 201),
            (self.admin, 403),
            (self.saisie, 403),
            (self.personal, 403),
        ):
            with self.subTest(user=getattr(user, "email", "anonymous")):
                self.authenticate(user)
                response = self.client.post(url, self.create_payload(user.email), format="json")
                self.assertEqual(response.status_code, expected_status)

    def test_api_agent_terrain_patch_is_limited_to_own_potential_open_case(self):
        url = reverse("delit-detail", args=[self.case.pk])
        self.authenticate(self.agent)
        response = self.client.patch(url, {"facts": "Faits mis a jour par agent terrain."}, format="json")
        self.assertEqual(response.status_code, 200)

        other_case = self.make_case(detected_by=self.other_agent)
        response = self.client.patch(
            reverse("delit-detail", args=[other_case.pk]),
            {"facts": "Tentative sur dossier autre agent."},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        reviewed_case = self.make_case(
            detected_by=self.agent,
            qualification_status=DelitCase.QualificationStatus.UNDER_REVIEW,
        )
        response = self.client.patch(
            reverse("delit-detail", args=[reviewed_case.pk]),
            {"facts": "Tentative sur dossier non potentiel."},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        closed_case = self.make_case(detected_by=self.agent, procedure_status=DelitCase.ProcedureStatus.CLOSED)
        response = self.client.patch(
            reverse("delit-detail", args=[closed_case.pk]),
            {"facts": "Tentative sur dossier ferme."},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_api_agent_saisie_patch_depends_on_procedure_status(self):
        self.authenticate(self.saisie)
        open_case = self.make_case(detected_by=self.agent)
        response = self.client.patch(
            reverse("delit-detail", args=[open_case.pk]),
            {"facts": "Faits corriges par agent de saisie."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        for status in (DelitCase.ProcedureStatus.CLOSED, DelitCase.ProcedureStatus.CANCELLED):
            case = self.make_case(detected_by=self.agent, procedure_status=status)
            with self.subTest(procedure_status=status):
                response = self.client.patch(
                    reverse("delit-detail", args=[case.pk]),
                    {"facts": "Tentative sur dossier non modifiable."},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)

    def test_api_administrative_confirm_action_is_reserved_to_admin(self):
        url = reverse("delit-confirm", args=[self.case.pk])
        for user, expected_status in (
            (self.admin, 200),
            (self.agent, 403),
            (self.saisie, 403),
        ):
            with self.subTest(role=user.agent_profile.role):
                case = self.make_case(detected_by=self.agent)
                self.authenticate(user)
                response = self.client.post(
                    reverse("delit-confirm", args=[case.pk]),
                    {"reason": "Motif administratif valide."},
                    format="json",
                )
                self.assertEqual(response.status_code, expected_status)

    def test_api_add_action_follows_object_permission_rules(self):
        payload = {
            "action_type": DelitAction.ActionType.IDENTITY_CHECK,
            "description": "Controle effectue sur place.",
        }
        self.authenticate(self.agent)
        response = self.client.post(reverse("delit-add-action", args=[self.case.pk]), payload, format="json")
        self.assertEqual(response.status_code, 201)

        other_case = self.make_case(detected_by=self.other_agent)
        response = self.client.post(reverse("delit-add-action", args=[other_case.pk]), payload, format="json")
        self.assertEqual(response.status_code, 403)
