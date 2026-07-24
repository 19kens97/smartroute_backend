from .base import *

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "smartroute-test-cache",
        "KEY_PREFIX": "smartroute-test",
        "TIMEOUT": 300,
    }
}

API_RESPONSE_LOGGING_ENABLED = False
API_RESPONSE_LOGGING_INCLUDE_BODY = False
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
    "loggers": {
        "apps.http": {"handlers": ["null"], "level": "CRITICAL", "propagate": False},
        "django.request": {"handlers": ["null"], "level": "CRITICAL", "propagate": False},
    },
}

MIDDLEWARE = [
    item for item in MIDDLEWARE
    if item != "whitenoise.middleware.WhiteNoiseMiddleware"
]
