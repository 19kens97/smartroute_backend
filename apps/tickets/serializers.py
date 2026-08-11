from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import AgentProfile
from apps.infractions.models import Infraction
from apps.vehicles.models import Vehicle
from apps.media_storage.services import (
    MEDIA_TYPE_AUDIO,
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    get_audio_limits,
    get_image_limits,
    get_video_limits,
    validate_uploaded_media,
)

from .models import Ticket, TicketInfraction, TicketProof, TicketVerbalization
from .services import generate_unique_ticket_number, next_verbalization_sequence


def _profile(user):
    try:
        return user.agent_profile
    except (AttributeError, AgentProfile.DoesNotExist):
        return None


def _display_name(user):
    if user is None:
        return None
    person = getattr(user, "person", None)
    return getattr(person, "full_name", "") or user.email or user.username


def _signature(profile):
    if profile is None:
        return None
    return getattr(profile, "signature_file", None) or getattr(profile, "signature", None)


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

    @extend_schema_field(serializers.URLField())
    def get_url(self, obj):
        request = self.context.get("request")
        path = (
            f"/api/tickets/{obj.verbalization.ticket_id}/"
            f"verbalizations/{obj.verbalization_id}/proofs/{obj.pk}/download/"
        )
        return request.build_absolute_uri(path) if request else path

    def validate(self, attrs):
        file_obj = attrs.get("file")
        evidence_type = attrs.get("evidence_type", TicketProof.EvidenceType.PHOTO)
        duration = attrs.get("duration_seconds")

        if evidence_type == TicketProof.EvidenceType.PHOTO:
            metadata = validate_uploaded_media(
                file_obj,
                media_type=MEDIA_TYPE_IMAGE,
                duration_seconds=duration,
                field_name="file",
                **get_image_limits(),
            )
        elif evidence_type == TicketProof.EvidenceType.VIDEO:
            metadata = validate_uploaded_media(
                file_obj,
                media_type=MEDIA_TYPE_VIDEO,
                duration_seconds=duration,
                field_name="file",
                **get_video_limits(),
            )
        elif evidence_type == TicketProof.EvidenceType.AUDIO:
            metadata = validate_uploaded_media(
                file_obj,
                media_type=MEDIA_TYPE_AUDIO,
                duration_seconds=duration,
                field_name="file",
                **get_audio_limits(),
            )
        else:
            raise serializers.ValidationError({"evidence_type": "Type de preuve non supporté."})

        attrs.update(metadata)
        return attrs


class TicketInfractionReadSerializer(serializers.ModelSerializer):
    infraction_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = TicketInfraction
        fields = (
            "id",
            "infraction_id",
            "code_snapshot",
            "label_snapshot",
            "article_snapshot",
            "penalty_type_snapshot",
            "amount_snapshot",
            "minimum_amount_snapshot",
            "maximum_amount_snapshot",
            "amount_options_snapshot",
            "penalty_text_snapshot",
            "currency_snapshot",
        )
        read_only_fields = fields


class VerbalizationInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField(required=False)
    vehicle = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(),
        required=False,
        allow_null=True,
    )
    plate_number_snapshot = serializers.CharField(required=False, allow_blank=True)
    occurred_at = serializers.DateTimeField(required=False)
    location_label = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)
    infraction_codes = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )

    def to_internal_value(self, data):
        if "selected_amount" in data:
            raise serializers.ValidationError(
                {"selected_amount": "Le montant choisi n'est plus accepte sur une verbalisation."}
            )
        return super().to_internal_value(data)
    def validate_infraction_codes(self, value):
        normalized = [str(code).strip().upper() for code in value]
        if any(not code for code in normalized):
            raise serializers.ValidationError("Un code d'infraction ne peut pas être vide.")
        if len(normalized) != len(set(normalized)):
            raise serializers.ValidationError("Une même infraction ne peut être répétée dans une verbalisation.")
        found = set(
            Infraction.objects.filter(code__in=normalized, active=True).values_list("code", flat=True)
        )
        missing = [code for code in normalized if code not in found]
        if missing:
            raise serializers.ValidationError(
                "Infractions inconnues ou inactives : " + ", ".join(missing)
            )
        return normalized

    def validate(self, attrs):
        if "selected_amount" in getattr(self, "initial_data", {}):
            raise serializers.ValidationError(
                {"selected_amount": "Le montant choisi n'est plus accepte sur une verbalisation."}
            )
        vehicle = attrs.get("vehicle")
        plate = str(attrs.get("plate_number_snapshot") or "").strip()
        if vehicle is None and not plate:
            raise serializers.ValidationError(
                {"plate_number_snapshot": "Le véhicule ou la plaque est obligatoire."}
            )
        return attrs


class TicketVerbalizationSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()
    agent_role = serializers.SerializerMethodField()
    infractions = TicketInfractionReadSerializer(many=True, read_only=True)
    proofs = TicketProofSerializer(many=True, read_only=True)

    class Meta:
        model = TicketVerbalization
        fields = (
            "id",
            "client_uuid",
            "sequence_number",
            "agent",
            "agent_name",
            "agent_role",
            "vehicle",
            "plate_number_snapshot",
            "occurred_at",
            "location_label",
            "latitude",
            "longitude",
            "note",
            "status",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "infractions",
            "proofs",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_agent_name(self, obj):
        return _display_name(obj.agent)

    @extend_schema_field(serializers.CharField())
    def get_agent_role(self, obj):
        profile = _profile(obj.agent)
        return getattr(profile, "role", "") if profile else ""


class TicketListSerializer(serializers.ModelSerializer):
    verbalization_count = serializers.IntegerField(read_only=True)
    opened_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = (
            "id",
            "ticket_number",
            "barcode_value",
            "driver",
            "driver_dossier_snapshot",
            "driver_name_snapshot",
            "status",
            "sync_status",
            "pricing_status",
            "opened_by_name",
            "opened_at",
            "verbalization_count",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_opened_by_name(self, obj):
        return _display_name(obj.opened_by)


class TicketSerializer(serializers.ModelSerializer):
    first_verbalization = VerbalizationInputSerializer(write_only=True, required=True)
    verbalizations = TicketVerbalizationSerializer(many=True, read_only=True)
    opened_by_name = serializers.SerializerMethodField()
    barcode_image_url = serializers.SerializerMethodField()
    agent_signature_url = serializers.SerializerMethodField()
    verbalization_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ticket
        fields = (
            "id",
            "client_uuid",
            "ticket_number",
            "barcode_value",
            "barcode_image_url",
            "driver",
            "driver_dossier_snapshot",
            "driver_name_snapshot",
            "driver_nif_snapshot",
            "opened_by",
            "opened_by_name",
            "opened_at",
            "status",
            "sync_status",
            "pricing_status",
            "pricing_authority",
            "pricing_external_reference",
            "pricing_requested_at",
            "pricing_last_checked_at",
            "pricing_message",
            "note",
            "closed_at",
            "closed_by",
            "closure_reason",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "verbalization_count",
            "first_verbalization",
            "verbalizations",
            "agent_signature_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "ticket_number",
            "barcode_value",
            "barcode_image_url",
            "opened_by",
            "opened_by_name",
            "opened_at",
            "status",
            "pricing_status",
            "pricing_authority",
            "pricing_external_reference",
            "pricing_requested_at",
            "pricing_last_checked_at",
            "pricing_message",
            "closed_at",
            "closed_by",
            "closure_reason",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "verbalization_count",
            "verbalizations",
            "agent_signature_url",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_opened_by_name(self, obj):
        return _display_name(obj.opened_by)

    @extend_schema_field(serializers.URLField())
    def get_barcode_image_url(self, obj):
        request = self.context.get("request")
        path = f"/api/tickets/{obj.pk}/barcode/"
        return request.build_absolute_uri(path) if request else path

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_agent_signature_url(self, obj):
        first = obj.verbalizations.order_by("sequence_number").first()
        if first is None:
            return None
        profile = _profile(first.agent)
        if not _signature(profile):
            return None
        request = self.context.get("request")
        path = f"/api/tickets/{obj.pk}/agent-signature/"
        return request.build_absolute_uri(path) if request else path

    @transaction.atomic
    def create(self, validated_data):
        verbalization_data = validated_data.pop("first_verbalization")
        infraction_codes = verbalization_data.pop("infraction_codes")
        request = self.context["request"]
        last_error = None

        for _ in range(10):
            try:
                with transaction.atomic():
                    ticket = Ticket.objects.create(
                        ticket_number=generate_unique_ticket_number(),
                        opened_by=request.user,
                        **validated_data,
                    )
                    verbalization = TicketVerbalization.objects.create(
                        ticket=ticket,
                        sequence_number=1,
                        agent=request.user,
                        **verbalization_data,
                    )
                    infractions = {
                        item.code: item
                        for item in Infraction.objects.filter(
                            code__in=infraction_codes,
                            active=True,
                        )
                    }
                    for code in infraction_codes:
                        TicketInfraction.objects.create(
                            verbalization=verbalization,
                            infraction=infractions[code],
                        )
                    return ticket
            except IntegrityError as exc:
                last_error = exc
        raise serializers.ValidationError(
            {"ticket_number": "Impossible de générer un numéro de PV unique."}
        ) from last_error

    def update(self, instance, validated_data):
        validated_data.pop("first_verbalization", None)
        return super().update(instance, validated_data)


class AddVerbalizationSerializer(VerbalizationInputSerializer):
    @transaction.atomic
    def create(self, validated_data):
        infraction_codes = validated_data.pop("infraction_codes")
        ticket = self.context["ticket"]
        request = self.context["request"]
        sequence = next_verbalization_sequence(ticket)
        verbalization = TicketVerbalization.objects.create(
            ticket=ticket,
            sequence_number=sequence,
            agent=request.user,
            **validated_data,
        )
        infractions = {
            item.code: item
            for item in Infraction.objects.filter(code__in=infraction_codes, active=True)
        }
        for code in infraction_codes:
            TicketInfraction.objects.create(
                verbalization=verbalization,
                infraction=infractions[code],
            )
        return verbalization


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=1000)
