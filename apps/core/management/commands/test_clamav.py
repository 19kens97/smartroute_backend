from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from apps.media_storage.services import _scan_with_clamav_tcp, ping_clamav_tcp


EICAR_PARTS = (
    "X5O!P%@AP[4\\PZX54(P^)7CC)7}",
    "$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!",
    "$H+H*",
)


def _eicar_bytes():
    return "".join(EICAR_PARTS).encode("ascii")


class Command(BaseCommand):
    help = "Run an integration check against a real clamd TCP service."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="clamd TCP host. Defaults to ANTIVIRUS_CLAMAV_HOST.")
        parser.add_argument("--port", type=int, default=None, help="clamd TCP port. Defaults to ANTIVIRUS_CLAMAV_PORT.")
        parser.add_argument("--timeout", type=float, default=None, help="Socket timeout seconds. Defaults to ANTIVIRUS_TIMEOUT_SECONDS.")
        parser.add_argument("--skip-unavailable", action="store_true", help="Do not run the invalid-port unavailable check.")

    def handle(self, *args, **options):
        overrides = {}
        if options["host"] is not None:
            overrides["ANTIVIRUS_CLAMAV_HOST"] = options["host"]
        if options["port"] is not None:
            overrides["ANTIVIRUS_CLAMAV_PORT"] = options["port"]
        if options["timeout"] is not None:
            overrides["ANTIVIRUS_TIMEOUT_SECONDS"] = options["timeout"]

        with override_settings(**overrides):
            if not ping_clamav_tcp():
                raise CommandError("clamd PING failed")
            self.stdout.write(self.style.SUCCESS("PING/PONG: OK"))

            clean = SimpleUploadedFile("clean.txt", b"SmartRoute clean antivirus integration test\n", content_type="text/plain")
            clean_result = _scan_with_clamav_tcp(clean)
            if clean_result != "CLEAN":
                raise CommandError(f"clean file scan failed: {clean_result}")
            self.stdout.write(self.style.SUCCESS("Clean file: CLEAN"))

            eicar = SimpleUploadedFile("eicar.txt", _eicar_bytes(), content_type="text/plain")
            eicar_result = _scan_with_clamav_tcp(eicar)
            if eicar_result != "INFECTED":
                raise CommandError(f"EICAR detection failed: {eicar_result}")
            self.stdout.write(self.style.SUCCESS("EICAR: INFECTED"))

            if not options["skip_unavailable"]:
                unavailable_port = 1 if (options["port"] or 3310) != 1 else 2
                with override_settings(ANTIVIRUS_CLAMAV_PORT=unavailable_port, ANTIVIRUS_TIMEOUT_SECONDS=0.2):
                    unavailable = SimpleUploadedFile("clean.txt", b"clean", content_type="text/plain")
                    unavailable_result = _scan_with_clamav_tcp(unavailable)
                    if unavailable_result != "UNAVAILABLE":
                        raise CommandError(f"unavailable scanner check failed: {unavailable_result}")
                self.stdout.write(self.style.SUCCESS("Unavailable scanner: UNAVAILABLE"))