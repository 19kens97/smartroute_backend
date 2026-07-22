from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from apps.infractions.services import (
    seed_official_infractions,
)


class Command(BaseCommand):
    help = (
        "Valide et synchronise le catalogue officiel "
        "des infractions DCPR."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--disable-missing",
            action="store_true",
            help=(
                "Désactive les codes présents en base mais "
                "absents du catalogue source."
            ),
        )

    def handle(self, *args, **options):
        result = seed_official_infractions(
            disable_missing=options[
                "disable_missing"
            ]
        )

        if result["errors"]:
            raise CommandError(
                "; ".join(result["errors"])
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Synchronisation terminée : "
                f"created={result['created']} "
                f"updated={result['updated']} "
                f"unchanged={result['unchanged']} "
                f"disabled={result['disabled']} "
                f"active_count={result['active_count']}"
            )
        )
