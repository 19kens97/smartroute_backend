import hashlib
import logging
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import serializers

logger = logging.getLogger(__name__)

MEDIA_TYPE_IMAGE = "image"
MEDIA_TYPE_VIDEO = "video"
MEDIA_TYPE_AUDIO = "audio"
MEDIA_TYPE_DOCUMENT = "document"
MEDIA_TYPE_SIGNATURE = "signature"

DANGEROUS_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".html",
    ".htm",
    ".js",
    ".php",
    ".ps1",
    ".sh",
    ".svg",
}


def _extension(filename):
    return Path(filename or "").suffix.lower()


def _has_dangerous_extension(filename):
    return any(part.lower() in DANGEROUS_EXTENSIONS for part in Path(filename or "").suffixes)


def _uuid_filename(filename, fallback_extension=".bin"):
    extension = _extension(filename) or fallback_extension
    return f"{uuid.uuid4()}{extension}"


def ticket_proof_upload_path(instance, filename):
    ticket = getattr(instance, "ticket", None)
    ticket_ref = getattr(ticket, "ticket_number", None) or getattr(instance, "ticket_id", None) or "pending"
    subdir = {
        "PHOTO": "photos",
        "VIDEO": "videos",
        "AUDIO": "audio",
    }.get(getattr(instance, "evidence_type", ""), "files")
    return f"tickets/{ticket_ref}/{subdir}/{_uuid_filename(filename)}"


def alert_evidence_upload_path(instance, filename):
    subdir = {
        "AUDIO": "audio",
        "VIDEO": "videos",
        "PHOTO": "photos",
    }.get(getattr(instance, "evidence_type", ""), "files")
    return f"alerts/{getattr(instance, 'alert_id', None) or 'pending'}/{subdir}/{_uuid_filename(filename)}"


def user_signature_upload_path(instance, filename):
    return f"signatures/agents/{getattr(instance, 'pk', None) or 'pending'}/{uuid.uuid4()}.png"


def document_upload_path(instance, filename):
    vehicle_id = getattr(instance, "vehicle_id", None) or "pending"
    return f"documents/vehicles/{vehicle_id}/{_uuid_filename(filename)}"


def scan_upload_path(_instance, filename):
    return f"scans/{_uuid_filename(filename, '.jpg')}"


def profile_upload_path(instance, filename):
    return f"profiles/{getattr(instance, 'pk', None) or 'pending'}/{_uuid_filename(filename)}"


def compute_sha256(file_obj):
    hasher = hashlib.sha256()
    current_position = None
    try:
        current_position = file_obj.tell()
    except (AttributeError, OSError):
        current_position = None

    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    for chunk in file_obj.chunks() if hasattr(file_obj, "chunks") else iter(lambda: file_obj.read(8192), b""):
        if not chunk:
            break
        hasher.update(chunk)
    if hasattr(file_obj, "seek"):
        file_obj.seek(current_position or 0)
    return hasher.hexdigest()


def validate_uploaded_media(
    file_obj,
    *,
    media_type,
    allowed_mime_types,
    allowed_extensions,
    max_size_mb,
    duration_seconds=None,
    max_duration_seconds=None,
    field_name="file",
):
    if file_obj is None:
        raise serializers.ValidationError({field_name: "Le fichier est requis."})
    if getattr(file_obj, "size", 0) <= 0:
        raise serializers.ValidationError({field_name: "Le fichier est vide."})

    filename = getattr(file_obj, "name", "") or ""
    mime_type = (getattr(file_obj, "content_type", "") or "").lower()
    extension = _extension(filename)
    allowed_extensions = {ext.lower() for ext in allowed_extensions}
    allowed_mime_types = {mime.lower() for mime in allowed_mime_types}

    if _has_dangerous_extension(filename):
        logger.warning("event=media_validation_failed reason=dangerous_extension media_type=%s filename=%s", media_type, filename)
        raise serializers.ValidationError({field_name: "Extension de fichier non autorisee."})
    if extension not in allowed_extensions:
        logger.warning("event=media_validation_failed reason=extension media_type=%s extension=%s", media_type, extension)
        raise serializers.ValidationError({field_name: "Extension de fichier non autorisee."})
    if mime_type not in allowed_mime_types:
        logger.warning("event=media_validation_failed reason=mime media_type=%s mime_type=%s", media_type, mime_type)
        raise serializers.ValidationError({field_name: "Type MIME de fichier non autorise."})

    max_size = max_size_mb * 1024 * 1024
    if file_obj.size > max_size:
        logger.warning("event=media_validation_failed reason=size media_type=%s size=%s max_size=%s", media_type, file_obj.size, max_size)
        raise serializers.ValidationError({field_name: "Le fichier est trop volumineux."})
    if max_duration_seconds is not None and duration_seconds is not None and duration_seconds > max_duration_seconds:
        logger.warning("event=media_validation_failed reason=duration media_type=%s duration=%s max_duration=%s", media_type, duration_seconds, max_duration_seconds)
        raise serializers.ValidationError({"duration_seconds": "La duree du fichier depasse la limite autorisee."})

    return {
        "mime_type": mime_type,
        "size_bytes": getattr(file_obj, "size", None),
        "checksum_sha256": compute_sha256(file_obj),
    }


def get_image_limits():
    return {
        "allowed_mime_types": getattr(settings, "ALLOWED_IMAGE_MIME_TYPES", ["image/jpeg", "image/png"]),
        "allowed_extensions": getattr(settings, "ALLOWED_IMAGE_EXTENSIONS", [".jpg", ".jpeg", ".png"]),
        "max_size_mb": min(getattr(settings, "MAX_IMAGE_SIZE_MB", 5), getattr(settings, "SECURE_UPLOAD_MAX_MB", 5)),
    }


def get_video_limits():
    return {
        "allowed_mime_types": getattr(settings, "ALERT_EVIDENCE_ALLOWED_VIDEO_MIME_TYPES", ["video/mp4", "video/quicktime"]),
        "allowed_extensions": getattr(settings, "ALERT_EVIDENCE_ALLOWED_VIDEO_EXTENSIONS", [".mp4", ".mov"]),
        "max_size_mb": min(getattr(settings, "MAX_VIDEO_SIZE_MB", 35), getattr(settings, "ALERT_EVIDENCE_VIDEO_MAX_MB", 35)),
        "max_duration_seconds": getattr(settings, "ALERT_EVIDENCE_VIDEO_MAX_DURATION_SECONDS", 60),
    }


def get_audio_limits():
    return {
        "allowed_mime_types": getattr(settings, "ALERT_EVIDENCE_ALLOWED_AUDIO_MIME_TYPES", ["audio/mp4", "audio/mpeg", "audio/wav", "audio/aac"]),
        "allowed_extensions": getattr(settings, "ALERT_EVIDENCE_ALLOWED_AUDIO_EXTENSIONS", [".m4a", ".mp4", ".aac", ".mp3", ".wav"]),
        "max_size_mb": min(getattr(settings, "MAX_AUDIO_SIZE_MB", 10), getattr(settings, "ALERT_EVIDENCE_AUDIO_MAX_MB", 10)),
        "max_duration_seconds": getattr(settings, "ALERT_EVIDENCE_AUDIO_MAX_DURATION_SECONDS", 180),
    }
