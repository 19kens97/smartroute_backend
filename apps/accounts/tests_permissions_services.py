from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AgentProfile, Person, User
from apps.accounts.permissions import (
    HasActiveAgentProfile,
    IsAdmin,
    IsAdminOrAgentSaisie,
    IsAgentTerrain,
    IsAgentTerrainOrAgentSaisie,
    IsPersonalAccount,
    IsProfessionalAccount,
)
from apps.accounts.services.token import revoke_all_user_refresh_tokens


def create_user(*, role=None, account_type=User.AccountType.PROFESSIONAL, active=True, profile_active=True, suffix="001"):
    person = Person.objects.create(nif=f"100-000-{int(suffix):03d}-0", first_name="Test", last_name=f"User{suffix}")
    user = User.objects.create_user(
        email=f"user{suffix}@example.com" if account_type == User.AccountType.PROFESSIONAL else "",
        password="Passw0rd!123",
        person=person,
        account_type=account_type,
        is_active=active,
    )
    if role:
        AgentProfile.objects.create(user=user, role=role, badge_number=f"10-00-00-0{int(suffix):04d}", is_active=profile_active)
    return user


class AccountPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_professional_and_personal_account_permissions(self):
        professional = create_user(role=AgentProfile.Role.AGENT_TERRAIN, suffix="001")
        personal = create_user(account_type=User.AccountType.PERSONAL, suffix="002")

        self.assertTrue(IsProfessionalAccount().has_permission(self._request(professional), SimpleNamespace()))
        self.assertFalse(IsProfessionalAccount().has_permission(self._request(personal), SimpleNamespace()))
        self.assertTrue(IsPersonalAccount().has_permission(self._request(personal), SimpleNamespace()))
        self.assertFalse(IsPersonalAccount().has_permission(self._request(professional), SimpleNamespace()))

    def test_agent_role_permissions_require_active_profile_and_expected_role(self):
        admin = create_user(role=AgentProfile.Role.ADMIN, suffix="003")
        terrain = create_user(role=AgentProfile.Role.AGENT_TERRAIN, suffix="004")
        saisie = create_user(role=AgentProfile.Role.AGENT_SAISIE, suffix="005")
        inactive_profile = create_user(role=AgentProfile.Role.AGENT_TERRAIN, profile_active=False, suffix="006")

        self.assertTrue(HasActiveAgentProfile().has_permission(self._request(admin), SimpleNamespace()))
        self.assertFalse(HasActiveAgentProfile().has_permission(self._request(inactive_profile), SimpleNamespace()))
        self.assertTrue(IsAdmin().has_permission(self._request(admin), SimpleNamespace()))
        self.assertTrue(IsAgentTerrain().has_permission(self._request(terrain), SimpleNamespace()))
        self.assertFalse(IsAgentTerrain().has_permission(self._request(saisie), SimpleNamespace()))
        self.assertTrue(IsAdminOrAgentSaisie().has_permission(self._request(admin), SimpleNamespace()))
        self.assertTrue(IsAdminOrAgentSaisie().has_permission(self._request(saisie), SimpleNamespace()))
        self.assertFalse(IsAdminOrAgentSaisie().has_permission(self._request(terrain), SimpleNamespace()))
        self.assertTrue(IsAgentTerrainOrAgentSaisie().has_permission(self._request(terrain), SimpleNamespace()))
        self.assertTrue(IsAgentTerrainOrAgentSaisie().has_permission(self._request(saisie), SimpleNamespace()))


class TokenRevocationServiceTests(TestCase):
    def test_revoke_all_user_refresh_tokens_blacklists_only_target_user(self):
        target = create_user(role=AgentProfile.Role.AGENT_TERRAIN, suffix="007")
        other = create_user(role=AgentProfile.Role.AGENT_TERRAIN, suffix="008")
        target_refresh_1 = RefreshToken.for_user(target)
        target_refresh_2 = RefreshToken.for_user(target)
        other_refresh = RefreshToken.for_user(other)
        target_refresh_1.blacklist()

        revoked = revoke_all_user_refresh_tokens(target)

        self.assertEqual(revoked, 1)
        self.assertEqual(OutstandingToken.objects.filter(user=target).count(), 2)
        self.assertEqual(OutstandingToken.objects.filter(user=other).count(), 1)
        self.assertTrue(hasattr(OutstandingToken.objects.get(jti=str(target_refresh_2["jti"])), "blacklistedtoken"))
        self.assertFalse(hasattr(OutstandingToken.objects.get(jti=str(other_refresh["jti"]), user=other), "blacklistedtoken"))

    def test_revoke_user_without_tokens_returns_zero(self):
        target = create_user(role=AgentProfile.Role.AGENT_TERRAIN, suffix="009")
        self.assertEqual(revoke_all_user_refresh_tokens(target), 0)
