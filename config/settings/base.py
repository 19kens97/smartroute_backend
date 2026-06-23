from datetime import timedelta
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = config("SECRET_KEY", default="unsafe-dev-key")
DEBUG_RAW = str(config("DEBUG", default="False")).strip().lower()
DEBUG = DEBUG_RAW in {"1", "true", "yes", "on", "dev", "development"}
ALLOWED_HOSTS = [h.strip() for h in config("ALLOWED_HOSTS", default="127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "apps.core",
    "apps.accounts",
    "apps.owners",
    "apps.vehicles",
    "apps.documents",
    "apps.drivers",
    "apps.insurance",
    "apps.scans",
    "apps.infractions",
    "apps.tickets",
    "apps.alerts",
    "apps.dashboard",
    "apps.reports",
    "apps.sync",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "accounts.User"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "America/Port-au-Prince"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_SIGNATURE_ROOT = BASE_DIR / "private" / "agent-signatures"
PRIVATE_ALERT_EVIDENCE_ROOT = BASE_DIR / "private" / "alert-evidence"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CORS_ALLOWED_ORIGINS = [o.strip() for o in config("CORS_ALLOWED_ORIGINS", default="").split(",") if o.strip()]
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", cast=bool, default=False)

GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
GEMINI_MODEL = config("GEMINI_MODEL", default="gemini-2.5-flash")
GEMINI_FALLBACK_MODELS = [m.strip() for m in config("GEMINI_FALLBACK_MODELS", default="").split(",") if m.strip()]
GEMINI_LOG_RESPONSE = config("GEMINI_LOG_RESPONSE", cast=bool, default=False)
GEMINI_LOG_RAW_RESPONSE = config("GEMINI_LOG_RAW_RESPONSE", cast=bool, default=False)
ENABLE_RECOGNIZE_ENDPOINT = config("ENABLE_RECOGNIZE_ENDPOINT", cast=bool, default=False)

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("apps.core.renderers.StandardizedJSONRenderer",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.UserRateThrottle", "rest_framework.throttling.AnonRateThrottle"),
    "DEFAULT_THROTTLE_RATES": {"user": "300/min", "anon": "50/min"},
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SmartRoute API",
    "DESCRIPTION": "Backend Django/DRF SmartRoute",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

USE_REDIS = config("USE_REDIS", cast=bool, default=False)
USE_CELERY = config("USE_CELERY", cast=bool, default=False)
REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/1")
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/2")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/3")
if USE_CELERY:
    INSTALLED_APPS += ["django_celery_beat", "django_celery_results"]

SECURE_UPLOAD_MAX_MB = 5
ALLOWED_UPLOAD_EXTENSIONS = [".jpg", ".jpeg", ".png", ".pdf"]
ALERT_EVIDENCE_AUDIO_MAX_MB = 10
ALERT_EVIDENCE_VIDEO_MAX_MB = 35
ALERT_EVIDENCE_AUDIO_MAX_DURATION_SECONDS = 180
ALERT_EVIDENCE_VIDEO_MAX_DURATION_SECONDS = 60
ALERT_EVIDENCE_ALLOWED_AUDIO_MIME_TYPES = ["audio/m4a", "audio/mp4", "audio/aac", "audio/mpeg", "audio/x-m4a"]
ALERT_EVIDENCE_ALLOWED_VIDEO_MIME_TYPES = ["video/mp4", "video/quicktime"]
ALERT_EVIDENCE_ALLOWED_AUDIO_EXTENSIONS = [".m4a", ".mp4", ".aac", ".mp3"]
ALERT_EVIDENCE_ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".mov"]
