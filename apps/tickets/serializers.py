from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.infractions.models import Infraction
from apps.media_storage.services import (
    MEDIA_TYPE_AUDIO,
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    get_audio_limits,
    get_image_limits,
    get_video_limits,
    validate_uploaded_media,
)
from .models import Ticket, TicketInfraction, TicketProof
from .services import generate_unique_ticket_number, is_valid_ticket_number


class TicketProofSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = TicketProof
        fields = (
            "id",
            "file",
            "url",
            "evidence_type",
            "mime_type",
            "duration_seconds",
            "caption",
            "size_bytes",
            "checksum_sha256",
            "created_at",
        )
        read_only_fields = ("mime_type", "size_bytes", "checksum_sha256", "url", "created_at")
        extra_kwargs = {"file": {"write_only": True}}

    def get_url(self, obj):
        if not obj.file:
            return ""
        request = self.context.get("request")
        path = f"/api/tickets/{obj.ticket_id}/proofs/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request else path

    def validate(self, attrs):
        file_obj = attrs.get("file")
        evidence_type = attrs.get("evidence_type") or TicketProof.EVIDENCE_PHOTO
        duration_seconds = attrs.get("duration_seconds")

        if evidence_type == TicketProof.EVIDENCE_PHOTO:
            metadata = validate_uploaded_media(
                file_obj,
                media_type=MEDIA_TYPE_IMAGE,
                duration_seconds=duration_seconds,
                field_name="file",
                **get_image_limits(),
            )
        elif evidence_type == TicketProof.EVIDENCE_VIDEO:
            metadata = validate_uploaded_media(
                file_obj,
                media_type=MEDIA_TYPE_VIDEO,
                duration_seconds=duration_seconds,
                field_name="file",
                **get_video_limits(),
            )
        elif evidence_type == TicketProof.EVIDENCE_AUDIO:
            metadata = validate_uploaded_media(
                file_obj,
                media_type=MEDIA_TYPE_AUDIO,
                duration_seconds=duration_seconds,
                field_name="file",
                **get_audio_limits(),
            )
        else:
            raise serializers.ValidationError({"evidence_type": "Unsupported evidence type."})

        attrs.update(metadata)
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
        return obj.infraction.article or ""


class TicketAgentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField(allow_blank=True)
    badge_number = serializers.CharField(allow_blank=True)
    role = serializers.CharField(allow_blank=True)
    has_signature = serializers.BooleanField()
    signature_updated_at = serializers.DateTimeField(allow_null=True)


class TicketSerializer(serializers.ModelSerializer):
    infraction_codes = serializers.ListField(child=serializers.CharField(), write_only=True, required=True)
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
            "occurred_at",
            "location_label",
            "latitude",
            "longitude",
            "ticket_number",
            "infraction_codes",
            "infractions",
            "proofs",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("agent", "agent_detail", "agent_signature_url", "ticket_number", "infractions", "proofs", "sync_status")

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

    def validate_infraction_codes(self, value):
        if not value:
            raise serializers.ValidationError("At least one infraction is required.")
        normalized = [str(code).strip().upper() for code in value if str(code).strip()]
        if len(normalized) != len(value):
            raise serializers.ValidationError("Infraction codes cannot be blank.")
        duplicates = sorted({code for code in normalized if normalized.count(code) > 1})
        if duplicates:
            raise serializers.ValidationError(f"Duplicate infraction codes: {', '.join(duplicates)}.")
        found = set(Infraction.objects.filter(code__in=normalized, active=True).values_list("code", flat=True))
        missing = [code for code in normalized if code not in found]
        if missing:
            raise serializers.ValidationError(f"Infractions inconnues ou inactives : {', '.join(missing)}.")
        return normalized

    def validate(self, attrs):
        ticket_number = attrs.get("ticket_number")
        if ticket_number and not is_valid_ticket_number(ticket_number):
            raise serializers.ValidationError({"ticket_number": "Ticket number must use exactly 8 uppercase hexadecimal characters."})
        return attrs

    def create(self, validated_data):
        codes = validated_data.pop("infraction_codes")
        last_error = None
        for _ in range(10):
            try:
                with transaction.atomic():
                    ticket = Ticket.objects.create(ticket_number=generate_unique_ticket_number(), **validated_data)
                    infractions = Infraction.objects.filter(code__in=codes, active=True)
                    infraction_by_code = {infraction.code: infraction for infraction in infractions}
                    for code in codes:
                        infraction = infraction_by_code[code]
                        TicketInfraction.objects.create(ticket=ticket, infraction=infraction, amount_snapshot=infraction.amount or 0)
                    return ticket
            except IntegrityError as exc:
                last_error = exc
        raise serializers.ValidationError({"ticket_number": "Impossible de generer un numero de PV unique."}) from last_error

    def update(self, instance, validated_data):
        validated_data.pop("infraction_codes", None)
        return super().update(instance, validated_data)
