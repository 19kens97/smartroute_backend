from .base import *
from decouple import config
from .production_checks import PRODUCTION_SECURITY_SETTINGS, coerce_bool, validate_production_settings

DEBUG = coerce_bool(config("DEBUG", default=False))
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
    database_engine=DATABASES["default"]["ENGINE"],
    antivirus_scanner=ANTIVIRUS_SCANNER,
    antivirus_required=ANTIVIRUS_REQUIRED,
    antivirus_clamav_host=ANTIVIRUS_CLAMAV_HOST,
    antivirus_clamav_port=ANTIVIRUS_CLAMAV_PORT,
    antivirus_timeout_seconds=ANTIVIRUS_TIMEOUT_SECONDS,
)


