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
