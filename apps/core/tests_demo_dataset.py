
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import AgentProfile, Person
from apps.alerts.models import Alert
from apps.drivers.models import Driver
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner, VehicleOwnership
from apps.scans.models import Scan
from apps.tickets.models import Ticket, TicketVerbalization
from apps.vehicles.models import Vehicle


class DemoDatasetCommandTests(TestCase):
    def run_seed(self):
        out = StringIO()
        call_command("reset_smartroute_demo", stdout=out)
        return out.getvalue()

    @override_settings(DEBUG=False, ENVIRONMENT="production")
    def test_command_refuses_non_debug_environment(self):
        with self.assertRaises(CommandError):
            call_command("reset_smartroute_demo", stdout=StringIO())

    def test_command_creates_expected_dataset_and_is_idempotent(self):
        first_output = self.run_seed()
        self.assertIn("Dataset SmartRoute reinitialise avec succes", first_output)

        User = get_user_model()
        self.assertGreaterEqual(User.objects.filter(email__endswith="@smartroute.test", account_type=User.AccountType.PROFESSIONAL).count(), 14)
        self.assertGreaterEqual(User.objects.filter(account_type=User.AccountType.PERSONAL, person__nif__startswith="900").count(), 5)
        self.assertGreaterEqual(AgentProfile.objects.filter(user__email__endswith="@smartroute.test").count(), 14)
        self.assertGreaterEqual(Driver.objects.filter(dossier_number__startswith="DL-100").count(), 10)
        self.assertGreaterEqual(Owner.objects.filter(person__nif__startswith="900").count(), 5)
        self.assertGreaterEqual(Vehicle.objects.filter(plate_number__startswith="SR").count(), 15)
        self.assertGreaterEqual(Scan.objects.count(), 30)
        self.assertGreaterEqual(Ticket.objects.count(), 20)
        self.assertTrue(TicketVerbalization.objects.filter(ticket__in=Ticket.objects.all()).exists())
        self.assertTrue(InsurancePolicy.objects.filter(status=InsurancePolicy.Status.EXPIRED).exists())
        self.assertTrue(Alert.objects.filter(vehicle__plate_number__startswith="SR").exists())

        for vehicle in Vehicle.objects.filter(plate_number__startswith="SR", owner__isnull=False):
            current = VehicleOwnership.objects.get(vehicle=vehicle, is_current=True)
            self.assertEqual(vehicle.owner_id, current.owner_id)
        for vehicle in Vehicle.objects.filter(plate_number__startswith="SR"):
            self.assertLessEqual(VehicleOwnership.objects.filter(vehicle=vehicle, is_current=True).count(), 1)

        counts = {
            "persons": Person.objects.filter(nif__startswith="900").count(),
            "vehicles": Vehicle.objects.filter(plate_number__startswith="SR").count(),
            "tickets": Ticket.objects.count(),
            "scans": Scan.objects.count(),
        }
        self.run_seed()
        self.assertEqual(counts["persons"], Person.objects.filter(nif__startswith="900").count())
        self.assertEqual(counts["vehicles"], Vehicle.objects.filter(plate_number__startswith="SR").count())
        self.assertEqual(counts["tickets"], Ticket.objects.count())
        self.assertEqual(counts["scans"], Scan.objects.count())


