import logging

from django.core.cache import caches

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_VERSION = 1
DASHBOARD_CACHE_TTL_SECONDS = 120


def get_cache():
    return caches["default"]


def dashboard_cache_key(days: int) -> str:
    return f"smartroute:statistics:dashboard:days:{days}:v{DASHBOARD_CACHE_VERSION}"


def statistics_cache_keys():
    return [dashboard_cache_key(days) for days in range(1, 32)]


def safe_cache_get(key: str, cache_backend=None):
    backend = cache_backend or get_cache()
    try:
        return backend.get(key)
    except Exception:
        logger.warning("event=cache_get_failed key=%s", key, exc_info=True)
        return None


def safe_cache_set(key: str, value, timeout: int = DASHBOARD_CACHE_TTL_SECONDS, cache_backend=None) -> bool:
    backend = cache_backend or get_cache()
    try:
        backend.set(key, value, timeout=timeout)
        return True
    except Exception:
        logger.warning("event=cache_set_failed key=%s", key, exc_info=True)
        return False


def invalidate_statistics_cache():
    backend = get_cache()
    keys = statistics_cache_keys()
    try:
        backend.delete_many(keys)
        logger.info("event=statistics_cache_invalidated count=%s", len(keys))
    except Exception:
        logger.warning("event=statistics_cache_invalidation_failed", exc_info=True)
