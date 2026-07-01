from django.core.management.base import BaseCommand, CommandError

from apps.infractions.services import seed_official_infractions


class Command(BaseCommand):
    help = "Seed the official DCPR infraction catalog."

    def handle(self, *args, **options):
        result = seed_official_infractions()
        if result["errors"]:
            raise CommandError("; ".join(result["errors"]))
        self.stdout.write(
            self.style.SUCCESS(
                "Infractions seed completed: "
                f"created={result['created']} updated={result['updated']} "
                f"unchanged={result['unchanged']} disabled={result['disabled']} "
                f"active_count={result['active_count']}"
            )
        )
