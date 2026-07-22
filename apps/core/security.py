import re
import uuid
from collections.abc import Mapping


MASKED_VALUE_KEYS = {
    "address",
    "birth_date",
    "driver_dossier_snapshot",
    "driver_name_snapshot",
    "driver_nif_snapshot",
    "email",
    "full_name",
    "latitude",
    "location_label",
    "longitude",
    "nif",
    "numero_immatriculation",
    "phone",
    "plate",
    "plate_number",
    "plate_number_snapshot",
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

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def normalize_request_id(value):
    text = str(value or "").strip()
    if text and REQUEST_ID_PATTERN.fullmatch(text):
        return text
    return str(uuid.uuid4())


def mask_value(key, value):
    if value in (None, ""):
        return value

    text = str(value)
    key = str(key).lower()

    if key == "email" and "@" in text:
        local, domain = text.split("@", 1)
        return f"{local[:1]}***@{domain}"

    if key in {"phone", "telephone"}:
        return (
            f"{text[:4]}****{text[-4:]}"
            if len(text) > 8
            else "<masked>"
        )

    if key in {"nif", "driver_nif_snapshot"}:
        return (
            f"{text[:2]}***{text[-2:]}"
            if len(text) > 4
            else "<masked>"
        )

    if key in {
        "plate",
        "plate_number",
        "plate_number_snapshot",
        "plaque",
        "numero_immatriculation",
    }:
        return (
            f"{text[:2]}***{text[-2:]}"
            if len(text) > 4
            else "<masked>"
        )

    return "<masked>"


def sanitize_mapping(value):
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_KEYS:
                result[key] = "<redacted>"
            elif key_text in MASKED_VALUE_KEYS:
                result[key] = mask_value(key_text, item)
            else:
                result[key] = sanitize_mapping(item)
        return result

    if isinstance(value, (list, tuple)):
        return [sanitize_mapping(item) for item in value]

    return value


def get_client_ip(request):
    trust_proxy = bool(
        getattr(
            request,
            "_smartroute_trust_forwarded_for",
            False,
        )
    )
    if trust_proxy:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()

    return request.META.get("REMOTE_ADDR") or None
