from django.core.exceptions import ImproperlyConfigured


UNSAFE_SECRET_KEYS = {
    "",
    "unsafe-dev-key",
    "change-me",
    "changeme",
    "change-me-with-at-least-32-characters",
    "your-secret-key",
    "replace-me",
    "replace-with-a-real-long-random-secret",
    "secret",
    "placeholder",
    "example-secret-key",
}

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
PRODUCTION_DATABASE_ENGINE = "django.db.backends.postgresql"

PRODUCTION_SECURITY_SETTINGS = {
    "SECURE_SSL_REDIRECT": True,
    "SECURE_HSTS_SECONDS": 31536000,
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
    "SECURE_HSTS_PRELOAD": True,
    "SECURE_CONTENT_TYPE_NOSNIFF": True,
    "SECURE_REFERRER_POLICY": "same-origin",
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "X_FRAME_OPTIONS": "DENY",
}


def coerce_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f"Invalid boolean value for production settings: {value!r}. "
        "Use one of true/false, 1/0, yes/no, on/off."
    )


def normalize_hosts(value):
    if isinstance(value, str):
        raw_hosts = value.split(",")
    else:
        raw_hosts = value or []
    return [str(host).strip() for host in raw_hosts if str(host).strip()]


def _is_unsafe_secret_key(secret_key):
    value = str(secret_key or "").strip()
    normalized = value.lower()
    return (
        not value
        or normalized in UNSAFE_SECRET_KEYS
        or normalized.startswith("django-insecure-")
        or normalized.startswith("replace-")
    )


def validate_production_settings(
    *,
    secret_key,
    debug,
    allowed_hosts,
    cors_allow_all_origins,
    api_response_logging_include_body,
    database_engine,
    antivirus_scanner="disabled",
    antivirus_required=False,
    antivirus_clamav_host="",
    antivirus_clamav_port=0,
    antivirus_timeout_seconds=0,
):
    errors = []

    if _is_unsafe_secret_key(secret_key):
        errors.append("SECRET_KEY must be set to a strong non-placeholder value in production.")

    if coerce_bool(debug):
        errors.append("DEBUG must be False in production.")

    hosts = normalize_hosts(allowed_hosts)
    if not hosts:
        errors.append("ALLOWED_HOSTS must contain explicit production hostnames.")
    elif "*" in hosts:
        errors.append("ALLOWED_HOSTS cannot contain '*' in production.")

    if coerce_bool(cors_allow_all_origins):
        errors.append("CORS_ALLOW_ALL_ORIGINS must be False in production.")

    if coerce_bool(api_response_logging_include_body):
        errors.append("API_RESPONSE_LOGGING_INCLUDE_BODY must be False in production.")

    if database_engine != PRODUCTION_DATABASE_ENGINE:
        errors.append("DATABASES.default.ENGINE must be PostgreSQL in production.")

    scanner = str(antivirus_scanner or "").strip().lower()
    if not coerce_bool(antivirus_required):
        errors.append("ANTIVIRUS_REQUIRED must be True in production.")
    if scanner != "clamav_tcp":
        errors.append("ANTIVIRUS_SCANNER must be 'clamav_tcp' in production.")
    if not str(antivirus_clamav_host or "").strip():
        errors.append("ANTIVIRUS_CLAMAV_HOST must point to a private clamd host in production.")
    try:
        port = int(antivirus_clamav_port)
    except (TypeError, ValueError):
        port = 0
    if not (1 <= port <= 65535):
        errors.append("ANTIVIRUS_CLAMAV_PORT must be a valid TCP port in production.")
    try:
        timeout = float(antivirus_timeout_seconds)
    except (TypeError, ValueError):
        timeout = 0
    if timeout <= 0:
        errors.append("ANTIVIRUS_TIMEOUT_SECONDS must be greater than zero in production.")

    if errors:
        raise ImproperlyConfigured("Invalid production settings: " + " ".join(errors))
