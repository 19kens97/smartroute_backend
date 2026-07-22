from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import AgentProfile
from apps.delits.models import DelitCase
from apps.tickets.models import Ticket, TicketVerbalization


class SmartRouteDemoSeedTests(TestCase):
    """
    Tests d'intégration du jeu de démonstration actuel.

    Ces tests imposent la nouvelle architecture :
    - rôle dans AgentProfile ;
    - type de compte dans User ;
    - tickets OPEN/CLOSED/CANCELLED ;
    - verbalizations séparées ;
    - dossiers de délits distincts.
    """

    def test_seed_is_idempotent_and_uses_current_architecture(self):
        call_command("seed_smartroute_demo", verbosity=0)

        User = get_user_model()
        professional_users = User.objects.filter(
            account_type=User.AccountType.PROFESSIONAL,
            agent_profile__isnull=False,
        )
        self.assertTrue(professional_users.exists())
        self.assertTrue(
            AgentProfile.objects.filter(is_active=True).exists()
        )

        invalid_ticket_statuses = set(
            Ticket.objects.values_list("status", flat=True)
        ) - {
            Ticket.Status.OPEN,
            Ticket.Status.CLOSED,
            Ticket.Status.CANCELLED,
        }
        self.assertEqual(invalid_ticket_statuses, set())

        self.assertTrue(Ticket.objects.exists())
        self.assertTrue(TicketVerbalization.objects.exists())

        first_counts = {
            "users": User.objects.count(),
            "tickets": Ticket.objects.count(),
            "verbalizations": TicketVerbalization.objects.count(),
            "delits": DelitCase.objects.count(),
        }

        call_command("seed_smartroute_demo", verbosity=0)

        second_counts = {
            "users": User.objects.count(),
            "tickets": Ticket.objects.count(),
            "verbalizations": TicketVerbalization.objects.count(),
            "delits": DelitCase.objects.count(),
        }
        self.assertEqual(first_counts, second_counts)

    def test_reset_command_requires_confirmation(self):
        with self.assertRaises(Exception):
            call_command(
                "reset_and_seed_smartroute",
                verbosity=0,
            )
