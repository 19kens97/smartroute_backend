import hashlib
import logging
import io
import json

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, UnidentifiedImageError
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView
from apps.core.api import api_response
from .serializers import PasswordChangeSerializer, ProfileUpdateSerializer, UserSerializer

logger = logging.getLogger(__name__)

SIGNATURE_MAX_BYTES = 1024 * 1024
SIGNATURE_ALLOWED_FORMATS = {"PNG", "JPEG"}
SIGNATURE_MAX_WIDTH = 2000
SIGNATURE_MAX_HEIGHT = 1200


def _signature_status(user):
    return {
        "has_signature": bool(user.signature_file),
        "updated_at": user.signature_updated_at.isoformat() if user.signature_updated_at else None,
    }


def _is_blank_image(image):
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getbbox() is None:
        return True
    extrema = rgba.getextrema()
    return all(channel[0] == channel[1] for channel in extrema)


def _png_from_uploaded_signature(uploaded):
    if uploaded.size > SIGNATURE_MAX_BYTES:
        raise ValueError("FILE_TOO_LARGE")

    raw = uploaded.read()
    uploaded.seek(0)

    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except (UnidentifiedImageError, OSError):
        raise ValueError("INVALID_IMAGE") from None

    if image.format not in SIGNATURE_ALLOWED_FORMATS:
        raise ValueError("UNSUPPORTED_TYPE")
    if image.width > SIGNATURE_MAX_WIDTH or image.height > SIGNATURE_MAX_HEIGHT:
        raise ValueError("INVALID_DIMENSIONS")
    if _is_blank_image(image):
        raise ValueError("EMPTY_SIGNATURE")

    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def _png_from_strokes_payload(payload):
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("INVALID_PAYLOAD") from None

    if data.get("format") != "strokes-v1":
        raise ValueError("INVALID_PAYLOAD")

    width = int(data.get("canvasWidth") or 0)
    height = int(data.get("canvasHeight") or 0)
    strokes = data.get("strokes")

    if width <= 0 or height <= 0 or width > SIGNATURE_MAX_WIDTH or height > SIGNATURE_MAX_HEIGHT:
        raise ValueError("INVALID_DIMENSIONS")
    if not isinstance(strokes, list) or not any(isinstance(stroke, list) and len(stroke) > 1 for stroke in strokes):
        raise ValueError("EMPTY_SIGNATURE")

    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    for stroke in strokes:
        if not isinstance(stroke, list) or len(stroke) < 2:
            continue
        points = []
        for point in stroke:
            if not isinstance(point, dict):
                continue
            x = max(0, min(width - 1, int(round(float(point.get("x", 0))))))
            y = max(0, min(height - 1, int(round(float(point.get("y", 0))))))
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=(7, 20, 45, 255), width=4, joint="curve")

    if _is_blank_image(image):
        raise ValueError("EMPTY_SIGNATURE")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()
    if len(png) > SIGNATURE_MAX_BYTES:
        raise ValueError("FILE_TOO_LARGE")
    return png


