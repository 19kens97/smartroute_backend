from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.infractions.models import Infraction

from .models import Ticket, TicketInfraction, TicketVerbalization
from .services import find_open_ticket


class TicketTestMixin:
    password = "Pass1234!Secure"

    def professional(self, email, role, badge):
        User = get_user_model()
        person = Person.objects.create(
            nif="96" + "".join(ch for ch in badge if ch.isdigit())[-8:].zfill(8),
            first_name=role,
            last_name="Tickets",
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

    def fixed_infraction(self):
        return Infraction.objects.create(
            code="I001",
            number=1,
            label="Infraction fixe",
            official_label="Infraction fixe",
            category=Infraction.Category.CIRCULATION,
            penalty_type=Infraction.PenaltyType.FIXED,
            amount=Decimal("1000.00"),
            penalty_text="1000",
            currency="HTG",
            display_order=1,
        )


class TicketModelTests(TicketTestMixin, TestCase):
    def setUp(self):
        self.agent = self.professional(
            "model.field@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "97-00-00-00001",
        )
        self.infraction = self.fixed_infraction()

    def test_ticket_generates_number_and_barcode_value(self):
        ticket = Ticket.objects.create(
            opened_by=self.agent,
            driver_dossier_snapshot="AB-12345-CD",
        )
        self.assertRegex(ticket.ticket_number, r"^[0-9A-F]{8}$")
        self.assertEqual(ticket.barcode_value, f"PV:{ticket.ticket_number}")

    def test_infraction_snapshot_is_informational_without_selected_amount(self):
        ticket = Ticket.objects.create(
            opened_by=self.agent,
            driver_dossier_snapshot="AB-12345-CD",
        )
        verbalization = TicketVerbalization.objects.create(
            ticket=ticket,
            sequence_number=1,
            agent=self.agent,
            plate_number_snapshot="HT-100",
        )
        link = TicketInfraction.objects.create(
            verbalization=verbalization,
            infraction=self.infraction,
        )
        self.assertEqual(link.amount_snapshot, Decimal("1000.00"))
        self.assertFalse(hasattr(link, "selected_amount"))

    def test_open_ticket_is_found_by_dossier(self):
        ticket = Ticket.objects.create(
            opened_by=self.agent,
            driver_dossier_snapshot="AB-12345-CD",
        )
        self.assertEqual(
            find_open_ticket(dossier_number="ab12345cd"),
            ticket,
        )


class TicketApiTests(TicketTestMixin, APITestCase):
    def setUp(self):
        self.field = self.professional(
            "ticket.field@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "97-00-00-00002",
        )
        self.other_field = self.professional(
            "ticket.other@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "97-00-00-00005",
        )
        self.entry = self.professional(
            "ticket.entry@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "97-00-00-00004",
        )
        self.admin = self.professional(
            "ticket.admin@example.com",
            AgentProfile.Role.ADMIN,
            "97-00-00-00003",
        )
        self.infraction = self.fixed_infraction()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def create_payload(self):
        return {
            "driver_dossier_snapshot": "AB-12345-CD",
            "first_verbalization": {
                "plate_number_snapshot": "HT-100",
                "location_label": "Delmas 33",
                "infraction_codes": [self.infraction.code],
            },
        }

    def test_field_agent_creates_ticket_with_first_verbalization(self):
        self.auth(self.field)
        response = self.client.post(
            "/api/tickets/",
            self.create_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(pk=response.data["id"])
        self.assertEqual(ticket.status, Ticket.Status.OPEN)
        self.assertEqual(ticket.verbalizations.count(), 1)
        self.assertEqual(ticket.verbalizations.first().sequence_number, 1)

    def test_second_control_adds_verbalization_to_open_ticket(self):
        self.auth(self.field)
        created = self.client.post(
            "/api/tickets/",
            self.create_payload(),
            format="json",
        )
        ticket_id = created.data["id"]

        self.auth(self.other_field)
        response = self.client.post(
            f"/api/tickets/{ticket_id}/verbalizations/",
            {
                "plate_number_snapshot": "HT-200",
                "location_label": "Pétion-Ville",
                "infraction_codes": [self.infraction.code],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["sequence_number"], 2)
        self.assertEqual(response.data["data"]["agent"], self.other_field.pk)
        self.assertEqual(TicketVerbalization.objects.filter(ticket_id=ticket_id).count(), 2)

    def test_closed_ticket_rejects_new_verbalization(self):
        ticket = Ticket.objects.create(
            opened_by=self.field,
            driver_dossier_snapshot="AB-12345-CD",
        )
        TicketVerbalization.objects.create(
            ticket=ticket,
            sequence_number=1,
            agent=self.field,
            plate_number_snapshot="HT-100",
        )
        ticket.status = Ticket.Status.CLOSED
        ticket.closed_by = self.admin
        ticket.closure_reason = "Dossier régularisé."
        ticket.save()

        self.auth(self.field)
        response = self.client.post(
            f"/api/tickets/{ticket.pk}/verbalizations/",
            {
                "plate_number_snapshot": "HT-200",
                "infraction_codes": [self.infraction.code],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_barcode_endpoint_returns_svg(self):
        ticket = Ticket.objects.create(
            opened_by=self.field,
            driver_dossier_snapshot="AB-12345-CD",
        )
        self.auth(self.field)
        response = self.client.get(f"/api/tickets/{ticket.pk}/barcode/")
        if response.status_code == 503:
            self.assertIn("code-barres", response.data["message"])
        else:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/svg+xml")

    def test_api_does_not_accept_selected_amount(self):
        self.auth(self.field)
        payload = self.create_payload()
        payload["first_verbalization"]["selected_amount"] = "1000.00"
        response = self.client.post("/api/tickets/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_only_admin_closes_ticket(self):
        ticket = Ticket.objects.create(
            opened_by=self.field,
            driver_dossier_snapshot="AB-12345-CD",
        )
        self.auth(self.entry)
        denied = self.client.post(
            f"/api/tickets/{ticket.pk}/close/",
            {"reason": "Dossier traité."},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.auth(self.admin)
        accepted = self.client.post(
            f"/api/tickets/{ticket.pk}/close/",
            {"reason": "Dossier régularisé."},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.CLOSED)

