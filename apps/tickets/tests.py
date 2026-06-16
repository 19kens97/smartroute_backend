from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from apps.infractions.models import Infraction
from .models import Ticket

class TicketApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.terrain = User.objects.create_user(username="terrain", password="Pass1234!", role="AGENT_TERRAIN")
        self.other_terrain = User.objects.create_user(username="terrain2", password="Pass1234!", role="AGENT_TERRAIN")
        self.saisie = User.objects.create_user(username="saisie", password="Pass1234!", role="AGENT_SAISIE")
        token = self.client.post("/api/auth/token/", {"username":"terrain","password":"Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.inf = Infraction.objects.create(code="I1", label="Test", amount=100)

    def test_ticket_create_requires_infraction(self):
        r = self.client.post("/api/tickets/", {"driver_license":"D1","plate_number_snapshot":"AA1","infraction_ids":[]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ticket_create_with_infraction(self):
        r = self.client.post("/api/tickets/", {"driver_license":"D1","plate_number_snapshot":"AA1","infraction_ids":[self.inf.id]}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_ticket_create_rejects_invalid_infraction_id(self):
        r = self.client.post("/api/tickets/", {"driver_license":"D1","plate_number_snapshot":"AA1","infraction_ids":[999999]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_agent_terrain_cannot_update_other_agent_ticket(self):
        ticket = Ticket.objects.create(agent=self.other_terrain, driver_license="DX", plate_number_snapshot="BB2")
        r = self.client.patch(f"/api/tickets/{ticket.id}/", {"status": "ISSUED"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_agent_saisie_can_patch_ticket(self):
        ticket = Ticket.objects.create(agent=self.terrain, driver_license="D1", plate_number_snapshot="AA1")
        token = self.client.post("/api/auth/token/", {"username":"saisie","password":"Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        r = self.client.patch(f"/api/tickets/{ticket.id}/", {"status": "PENDING_SYNC"}, format="json")
        self.assertEqual(r.status_code, 200)
