from .base import *
from decouple import config
from .production_checks import PRODUCTION_SECURITY_SETTINGS, validate_production_settings

DEBUG = config("DEBUG", cast=bool, default=False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
globals().update(PRODUCTION_SECURITY_SETTINGS)
API_RESPONSE_LOGGING_INCLUDE_BODY = config("API_RESPONSE_LOGGING_INCLUDE_BODY", cast=bool, default=False)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="smartroute"),
        "USER": config("POSTGRES_USER", default="smartroute"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="smartroute"),
        "HOST": config("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }
}

validate_production_settings(
    secret_key=SECRET_KEY,
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    cors_allow_all_origins=CORS_ALLOW_ALL_ORIGINS,
    api_response_logging_include_body=API_RESPONSE_LOGGING_INCLUDE_BODY,
)
