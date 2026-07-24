from apps.core.management.commands.seed_smartroute_demo import Command as SeedCommand


class Command(SeedCommand):
    help = "Reset and seed the complete SmartRoute demo dataset for local/dev only."

    def handle(self, *args, **options):
        options["reset"] = True
        options["no_reset"] = False
        return super().handle(*args, **options)
