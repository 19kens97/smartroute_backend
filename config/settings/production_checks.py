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
    return bool(value)


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

    if errors:
        raise ImproperlyConfigured("Invalid production settings: " + " ".join(errors))
