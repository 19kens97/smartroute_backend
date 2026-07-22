from django.core.management.base import BaseCommand

from apps.alerts.services import expire_field_alerts


class Command(BaseCommand):
    help = (
        "Passe les alertes terrain actives et arrivées "
        "à échéance au statut EXPIRED."
    )

    def handle(self, *args, **options):
        count = expire_field_alerts()

        self.stdout.write(
            self.style.SUCCESS(
                f"{count} alerte(s) terrain expirée(s)."
            )
        )
