from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from apps.infractions.models import Infraction
from .models import Ticket, TicketInfraction, TicketProof


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac"}
PHOTO_MIME_PREFIX = "image/"
VIDEO_MIME_TYPES = set(getattr(settings, "ALERT_EVIDENCE_ALLOWED_VIDEO_MIME_TYPES", ("video/mp4", "video/quicktime")))
AUDIO_MIME_TYPES = set(getattr(settings, "ALERT_EVIDENCE_ALLOWED_AUDIO_MIME_TYPES", ("audio/mp4", "audio/mpeg", "audio/wav", "audio/aac")))


class TicketProofSerializer(serializers.ModelSerializer):
    size_bytes = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = TicketProof
        fields = ("id", "file", "url", "evidence_type", "mime_type", "duration_seconds", "caption", "size_bytes", "created_at")
        read_only_fields = ("mime_type", "size_bytes", "url", "created_at")

    def get_size_bytes(self, obj):
        try:
            return obj.file.size
        except (OSError, ValueError):
            return None

    def get_url(self, obj):
        if not obj.file:
            return ""
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        file_obj = attrs.get("file")
        evidence_type = attrs.get("evidence_type") or TicketProof.EVIDENCE_PHOTO
        duration_seconds = attrs.get("duration_seconds")
        if not file_obj:
            raise serializers.ValidationError({"file": "Proof file is required."})

        ext = Path(file_obj.name).suffix.lower()
        mime_type = getattr(file_obj, "content_type", "") or ""
        max_photo_size = settings.SECURE_UPLOAD_MAX_MB * 1024 * 1024
        max_video_size = getattr(settings, "ALERT_EVIDENCE_VIDEO_MAX_MB", 35) * 1024 * 1024
        max_audio_size = getattr(settings, "ALERT_EVIDENCE_AUDIO_MAX_MB", 10) * 1024 * 1024

        if evidence_type == TicketProof.EVIDENCE_PHOTO:
            if ext not in PHOTO_EXTENSIONS or not mime_type.startswith(PHOTO_MIME_PREFIX):
                raise serializers.ValidationError({"file": "Unsupported photo format."})
            if file_obj.size > max_photo_size:
                raise serializers.ValidationError({"file": "Photo file too large."})
        elif evidence_type == TicketProof.EVIDENCE_VIDEO:
            if ext not in VIDEO_EXTENSIONS or mime_type not in VIDEO_MIME_TYPES:
                raise serializers.ValidationError({"file": "Unsupported video format."})
            if file_obj.size > max_video_size:
                raise serializers.ValidationError({"file": "Video file too large."})
            max_duration = getattr(settings, "ALERT_EVIDENCE_VIDEO_MAX_DURATION_SECONDS", 60)
            if duration_seconds is not None and duration_seconds > max_duration:
                raise serializers.ValidationError({"duration_seconds": "Video is too long."})
        elif evidence_type == TicketProof.EVIDENCE_AUDIO:
            if ext not in AUDIO_EXTENSIONS or mime_type not in AUDIO_MIME_TYPES:
                raise serializers.ValidationError({"file": "Unsupported audio format."})
            if file_obj.size > max_audio_size:
                raise serializers.ValidationError({"file": "Audio file too large."})
            max_duration = getattr(settings, "ALERT_EVIDENCE_AUDIO_MAX_DURATION_SECONDS", 180)
            if duration_seconds is not None and duration_seconds > max_duration:
                raise serializers.ValidationError({"duration_seconds": "Audio is too long."})
        else:
            raise serializers.ValidationError({"evidence_type": "Unsupported evidence type."})

        attrs["mime_type"] = mime_type
        return attrs


class TicketInfractionReadSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="infraction_id")
    code = serializers.CharField(source="infraction.code")
    label = serializers.CharField(source="infraction.label")
    article = serializers.SerializerMethodField()
    amount = serializers.DecimalField(source="amount_snapshot", max_digits=10, decimal_places=2)

    class Meta:
        model = TicketInfraction
        fields = ("id", "code", "label", "article", "amount")

    def get_article(self, obj):
        return ""


class TicketAgentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField(allow_blank=True)
    badge_number = serializers.CharField(allow_blank=True)
    role = serializers.CharField(allow_blank=True)
    has_signature = serializers.BooleanField()
    signature_updated_at = serializers.DateTimeField(allow_null=True)


class TicketSerializer(serializers.ModelSerializer):
    infraction_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=True)
    proofs = TicketProofSerializer(many=True, read_only=True)
    infractions = TicketInfractionReadSerializer(source="ticket_infractions", many=True, read_only=True)
    agent_detail = serializers.SerializerMethodField()
    agent_signature_url = serializers.SerializerMethodField()
    sync_status = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = (
            "id",
            "client_uuid",
            "agent",
            "agent_detail",
            "agent_signature_url",
            "driver_license",
            "plate_number_snapshot",
            "vehicle",
            "status",
            "sync_status",
            "note",
            "barcode_value",
            "barcode_image",
            "infraction_ids",
            "infractions",
            "proofs",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("agent", "agent_detail", "agent_signature_url", "barcode_value", "barcode_image", "infractions", "proofs", "sync_status")

    def get_agent_detail(self, obj):
        agent = obj.agent
        full_name = getattr(agent, "full_name", "") or agent.get_full_name() or agent.username
        return {
            "id": agent.pk,
            "full_name": full_name,
            "badge_number": getattr(agent, "badge_number", "") or "",
            "role": getattr(agent, "role", "") or "",
            "has_signature": bool(getattr(agent, "signature_file", None)),
            "signature_updated_at": getattr(agent, "signature_updated_at", None),
        }

    def get_agent_signature_url(self, obj):
        if not getattr(obj.agent, "signature_file", None):
            return None
        request = self.context.get("request")
        path = f"/api/tickets/{obj.pk}/agent-signature/"
        return request.build_absolute_uri(path) if request else path

    def get_sync_status(self, obj):
        return "pending" if obj.status == "PENDING_SYNC" else "synced"

    def validate_infraction_ids(self, value):
        if not value:
            raise serializers.ValidationError("At least one infraction is required.")
        if Infraction.objects.filter(id__in=value, active=True).count() != len(set(value)):
            raise serializers.ValidationError("One or more infractions are invalid.")
        return value

    def create(self, validated_data):
        ids = validated_data.pop("infraction_ids")
        ticket = Ticket.objects.create(**validated_data)
        for infraction in Infraction.objects.filter(id__in=ids):
            TicketInfraction.objects.create(ticket=ticket, infraction=infraction, amount_snapshot=infraction.amount)
        return ticket

    def update(self, instance, validated_data):
        validated_data.pop("infraction_ids", None)
        return super().update(instance, validated_data)

