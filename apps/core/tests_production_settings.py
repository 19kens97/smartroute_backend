from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.production_checks import PRODUCTION_SECURITY_SETTINGS, coerce_bool, normalize_hosts, validate_production_settings


class ProductionSettingsValidationTests(SimpleTestCase):
    def valid_settings(self, **overrides):
        values = {
            "secret_key": "prod-secret-key-with-more-than-32-characters",
            "debug": False,
            "allowed_hosts": ["api.smartroute.example"],
            "cors_allow_all_origins": False,
            "api_response_logging_include_body": False,
        }
        values.update(overrides)
        return values

    def assert_invalid(self, message_fragment, **overrides):
        with self.assertRaises(ImproperlyConfigured) as context:
            validate_production_settings(**self.valid_settings(**overrides))
        self.assertIn(message_fragment, str(context.exception))

    def test_valid_production_settings_are_accepted(self):
        validate_production_settings(**self.valid_settings())

    def test_secret_key_is_required_and_cannot_be_placeholder(self):
        for value in (
            "unsafe-dev-key",
            "change-me",
            "changeme",
            "change-me-with-at-least-32-characters",
            "your-secret-key",
            "replace-me",
            "replace-with-a-real-long-random-secret",
            "secret",
            "placeholder",
            "django-insecure-example",
            "",
        ):
            self.assert_invalid("SECRET_KEY", secret_key=value)

    def test_debug_true_is_rejected(self):
        for value in (True, "True", "true", "1", "yes", "on"):
            self.assert_invalid("DEBUG", debug=value)

    def test_debug_false_values_are_accepted(self):
        for value in (False, "False", "false", "0", "no", "off"):
            validate_production_settings(**self.valid_settings(debug=value))

    def test_allowed_hosts_wildcard_is_rejected(self):
        self.assert_invalid("ALLOWED_HOSTS", allowed_hosts=["*"])
        self.assert_invalid("ALLOWED_HOSTS", allowed_hosts="api.smartroute.example, *")

    def test_allowed_hosts_comma_string_is_normalized(self):
        self.assertEqual(
            normalize_hosts(" api.smartroute.ht, admin.smartroute.ht "),
            ["api.smartroute.ht", "admin.smartroute.ht"],
        )
        validate_production_settings(
            **self.valid_settings(
                allowed_hosts=" api.smartroute.ht, admin.smartroute.ht "
            )
        )

    def test_allowed_hosts_empty_is_rejected(self):
        self.assert_invalid("ALLOWED_HOSTS", allowed_hosts=[])

    def test_cors_allow_all_origins_true_is_rejected(self):
        for value in (True, "True", "true", "1", "yes", "on"):
            self.assert_invalid("CORS_ALLOW_ALL_ORIGINS", cors_allow_all_origins=value)

    def test_cors_allow_all_origins_false_values_are_accepted(self):
        for value in (False, "False", "false", "0", "no", "off"):
            validate_production_settings(**self.valid_settings(cors_allow_all_origins=value))

    def test_response_body_logging_true_is_rejected(self):
        for value in (True, "True", "true", "1", "yes", "on"):
            self.assert_invalid("API_RESPONSE_LOGGING_INCLUDE_BODY", api_response_logging_include_body=value)

    def test_bool_coercion_is_explicit_for_common_env_values(self):
        self.assertTrue(coerce_bool("True"))
        self.assertTrue(coerce_bool("1"))
        self.assertTrue(coerce_bool("yes"))
        self.assertFalse(coerce_bool("False"))
        self.assertFalse(coerce_bool("0"))
        self.assertFalse(coerce_bool("no"))

    def test_production_security_headers_are_defined(self):
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SECURE_SSL_REDIRECT"], True)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SECURE_HSTS_SECONDS"], 31536000)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SECURE_HSTS_INCLUDE_SUBDOMAINS"], True)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SECURE_HSTS_PRELOAD"], True)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SECURE_CONTENT_TYPE_NOSNIFF"], True)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SECURE_REFERRER_POLICY"], "same-origin")
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["SESSION_COOKIE_SECURE"], True)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["CSRF_COOKIE_SECURE"], True)
        self.assertEqual(PRODUCTION_SECURITY_SETTINGS["X_FRAME_OPTIONS"], "DENY")
