from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.test_factories import (
    create_admin_user,
    create_agent_saisie_user,
    create_agent_terrain_user,
    create_person,
    create_personal_user,
)
from apps.sync.permissions import SyncAdminPermission, SyncPermission


class SyncPermissionMatrixTests(TestCase):
    def setUp(self):
        self.admin = create_admin_user(email="sync.permission.admin@example.com")
        self.terrain = create_agent_terrain_user(email="sync.permission.terrain@example.com")
        self.saisie = create_agent_saisie_user(email="sync.permission.saisie@example.com")
        self.personal = create_personal_user(first_name="SyncPerm", last_name="Personal")
        person = create_person(first_name="SyncPerm", last_name="NoProfile")
        self.no_profile = User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email="sync.permission.no.profile@example.com",
            password="Pass1234!Secure",
        )
        self.inactive_user = create_agent_terrain_user(email="sync.permission.inactive@example.com", is_active=False)
        self.inactive_profile = create_agent_terrain_user(email="sync.permission.profile.inactive@example.com")
        self.inactive_profile.agent_profile.is_active = False
        self.inactive_profile.agent_profile.save()

    def request(self, user):
        return SimpleNamespace(user=user)

    def test_sync_permission_allows_active_professional_roles_only(self):
        permission = SyncPermission()
        expectations = [
            (self.admin, True),
            (self.terrain, True),
            (self.saisie, True),
            (self.personal, False),
            (self.no_profile, False),
            (self.inactive_user, False),
            (self.inactive_profile, False),
            (AnonymousUser(), False),
            (None, False),
        ]
        for user, expected in expectations:
            with self.subTest(user=getattr(user, "email", user)):
                self.assertIs(permission.has_permission(self.request(user), None), expected)

    def test_sync_admin_permission_allows_only_active_admin_profile(self):
        permission = SyncAdminPermission()
        expectations = [
            (self.admin, True),
            (self.terrain, False),
            (self.saisie, False),
            (self.personal, False),
            (self.no_profile, False),
            (self.inactive_user, False),
            (self.inactive_profile, False),
            (AnonymousUser(), False),
            (None, False),
        ]
        for user, expected in expectations:
            with self.subTest(user=getattr(user, "email", user)):
                self.assertIs(permission.has_permission(self.request(user), None), expected)
