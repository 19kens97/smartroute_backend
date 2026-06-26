from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from apps.core.cache import DASHBOARD_CACHE_VERSION, dashboard_cache_key, get_cache, invalidate_statistics_cache, safe_cache_get, safe_cache_set


class CacheUtilityTests(SimpleTestCase):
    def test_dashboard_cache_key_is_deterministic_and_non_sensitive(self):
        key = dashboard_cache_key(days=7)
        self.assertEqual(key, "smartroute:statistics:dashboard:days:7:v1")
        self.assertNotIn("@", key)
        self.assertNotIn("token", key.lower())
        self.assertIn(f"v{DASHBOARD_CACHE_VERSION}", key)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-statistics-cache"}})
    def test_safe_cache_get_set_and_invalidate_statistics_cache(self):
        cache = caches["default"]
        cache.clear()
        key = dashboard_cache_key(7)

        self.assertIsNone(safe_cache_get(key))
        self.assertTrue(safe_cache_set(key, {"ok": True}, timeout=30))
        self.assertEqual(safe_cache_get(key), {"ok": True})

        invalidate_statistics_cache()
        self.assertIsNone(cache.get(key))

    def test_safe_cache_get_tolerates_cache_backend_error(self):
        class BrokenCache:
            def get(self, key):
                raise RuntimeError("redis down")

            def set(self, key, value, timeout=None):
                raise RuntimeError("redis down")

        self.assertIsNone(safe_cache_get("smartroute:statistics:dashboard:days:7:v1", cache_backend=BrokenCache()))
        self.assertFalse(safe_cache_set("smartroute:statistics:dashboard:days:7:v1", {"ok": True}, cache_backend=BrokenCache()))

    def test_get_cache_returns_default_cache(self):
        self.assertIs(get_cache(), caches["default"])
