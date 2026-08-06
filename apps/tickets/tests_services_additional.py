from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import AgentProfile, Person, User
from apps.tickets.models import Ticket
from apps.tickets.services import (
    build_open_ticket_summary,
    find_open_ticket,
    generate_unique_ticket_number,
    is_valid_ticket_number,
)


class TicketServiceAdditionalTests(TestCase):
    def setUp(self):
        person = Person.objects.create(nif="140-000-001-0", first_name="Ticket", last_name="Agent")
        self.user = User.objects.create_user(email="ticket@example.com", password="Passw0rd!123", person=person)
        AgentProfile.objects.create(user=self.user, role=AgentProfile.Role.AGENT_TERRAIN, badge_number="14-00-00-00001")

    def test_ticket_number_validation_and_generation_retry(self):
        Ticket.objects.create(opened_by=self.user, ticket_number="ABCDEF12", driver_dossier_snapshot="AB-12345-CD", driver_name_snapshot="Driver")
        with patch("apps.tickets.services.secrets.token_hex", side_effect=["abcdef12", "12345678"]):
            self.assertEqual(generate_unique_ticket_number(), "12345678")

        self.assertTrue(is_valid_ticket_number("1234ABCD"))
        self.assertFalse(is_valid_ticket_number("1234abcd"))
        self.assertFalse(is_valid_ticket_number("XYZ"))

    def test_find_open_ticket_and_summary(self):
        open_ticket = Ticket.objects.create(opened_by=self.user, driver_dossier_snapshot="AB-12345-CD", driver_nif_snapshot="123", driver_name_snapshot="Driver")
        Ticket.objects.create(
            opened_by=self.user,
            status=Ticket.Status.CLOSED,
            closed_by=self.user,
            closure_reason="Payed manually",
            driver_dossier_snapshot="AB-12345-CD",
            driver_nif_snapshot="123",
            driver_name_snapshot="Driver",
        )

        self.assertEqual(find_open_ticket(dossier_number="ab12345cd"), open_ticket)
        self.assertEqual(find_open_ticket(nif="123"), open_ticket)
        self.assertIsNone(find_open_ticket(ticket_number="missing"))

        summary = build_open_ticket_summary([open_ticket])
        self.assertEqual(summary["count"], 1)
        self.assertTrue(summary["has_open_tickets"])
        self.assertEqual(summary["items"][0]["ticket_number"], open_ticket.ticket_number)
