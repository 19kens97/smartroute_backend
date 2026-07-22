import json
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.template.response import ContentNotRenderedError

from .security import (
    MASKED_VALUE_KEYS,
    SENSITIVE_KEYS,
    get_client_ip,
    mask_value,
    normalize_request_id,
    sanitize_mapping,
)


logger = logging.getLogger("apps.http")


class APIResponseLoggingMiddleware:
    """Journalise le cycle HTTP sans exposer les données sensibles."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.perf_counter()
        request_id = self.get_request_id(request)
        request.request_id = request_id
        request._smartroute_trust_forwarded_for = bool(
            getattr(
                settings,
                "API_TRUST_X_FORWARDED_FOR",
                False,
            )
        )

        if self.should_log(request):
            self.log_request_started(request, request_id)

        try:
            response = self.get_response(request)
        except Exception:
            self.log_request_failed(
                request,
                request_id,
                started_at,
            )
            raise

        response["X-Request-ID"] = request_id

        if self.should_log(request):
            self.log_request_completed(
                request,
                response,
                request_id,
                started_at,
            )

        return response

    def should_log(self, request):
        if not getattr(
            settings,
            "API_RESPONSE_LOGGING_ENABLED",
            True,
        ):
            return False

        prefix = getattr(
            settings,
            "API_RESPONSE_LOGGING_PATH_PREFIX",
            "/api/",
        )
        return request.path.startswith(prefix)

    def get_request_id(self, request):
        supplied = (
            request.headers.get("X-Request-ID")
            or request.META.get("HTTP_X_REQUEST_ID")
        )
        return normalize_request_id(supplied)

    def get_user_id(self, request):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            return getattr(user, "pk", None)
        return None

    def log_request_started(self, request, request_id):
        logger.info(
            "event=request_started request_id=%s "
            "method=%s path=%s user_id=%s client_ip=%s "
            "user_agent=%r",
            request_id,
            request.method,
            self.safe_path(request),
            self.get_user_id(request),
            get_client_ip(request),
            request.META.get("HTTP_USER_AGENT", ""),
        )

    def log_request_completed(
        self,
        request,
        response,
        request_id,
        started_at,
    ):
        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000
        response_size = self.response_size(response)

        include_body = getattr(
            settings,
            "API_RESPONSE_LOGGING_INCLUDE_BODY",
            False,
        )
        response_preview = (
            self.get_response_preview(response)
            if include_body
            else "<disabled>"
        )

        logger.info(
            "event=request_completed request_id=%s "
            "method=%s path=%s status=%s user_id=%s "
            "duration_ms=%.2f response_size=%s response=%s",
            request_id,
            request.method,
            self.safe_path(request),
            getattr(response, "status_code", None),
            self.get_user_id(request),
            duration_ms,
            response_size,
            response_preview,
        )

    def log_request_failed(
        self,
        request,
        request_id,
        started_at,
    ):
        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000
        logger.exception(
            "event=request_failed request_id=%s "
            "method=%s path=%s user_id=%s duration_ms=%.2f",
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
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        ):
            key_text = key.lower()
            if key_text in SENSITIVE_KEYS:
                safe_params.append((key, "<redacted>"))
            elif key_text in MASKED_VALUE_KEYS:
                safe_params.append(
                    (key, mask_value(key_text, value))
                )
            else:
                safe_params.append((key, value))

        return urlunsplit(
            (
                "",
                "",
                parsed.path,
                urlencode(safe_params),
                "",
            )
        )

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
            text = content.decode(
                charset,
                errors="replace",
            )
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
        sanitized = sanitize_mapping(data)
        return self.truncate(
            json.dumps(
                sanitized,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )

    def truncate(self, value):
        max_chars = getattr(
            settings,
            "API_RESPONSE_LOGGING_MAX_CHARS",
            2000,
        )
        text = str(value)

        if len(text) <= max_chars:
            return text

        return f"{text[:max_chars]}...<truncated>"
