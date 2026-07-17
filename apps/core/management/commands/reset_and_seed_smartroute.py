from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Reset the development/test database and seed a complete SmartRoute dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required explicit confirmation for the destructive reset.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError(
                "Refusing to reset the database without explicit confirmation. "
                "Run: python manage.py reset_and_seed_smartroute --confirm"
            )

        self._assert_safe_environment()

        self.stdout.write(self.style.WARNING("Resetting SmartRoute development/test database..."))
        call_command("flush", interactive=False, verbosity=0)
        call_command("seed_smartroute_demo", verbosity=options.get("verbosity", 1))
        self.stdout.write(self.style.SUCCESS("reset_and_seed_smartroute completed."))

    def _assert_safe_environment(self):
        settings_module = getattr(settings, "SETTINGS_MODULE", "") or ""
        database_name = str(connection.settings_dict.get("NAME", ""))
        engine = str(connection.settings_dict.get("ENGINE", ""))
        allowed_by_settings_module = settings.DEBUG or settings_module.endswith(".dev") or settings_module.endswith(".test")
        allowed_sqlite_dev_db = engine.endswith("sqlite3") and database_name.endswith("db.sqlite3")

        if not (allowed_by_settings_module or allowed_sqlite_dev_db):
            raise CommandError(
                "Refusing to reset this database because the current environment does not look like dev/test. "
                f"settings={settings_module or '<unknown>'}, database={database_name or '<unknown>'}"
            )