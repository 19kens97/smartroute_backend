from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AgentProfile, Person, User
from apps.reports.services import (
    build_summary,
    get_agent_report_queryset,
    get_ticket_report_queryset,
    parse_date_range,
    serialize_agent_row,
)
from apps.tickets.models import Ticket, TicketVerbalization


class ReportsServiceAdditionalTests(TestCase):
    def setUp(self):
        person = Person.objects.create(nif="150-000-001-0", first_name="Report", last_name="Agent")
        self.user = User.objects.create_user(email="report@example.com", password="Passw0rd!123", person=person)
        AgentProfile.objects.create(user=self.user, role=AgentProfile.Role.AGENT_SAISIE, badge_number="15-00-00-00001")
        self.ticket = Ticket.objects.create(opened_by=self.user, driver_dossier_snapshot="AB-12345-CD", driver_name_snapshot="Driver")
        self.verbalization = TicketVerbalization.objects.create(
            ticket=self.ticket,
            agent=self.user,
            sequence_number=1,
            plate_number_snapshot="AA12345",
            occurred_at=timezone.now(),
            location_label="Port-au-Prince",
        )

    def test_parse_date_range_is_inclusive_and_validates_order(self):
        start, end = parse_date_range({"from": "2026-08-01", "to": "2026-08-03"}, start_key="from", end_key="to")
        self.assertLess(start, end)
        self.assertEqual(start.hour, 0)
        self.assertEqual(end.hour, 23)
        with self.assertRaises(ValueError):
            parse_date_range({"from": "bad"}, start_key="from", end_key="to")
        with self.assertRaises(ValueError):
            parse_date_range({"from": "2026-08-03", "to": "2026-08-01"}, start_key="from", end_key="to")

    def test_ticket_report_queryset_currently_conflicts_with_ticket_property(self):
        queryset = get_ticket_report_queryset({"plate_number": "AA12345"})
        with self.assertRaises(AttributeError):
            list(queryset)

    def test_summary_and_agent_report_aggregate_exact_counts(self):
        summary = build_summary({})
        self.assertEqual(summary["tickets"]["total"], 1)
        self.assertEqual(summary["tickets"]["open"], 1)
        self.assertEqual(summary["verbalizations"]["active"], 1)

        agent = get_agent_report_queryset({"role": AgentProfile.Role.AGENT_SAISIE}).get()
        row = serialize_agent_row(agent)
        self.assertEqual(row["tickets_opened"], 1)
        self.assertEqual(row["verbalizations_created"], 1)
