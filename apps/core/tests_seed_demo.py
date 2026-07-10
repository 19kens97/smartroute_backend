from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import Alert
from apps.insurance.models import InsurancePolicy
from apps.scans.models import GeminiScan, Scan
from apps.tickets.models import Ticket


class SmartRouteDemoSeedTests(TestCase):
    def test_seed_smartroute_demo_covers_core_development_cases(self):
        call_command("seed_smartroute_demo", verbosity=0)

        User = get_user_model()
        milo = User.objects.get(username="milo")
        self.assertTrue(milo.check_password("Kens0001"))
        self.assertEqual(milo.role, User.Role.AGENT_TERRAIN)

        self.assertEqual(
            set(Alert.objects.values_list("alert_type", flat=True)),
            {
                Alert.TYPE_FIELD_ESCAPE,
                Alert.TYPE_REFUSED_CONTROL,
                Alert.TYPE_SUSPICIOUS_BEHAVIOR,
                Alert.TYPE_WANTED_VEHICLE,
                Alert.TYPE_STOLEN_PLATE,
                Alert.TYPE_JUDICIAL,
            },
        )
        self.assertEqual(set(Ticket.objects.values_list("status", flat=True)), {"DRAFT", "PENDING_SYNC", "ISSUED", "VALIDATED", "CANCELLED", "PAID"})
        self.assertEqual(set(InsurancePolicy.objects.values_list("status", flat=True)), {InsurancePolicy.STATUS_VALID, InsurancePolicy.STATUS_EXPIRED, InsurancePolicy.STATUS_SUSPENDED})
        self.assertGreaterEqual(Scan.objects.values("source").distinct().count(), 3)
        self.assertTrue(GeminiScan.objects.filter(plate_detected=True).exists())
        self.assertTrue(GeminiScan.objects.filter(plate_detected=False).exists())

        ticket_days = {
            timezone.localtime(created_at).date()
            for created_at in Ticket.objects.values_list("created_at", flat=True)
        }
        self.assertGreaterEqual(len(ticket_days), 4)

        call_command("seed_smartroute_demo", verbosity=0)
        self.assertEqual(User.objects.filter(username="milo").count(), 1)
        self.assertEqual(Ticket.objects.count(), 7)
