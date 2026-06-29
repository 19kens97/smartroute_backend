import json
import logging
import time
import uuid
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.template.response import ContentNotRenderedError

logger = logging.getLogger("apps.http")

MASKED_VALUE_KEYS = {
    "email",
    "nif",
    "numero_immatriculation",
    "phone",
    "plate",
    "plate_number",
    "plaque",
    "telephone",
}

SENSITIVE_KEYS = {
    "access",
    "access_token",
    "authorization",
    "confirm_password",
    "cookie",
    "evidence_file",
    "file",
    "image",
    "new_password",
    "old_password",
    "password",
    "raw_response",
    "refresh",
    "refresh_token",
    "secret",
    "signature",
    "signature_payload",
    "token",
}


class APIResponseLoggingMiddleware:
    """Log API request/response lifecycle without exposing sensitive payloads."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.perf_counter()
        request_id = self.get_request_id(request)
        request.request_id = request_id

        if self.should_log(request):
            self.log_request_started(request, request_id)

        try:
            response = self.get_response(request)
        except Exception:
            self.log_request_failed(request, request_id, started_at)
            raise

        response["X-Request-ID"] = request_id
        if self.should_log(request):
            self.log_request_completed(request, response, request_id, started_at)
        return response

    def should_log(self, request):
        if not getattr(settings, "API_RESPONSE_LOGGING_ENABLED", True):
            return False
        return request.path.startswith(getattr(settings, "API_RESPONSE_LOGGING_PATH_PREFIX", "/api/"))

    def get_request_id(self, request):
        request_id = request.headers.get("X-Request-ID") or request.META.get("HTTP_X_REQUEST_ID")
        return request_id or str(uuid.uuid4())

    def get_user_id(self, request):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            return getattr(user, "pk", None)
        try:
            authenticated = JWTAuthentication().authenticate(request)
        except Exception:
            return None
        if not authenticated:
            return None
        auth_user, _token = authenticated
        return getattr(auth_user, "pk", None) if getattr(auth_user, "is_authenticated", False) else None

    def log_request_started(self, request, request_id):
        logger.info(
            "event=request_started request_id=%s method=%s path=%s user_id=%s client_ip=%s user_agent=%r",
            request_id,
            request.method,
            self.safe_path(request),
            self.get_user_id(request),
            self.client_ip(request),
            request.META.get("HTTP_USER_AGENT", ""),
        )

    def log_request_completed(self, request, response, request_id, started_at):
        duration_ms = (time.perf_counter() - started_at) * 1000
        response_size = self.response_size(response)
        response_preview = self.get_response_preview(response) if getattr(settings, "API_RESPONSE_LOGGING_INCLUDE_BODY", True) else "<disabled>"
        logger.info(
            "event=request_completed request_id=%s method=%s path=%s status=%s user_id=%s duration_ms=%.2f response_size=%s response=%s",
            request_id,
            request.method,
            self.safe_path(request),
            getattr(response, "status_code", None),
            self.get_user_id(request),
            duration_ms,
            response_size,
            response_preview,
        )

    def log_request_failed(self, request, request_id, started_at):
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.exception(
            "event=request_failed request_id=%s method=%s path=%s user_id=%s duration_ms=%.2f",
            request_id,
            request.method,
            self.safe_path(request),
            self.get_user_id(request),
            duration_ms,
        )

    def safe_path(self, request):
        full_path = request.get_full_path()
        parsed = urlsplit(full_path)
        if not parsed.query:
            return parsed.path
        safe_params = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            key_text = key.lower()
            if key_text in SENSITIVE_KEYS:
                safe_params.append((key, "<redacted>"))
            elif key_text in MASKED_VALUE_KEYS:
                safe_params.append((key, self.mask_value(key_text, value)))
            else:
                safe_params.append((key, value))
        return urlunsplit(("", "", parsed.path, urlencode(safe_params), ""))

    def client_ip(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def response_size(self, response):
        header_value = response.get("Content-Length")
        if header_value:
            return header_value
        if getattr(response, "streaming", False):
            return "streaming"
        try:
            return len(response.content)
        except (AttributeError, ContentNotRenderedError):
            return "unknown"

    def get_response_preview(self, response):
        if getattr(response, "streaming", False):
            return "<streaming response>"
        try:
            content = response.content
        except (AttributeError, ContentNotRenderedError):
            data = getattr(response, "data", None)
            if data is None:
                return "<unavailable>"
            return self.serialize_preview(data)
        if not content:
            return ""
        charset = getattr(response, "charset", None) or "utf-8"
        try:
            text = content.decode(charset, errors="replace")
        except AttributeError:
            text = str(content)
        content_type = response.get("Content-Type", "")
        if "json" not in content_type.lower():
            return self.truncate(text)
        try:
            return self.serialize_preview(json.loads(text))
        except json.JSONDecodeError:
            return self.truncate(text)

    def serialize_preview(self, data):
        sanitized = self.sanitize(data)
        return self.truncate(json.dumps(sanitized, ensure_ascii=False, default=str, separators=(",", ":")))

    def sanitize(self, value):
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if key_text in SENSITIVE_KEYS:
                    result[key] = "<redacted>"
                elif key_text in MASKED_VALUE_KEYS:
                    result[key] = self.mask_value(key_text, item)
                else:
                    result[key] = self.sanitize(item)
            return result
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, tuple):
            return [self.sanitize(item) for item in value]
        return value

    def mask_value(self, key, value):
        if value in (None, ""):
            return value
        text = str(value)
        if key == "email" and "@" in text:
            local, domain = text.split("@", 1)
            return f"{local[:1]}***@{domain}"
        if key in {"phone", "telephone"}:
            return f"{text[:4]}****{text[-4:]}" if len(text) > 8 else "<masked>"
        if key == "nif":
            return f"{text[:2]}***{text[-2:]}" if len(text) > 4 else "<masked>"
        if key in {"plate", "plate_number", "plaque", "numero_immatriculation"}:
            return f"{text[:2]}***{text[-2:]}" if len(text) > 4 else "<masked>"
        return "<masked>"

    def truncate(self, value):
        max_chars = getattr(settings, "API_RESPONSE_LOGGING_MAX_CHARS", 4000)
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}...<truncated>"


