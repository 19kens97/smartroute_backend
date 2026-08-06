from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from apps.drivers import services


class DriverServiceTests(SimpleTestCase):
    def test_normalizes_dossier_and_lookup_values(self):
        self.assertEqual(services.normalize_dossier_number(" ab12345cd "), "AB-12345-CD")
        self.assertEqual(services.normalize_dossier_lookup_value(" ab-12345-cd "), "AB12345CD")

    def test_normalizes_nif_to_digits_only(self):
        self.assertEqual(services.normalize_nif("123-456 789-0"), "1234567890")
        self.assertEqual(services.normalize_nif(None), "")

    def test_license_validity_states(self):
        today = timezone.localdate()
        valid = type("DriverLike", (), {"issue_date": today - timedelta(days=1), "expires_at": today})()
        expired = type("DriverLike", (), {"issue_date": today - timedelta(days=10), "expires_at": today - timedelta(days=1)})()
        not_yet_valid = type("DriverLike", (), {"issue_date": today + timedelta(days=1), "expires_at": today + timedelta(days=10)})()
        unknown = type("DriverLike", (), {"issue_date": None, "expires_at": today + timedelta(days=10)})()

        self.assertEqual(services.get_license_validity_state(valid, today), services.VALIDITY_VALID)
        self.assertEqual(services.get_license_validity_state(expired, today), services.VALIDITY_EXPIRED)
        self.assertEqual(services.get_license_validity_state(not_yet_valid, today), services.VALIDITY_NOT_YET_VALID)
        self.assertEqual(services.get_license_validity_state(unknown, today), services.VALIDITY_UNKNOWN)
