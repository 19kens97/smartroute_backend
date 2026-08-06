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
from apps.tickets.models import Ticket, TicketVerbalization
from apps.tickets.permissions import TicketPermission


class TicketPermissionMatrixTests(TestCase):
    def setUp(self):
        self.permission = TicketPermission()
        self.admin = create_admin_user(email="ticket.permission.admin@example.com")
        self.terrain = create_agent_terrain_user(email="ticket.permission.terrain@example.com")
        self.other_terrain = create_agent_terrain_user(email="ticket.permission.other@example.com")
        self.saisie = create_agent_saisie_user(email="ticket.permission.saisie@example.com")
        self.personal = create_personal_user(first_name="TicketPerm", last_name="Personal")
        person = create_person(first_name="TicketPerm", last_name="NoProfile")
        self.no_profile = User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email="ticket.permission.no.profile@example.com",
            password="Pass1234!Secure",
        )
        self.inactive_profile = create_agent_terrain_user(email="ticket.permission.profile.inactive@example.com")
        self.inactive_profile.agent_profile.is_active = False
        self.inactive_profile.agent_profile.save()
        self.ticket = Ticket.objects.create(opened_by=self.terrain, driver_dossier_snapshot="AB-12345-CD")
        self.verbalization = TicketVerbalization.objects.create(
            ticket=self.ticket,
            sequence_number=1,
            agent=self.terrain,
            plate_number_snapshot="HT-100",
        )

    def request(self, user):
        return SimpleNamespace(user=user)

    def view(self, action):
        return SimpleNamespace(action=action)

    def test_profile_rejects_invalid_users(self):
        for user in (self.personal, self.no_profile, self.inactive_profile, AnonymousUser(), None):
            with self.subTest(user=getattr(user, "email", user)):
                self.assertIsNone(self.permission._profile(user))

    def test_has_permission_matrix(self):
        cases = [
            ("list", self.admin, True), ("list", self.terrain, True), ("list", self.saisie, True),
            ("create", self.terrain, True), ("create", self.admin, False), ("create", self.saisie, False),
            ("add_verbalization", self.terrain, True), ("add_verbalization", self.saisie, False),
            ("partial_update", self.admin, True), ("partial_update", self.saisie, True), ("partial_update", self.terrain, False),
            ("close", self.admin, True), ("cancel", self.admin, True), ("cancel_verbalization", self.admin, True),
            ("close", self.terrain, False), ("add_proof", self.terrain, True), ("add_proof", self.admin, False),
            ("unknown", self.admin, False), (None, self.admin, False), ("list", self.personal, False),
        ]
        for action, user, expected in cases:
            with self.subTest(action=action, user=getattr(user, "email", user)):
                self.assertIs(self.permission.has_permission(self.request(user), self.view(action)), expected)

    def test_object_permissions_follow_ticket_and_verbalization_state(self):
        for action in self.permission.READ_ACTIONS:
            with self.subTest(action=action):
                self.assertTrue(self.permission.has_object_permission(self.request(self.saisie), self.view(action), self.ticket))

        self.assertTrue(self.permission.has_object_permission(self.request(self.terrain), self.view("add_verbalization"), self.ticket))
        self.ticket.status = Ticket.Status.CLOSED
        self.ticket.closed_by = self.admin
        self.ticket.closure_reason = "Dossier ferme."
        self.ticket.save()
        self.assertFalse(self.permission.has_object_permission(self.request(self.terrain), self.view("add_verbalization"), self.ticket))
        self.assertFalse(self.permission.has_object_permission(self.request(self.admin), self.view("close"), self.ticket))

        self.ticket.status = Ticket.Status.OPEN
        self.ticket.save()
        self.assertTrue(self.permission.has_object_permission(self.request(self.admin), self.view("close"), self.ticket))
        self.assertTrue(self.permission.has_object_permission(self.request(self.saisie), self.view("partial_update"), self.ticket))
        self.ticket.status = Ticket.Status.CANCELLED
        self.ticket.cancelled_by = self.admin
        self.ticket.cancellation_reason = "Dossier annule."
        self.ticket.save()
        self.assertFalse(self.permission.has_object_permission(self.request(self.saisie), self.view("partial_update"), self.ticket))

    def test_proof_permission_is_limited_to_active_verbalization_owner_on_open_ticket(self):
        self.assertTrue(self.permission.has_object_permission(self.request(self.terrain), self.view("add_proof"), self.verbalization))
        self.assertFalse(self.permission.has_object_permission(self.request(self.other_terrain), self.view("add_proof"), self.verbalization))
        self.verbalization.status = TicketVerbalization.Status.CANCELLED
        self.verbalization.cancelled_by = self.admin
        self.verbalization.cancellation_reason = "Erreur terrain."
        self.verbalization.save()
        self.assertFalse(self.permission.has_object_permission(self.request(self.terrain), self.view("add_proof"), self.verbalization))
