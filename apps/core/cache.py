import logging

from django.core.cache import caches


logger = logging.getLogger(__name__)

STATISTICS_VERSION_KEY = "smartroute:statistics:version"
STATISTICS_CACHE_TTL_SECONDS = 120
DASHBOARD_CACHE_TTL_SECONDS = STATISTICS_CACHE_TTL_SECONDS
DEFAULT_STATISTICS_VERSION = 1


def get_cache():
    return caches["default"]


def get_statistics_version(cache_backend=None):
    try:
        backend = cache_backend or get_cache()
        version = backend.get(STATISTICS_VERSION_KEY)
        if version is None:
            backend.add(
                STATISTICS_VERSION_KEY,
                DEFAULT_STATISTICS_VERSION,
                timeout=None,
            )
            version = backend.get(STATISTICS_VERSION_KEY)
        return int(version or DEFAULT_STATISTICS_VERSION)
    except Exception:
        logger.warning(
            "event=statistics_cache_version_get_failed",
            exc_info=True,
        )
        return DEFAULT_STATISTICS_VERSION


def statistics_cache_key(namespace, *, version=None, **filters):
    normalized = ":".join(
        f"{key}={filters[key]}"
        for key in sorted(filters)
    )
    current_version = (
        version
        if version is not None
        else get_statistics_version()
    )
    suffix = f":{normalized}" if normalized else ""
    return (
        f"smartroute:statistics:{namespace}"
        f"{suffix}:v{current_version}"
    )


def dashboard_cache_key(days):
    return statistics_cache_key("dashboard", days=int(days))


def safe_cache_get(key, cache_backend=None):
    try:
        backend = cache_backend or get_cache()
        return backend.get(key)
    except Exception:
        logger.warning(
            "event=cache_get_failed key=%s",
            key,
            exc_info=True,
        )
        return None


def safe_cache_set(
    key,
    value,
    timeout=STATISTICS_CACHE_TTL_SECONDS,
    cache_backend=None,
):
    try:
        backend = cache_backend or get_cache()
        backend.set(key, value, timeout=timeout)
        return True
    except Exception:
        logger.warning(
            "event=cache_set_failed key=%s",
            key,
            exc_info=True,
        )
        return False


def invalidate_statistics_cache():
    try:
        backend = get_cache()
        try:
            new_version = backend.incr(STATISTICS_VERSION_KEY)
        except ValueError:
            backend.set(
                STATISTICS_VERSION_KEY,
                DEFAULT_STATISTICS_VERSION + 1,
                timeout=None,
            )
            new_version = DEFAULT_STATISTICS_VERSION + 1

        logger.info(
            "event=statistics_cache_invalidated version=%s",
            new_version,
        )
        return new_version
    except Exception:
        logger.warning(
            "event=statistics_cache_invalidation_failed",
            exc_info=True,
        )
        return None
