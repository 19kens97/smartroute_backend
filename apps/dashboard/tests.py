from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.infractions.models import Infraction
from apps.scans.models import GeminiScan, Scan
from apps.tickets.models import Ticket, TicketInfraction


class DashboardStatisticsTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="stats", password="pass", role="AGENT_TERRAIN")
        self.client.force_authenticate(user=self.user)

    def set_created_at(self, obj, day):
        dt = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time())) + timedelta(hours=10)
        obj.__class__.objects.filter(pk=obj.pk).update(created_at=dt, updated_at=dt)
        obj.refresh_from_db()
        return obj

    def set_scanned_at(self, obj, day):
        dt = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time())) + timedelta(hours=11)
        GeminiScan.objects.filter(pk=obj.pk).update(scanned_at=dt, created_at=dt, updated_at=dt)
        obj.refresh_from_db()
        return obj

    def test_dashboard_returns_seven_days_with_zeroes_and_counts(self):
        today = timezone.localdate()
        first_day = today - timedelta(days=6)
        scan = Scan.objects.create(agent=self.user, plate_number="AA-001")
        self.set_created_at(scan, first_day)
        gemini = GeminiScan.objects.create(agent=self.user, plate_number="BB-002", model_used="gemini", plate_detected=True)
        self.set_scanned_at(gemini, today)
        ticket = Ticket.objects.create(agent=self.user, driver_license="D1", plate_number_snapshot="AA-001")
        self.set_created_at(ticket, today)

        response = self.client.get("/api/dashboard/summary/")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["period"]["days"], 7)
        self.assertEqual(len(data["daily_activity"]), 7)
        self.assertEqual(data["daily_activity"][0]["date"], first_day.isoformat())
        self.assertEqual(data["daily_activity"][0]["scans"], 1)
        self.assertEqual(data["daily_activity"][-1]["scans"], 1)
        self.assertEqual(data["daily_activity"][-1]["tickets"], 1)
        self.assertTrue(any(item["scans"] == 0 and item["tickets"] == 0 for item in data["daily_activity"]))
        self.assertEqual(data["totals"]["scans"], 2)
        self.assertEqual(data["totals"]["tickets"], 1)

    def test_dashboard_counts_distinct_pv_and_top_infractions(self):
        today = timezone.localdate()
        belt = Infraction.objects.create(code="07", label="Ceinture", amount=100)
        speed = Infraction.objects.create(code="12", label="Vitesse", amount=200)
        phone = Infraction.objects.create(code="03", label="Telephone", amount=150)
        ticket_a = self.set_created_at(Ticket.objects.create(agent=self.user, driver_license="A", plate_number_snapshot="AA"), today)
        ticket_b = self.set_created_at(Ticket.objects.create(agent=self.user, driver_license="B", plate_number_snapshot="BB"), today)
        TicketInfraction.objects.create(ticket=ticket_a, infraction=belt, amount_snapshot=belt.amount)
        TicketInfraction.objects.create(ticket=ticket_a, infraction=speed, amount_snapshot=speed.amount)
        TicketInfraction.objects.create(ticket=ticket_b, infraction=speed, amount_snapshot=speed.amount)
        TicketInfraction.objects.create(ticket=ticket_b, infraction=phone, amount_snapshot=phone.amount)

        response = self.client.get("/api/dashboard/summary/")

        data = response.data["data"]
        self.assertEqual(data["totals"]["tickets"], 2)
        self.assertEqual(data["totals"]["infractions"], 4)
        self.assertEqual(data["top_infractions"][0]["number"], "12")
        self.assertEqual(data["top_infractions"][0]["count"], 2)
        self.assertEqual(data["top_infractions"][0]["percentage"], 50.0)
        self.assertLessEqual(len(data["top_infractions"]), 5)

    def test_dashboard_empty_and_authentication(self):
        response = self.client.get("/api/dashboard/summary/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["totals"], {"scans": 0, "tickets": 0, "infractions": 0, "pending_sync": 0})
        self.assertEqual(len(data["daily_activity"]), 7)
        self.assertEqual(data["top_infractions"], [])

        self.client.force_authenticate(user=None)
        denied = self.client.get("/api/dashboard/summary/")
        self.assertEqual(denied.status_code, 401)