def _signature_error_response(code):
    messages = {
        "MISSING_SIGNATURE": "Signature manquante.",
        "FILE_TOO_LARGE": "Le fichier de signature est trop volumineux.",
        "UNSUPPORTED_TYPE": "Format de signature non accepte.",
        "INVALID_IMAGE": "Image de signature invalide.",
        "INVALID_DIMENSIONS": "Dimensions de signature invalides.",
        "EMPTY_SIGNATURE": "Signature vide.",
        "INVALID_PAYLOAD": "Donnees de signature invalides.",
    }
    return api_response(False, messages.get(code, "Signature invalide."), {}, {"signature": code}, status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return api_response(True, "Profile loaded", UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(instance=request.user, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            logger.warning("event=profile_update_rejected request_id=%s user_id=%s fields=%s", getattr(request, "request_id", "-"), request.user.pk, sorted(request.data.keys()))
            return api_response(False, "Impossible de modifier le profil.", {}, serializer.errors, status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        try:
            from apps.core.services import log_action
            log_action(request.user, user, "UPDATE_PROFILE", {"fields": sorted(serializer.validated_data.keys())})
        except Exception:
            pass
        logger.info("event=profile_updated request_id=%s user_id=%s fields=%s", getattr(request, "request_id", "-"), request.user.pk, sorted(serializer.validated_data.keys()))
        return api_response(True, "Profil mis a jour.", UserSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            logger.warning("event=password_change_rejected request_id=%s user_id=%s error_fields=%s", getattr(request, "request_id", "-"), request.user.pk, sorted(serializer.errors.keys()))
            return api_response(False, "Impossible de modifier le mot de passe.", {}, serializer.errors, status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        try:
            from apps.core.services import log_action
            log_action(request.user, user, "CHANGE_PASSWORD")
        except Exception:
            pass
        logger.info("event=password_changed request_id=%s user_id=%s", getattr(request, "request_id", "-"), request.user.pk)
        return api_response(True, "Votre mot de passe a ete modifie avec succes.", {})


class ProfileSignatureView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        return api_response(True, "Signature status loaded", _signature_status(request.user))

    def put(self, request):
        uploaded = request.FILES.get("signature")
        payload = request.data.get("signature_payload")

        logger.info(
            "event=media_upload_started request_id=%s user_id=%s media_context=agent_signature has_file=%s has_payload=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            bool(uploaded),
            bool(payload),
        )

        if uploaded:
            try:
                png = _png_from_uploaded_signature(uploaded)
            except ValueError as exc:
                logger.warning("event=signature_upload_rejected request_id=%s user_id=%s reason=%s", getattr(request, "request_id", "-"), request.user.pk, str(exc))
                return _signature_error_response(str(exc))
        elif payload:
            try:
                png = _png_from_strokes_payload(payload)
            except ValueError as exc:
                logger.warning("event=signature_payload_rejected request_id=%s user_id=%s reason=%s", getattr(request, "request_id", "-"), request.user.pk, str(exc))
                return _signature_error_response(str(exc))
        else:
            return _signature_error_response("MISSING_SIGNATURE")

        user = request.user
        old_signature_name = user.signature_file.name if user.signature_file else ""
        signature_hash = hashlib.sha256(png).hexdigest()

        with transaction.atomic():
            user.signature_file.save("signature.png", ContentFile(png), save=False)
            user.signature_sha256 = signature_hash
            user.signature_updated_at = timezone.now()
            user.save(update_fields=["signature_file", "signature_sha256", "signature_updated_at"])

        if old_signature_name and old_signature_name != user.signature_file.name:
            user.signature_file.storage.delete(old_signature_name)

        logger.info("event=media_saved request_id=%s user_id=%s media_context=agent_signature sha256_prefix=%s", getattr(request, "request_id", "-"), request.user.pk, signature_hash[:12])
        logger.info("event=signature_saved request_id=%s user_id=%s sha256_prefix=%s", getattr(request, "request_id", "-"), request.user.pk, signature_hash[:12])
        return api_response(True, "Signature saved", _signature_status(user))

    def delete(self, request):
        user = request.user
        old_signature_name = user.signature_file.name if user.signature_file else ""
        user.signature_file = None
        user.signature_sha256 = ""
        user.signature_updated_at = None
        user.save(update_fields=["signature_file", "signature_sha256", "signature_updated_at"])
        if old_signature_name:
            user.signature_file.storage.delete(old_signature_name)
        logger.info("event=media_deleted request_id=%s user_id=%s media_context=agent_signature", getattr(request, "request_id", "-"), request.user.pk)
        logger.info("event=signature_deleted request_id=%s user_id=%s", getattr(request, "request_id", "-"), request.user.pk)
        return api_response(True, "Signature deleted", _signature_status(user))


class SmartTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        log_method = logger.info if response.status_code < 400 else logger.warning
        log_method("event=auth_login_completed request_id=%s status=%s", getattr(request, "request_id", "-"), response.status_code)
        return response

class SmartTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        log_method = logger.info if response.status_code < 400 else logger.warning
        log_method("event=auth_refresh_completed request_id=%s status=%s", getattr(request, "request_id", "-"), response.status_code)
        return response

class SmartTokenBlacklistView(TokenBlacklistView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        logger.info("event=auth_logout_completed request_id=%s user_id=%s status=%s", getattr(request, "request_id", "-"), getattr(request.user, "pk", None), response.status_code)
        return response



