from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from .cache import (
    DEFAULT_STATISTICS_VERSION,
    STATISTICS_VERSION_KEY,
    dashboard_cache_key,
    get_statistics_version,
    invalidate_statistics_cache,
    safe_cache_get,
    safe_cache_set,
    statistics_cache_key,
)


CACHE_SETTINGS = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.locmem."
            "LocMemCache"
        ),
        "LOCATION": "test-core-cache",
    }
}


@override_settings(CACHES=CACHE_SETTINGS)
class CacheUtilityTests(SimpleTestCase):
    def setUp(self):
        caches["default"].clear()

    def test_statistics_key_is_deterministic(self):
        key = statistics_cache_key(
            "tickets",
            status="OPEN",
            days=7,
        )
        self.assertIn("days=7", key)
        self.assertIn("status=OPEN", key)
        self.assertIn(":v1", key)

    def test_dashboard_key_uses_global_version(self):
        self.assertEqual(
            dashboard_cache_key(7),
            "smartroute:statistics:dashboard:days=7:v1",
        )

    def test_safe_get_set(self):
        key = dashboard_cache_key(7)
        self.assertIsNone(safe_cache_get(key))
        self.assertTrue(
            safe_cache_set(key, {"ok": True}, timeout=30)
        )
        self.assertEqual(
            safe_cache_get(key),
            {"ok": True},
        )

    def test_invalidation_increments_version(self):
        before = get_statistics_version()
        after = invalidate_statistics_cache()
        self.assertEqual(after, before + 1)
        self.assertEqual(
            caches["default"].get(STATISTICS_VERSION_KEY),
            after,
        )

    def test_backend_errors_are_tolerated(self):
        class BrokenCache:
            def get(self, key):
                raise RuntimeError("cache down")

            def set(self, key, value, timeout=None):
                raise RuntimeError("cache down")

        self.assertIsNone(
            safe_cache_get("key", cache_backend=BrokenCache())
        )
        self.assertFalse(
            safe_cache_set(
                "key",
                {"ok": True},
                cache_backend=BrokenCache(),
            )
        )
