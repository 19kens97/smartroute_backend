from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import AgentProfile
from apps.media_storage.services import (
    MEDIA_TYPE_AUDIO,
    MEDIA_TYPE_VIDEO,
    get_audio_limits,
    get_video_limits,
    validate_uploaded_media,
)
from apps.vehicles.models import normalize_plate_number

from .models import Alert, AlertEvidence
from .taxonomy import alert_options_payload, is_alert_taxonomy_type, is_valid_specification


FIELD_AGENT_TYPES = {
    Alert.AlertType.TRAFFIC_ACCIDENT,
    Alert.AlertType.TRAFFIC,
    Alert.AlertType.ROAD_OBSTACLE,
    Alert.AlertType.ROAD_CONDITION,
    Alert.AlertType.DANGEROUS_CONDITION,
    Alert.AlertType.ROAD_CONTROL,
    Alert.AlertType.REINFORCEMENT,
    Alert.AlertType.SPECIAL_EVENT,
}
ADMINISTRATIVE_TYPES = {
    Alert.AlertType.WANTED_VEHICLE,
    Alert.AlertType.STOLEN_PLATE,
}
SYSTEM_ONLY_TYPES = {
    Alert.AlertType.JUDICIAL,
    Alert.AlertType.DOCUMENT_EXPIRY_WARNING,
}


def agent_role(user):
    try:
        return user.agent_profile.role
    except (AttributeError, AgentProfile.DoesNotExist):
        return None


def display_name(user):
    if user is None:
        return None
    person = getattr(user, "person", None)
    return getattr(person, "full_name", "") or user.email or user.username


class AlertEvidenceSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AlertEvidence
        fields = (
            "id",
            "evidence_type",
            "mime_type",
            "size_bytes",
            "duration_seconds",
            "checksum_sha256",
            "url",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.URLField())
    def get_url(self, obj):
        request = self.context.get("request")
        path = f"/api/alerts/{obj.alert_id}/evidence/{obj.pk}/"
        return request.build_absolute_uri(path) if request else path


class AlertListSerializer(serializers.ModelSerializer):
    alert_type_display = serializers.CharField(
        source="get_alert_type_display",
        read_only=True,
    )
    specification_display = serializers.CharField(
        source="get_specification_display",
        read_only=True,
    )
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    is_opened = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = (
            "id",
            "category",
            "category_display",
            "alert_type",
            "alert_type_display",
            "specification",
            "specification_display",
            "severity",
            "status",
            "plate_number",
            "source",
            "is_opened",
            "document_expires_on",
            "expires_at",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_is_opened(self, obj):
        return bool(getattr(obj, "is_opened_for_user", False))


class AlertSerializer(serializers.ModelSerializer):
    alert_type = serializers.ChoiceField(
        choices=list(Alert.AlertType.choices) + [("KIDNAPPING", "Enlevement")],
        required=False,
    )
    alert_type_display = serializers.CharField(
        source="get_alert_type_display",
        read_only=True,
    )
    specification_display = serializers.CharField(
        source="get_specification_display",
        read_only=True,
    )
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    created_by_name = serializers.SerializerMethodField()
    created_by_role = serializers.SerializerMethodField()
    is_opened = serializers.SerializerMethodField()
    evidence = AlertEvidenceSerializer(many=True, read_only=True)
    evidence_type = serializers.ChoiceField(
        choices=AlertEvidence.EvidenceType.choices,
        write_only=True,
        required=False,
    )
    evidence_file = serializers.FileField(
        write_only=True,
        required=False,
    )
    evidence_duration_seconds = serializers.IntegerField(
        write_only=True,
        required=False,
        min_value=0,
    )

    class Meta:
        model = Alert
        fields = (
            "id",
            "category",
            "category_display",
            "alert_type",
            "alert_type_display",
            "specification",
            "specification_display",
            "severity",
            "status",
            "status_display",
            "vehicle",
            "plate_number",
            "description",
            "created_by",
            "created_by_name",
            "created_by_role",
            "source",
            "subject_person",
            "subject_nif",
            "system_reasons",
            "control_period_start",
            "control_period_end",
            "document_expires_on",
            "expires_at",
            "resolved_at",
            "resolved_by",
            "resolution_note",
            "is_opened",
            "evidence",
            "evidence_type",
            "evidence_file",
            "evidence_duration_seconds",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "category",
            "severity",
            "status",
            "created_by",
            "created_by_name",
            "created_by_role",
            "source",
            "subject_person",
            "subject_nif",
            "system_reasons",
            "control_period_start",
            "control_period_end",
            "document_expires_on",
            "expires_at",
            "resolved_at",
            "resolved_by",
            "resolution_note",
            "is_opened",
            "evidence",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by_name(self, obj):
        return display_name(obj.created_by)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by_role(self, obj):
        return agent_role(obj.created_by)

    @extend_schema_field(serializers.BooleanField())
    def get_is_opened(self, obj):
        return bool(getattr(obj, "is_opened_for_user", False))

    def _validate_evidence(self, attrs):
        evidence_file = attrs.get("evidence_file")
        evidence_type = attrs.get("evidence_type")
        duration = attrs.get("evidence_duration_seconds")

        if evidence_file is None and evidence_type is None:
            return

        if evidence_file is None:
            raise serializers.ValidationError(
                {"evidence_file": "Le fichier de preuve est requis."}
            )

        if evidence_type is None:
            raise serializers.ValidationError(
                {"evidence_type": "Le type de preuve est requis."}
            )

        if evidence_type == AlertEvidence.EvidenceType.AUDIO:
            metadata = validate_uploaded_media(
                evidence_file,
                media_type=MEDIA_TYPE_AUDIO,
                duration_seconds=duration,
                field_name="evidence_file",
                **get_audio_limits(),
            )
        else:
            metadata = validate_uploaded_media(
                evidence_file,
                media_type=MEDIA_TYPE_VIDEO,
                duration_seconds=duration,
                field_name="evidence_file",
                **get_video_limits(),
            )

        attrs["evidence_metadata"] = metadata

    def validate(self, attrs):
        request = self.context.get("request")
        role = agent_role(getattr(request, "user", None))
        instance = self.instance
        incoming_type = attrs.get("alert_type")
        alert_type = incoming_type or getattr(instance, "alert_type", None)
        incoming_specification = attrs.get("specification")
        specification = incoming_specification if incoming_specification is not None else getattr(instance, "specification", "")

        if incoming_type == "KIDNAPPING":
            alert_type = Alert.AlertType.SPECIAL_EVENT
            specification = "KIDNAPPING"
            attrs["alert_type"] = alert_type
            attrs["specification"] = specification

        if is_alert_taxonomy_type(alert_type):
            if not specification:
                raise serializers.ValidationError(
                    {"specification": "La specification est obligatoire pour ce type d'alerte."}
                )
            if not is_valid_specification(alert_type, specification):
                raise serializers.ValidationError(
                    {"specification": "La specification selectionnee ne correspond pas au type d'alerte."}
                )
        elif specification:
            raise serializers.ValidationError(
                {"specification": "Ce type d'alerte ne supporte pas de specification."}
            )

        if instance is None:
            if alert_type in SYSTEM_ONLY_TYPES:
                raise serializers.ValidationError(
                    {
                        "alert_type": (
                            "Ce type d'alerte ne peut Ãªtre crÃ©Ã© "
                            "que par le systÃ¨me."
                        )
                    }
                )

            if role == AgentProfile.Role.AGENT_TERRAIN:
                allowed_types = FIELD_AGENT_TYPES
                attrs["category"] = Alert.Category.FIELD_REPORT
            elif role == AgentProfile.Role.AGENT_SAISIE:
                allowed_types = ADMINISTRATIVE_TYPES
                attrs["category"] = Alert.Category.ADMINISTRATIVE
            else:
                allowed_types = set()

            if alert_type not in allowed_types:
                raise serializers.ValidationError(
                    {
                        "alert_type": (
                            "Ce type d'alerte n'est pas autorisÃ© "
                            "pour votre rÃ´le."
                        )
                    }
                )
        else:
            if instance.category == Alert.Category.AUTOMATIC:
                raise serializers.ValidationError(
                    "Une alerte automatique ne peut pas Ãªtre modifiÃ©e manuellement."
                )

            if instance.is_terminal:
                raise serializers.ValidationError(
                    "Une alerte clÃ´turÃ©e ne peut plus Ãªtre modifiÃ©e."
                )

            if incoming_type is not None and incoming_type != instance.alert_type:
                raise serializers.ValidationError(
                    {
                        "alert_type": (
                            "Le type d'une alerte existante "
                            "ne peut pas Ãªtre modifiÃ©."
                        )
                    }
                )

            if (
                attrs.get("evidence_file") is not None
                or attrs.get("evidence_type") is not None
            ):
                raise serializers.ValidationError(
                    {
                        "evidence_file": (
                            "Une preuve ne peut Ãªtre ajoutÃ©e "
                            "qu'Ã  la crÃ©ation."
                        )
                    }
                )

        plate = normalize_plate_number(
            attrs.get(
                "plate_number",
                getattr(instance, "plate_number", ""),
            )
        )

        if alert_type in ADMINISTRATIVE_TYPES and not plate:
            raise serializers.ValidationError(
                {
                    "plate_number": (
                        "Le numÃ©ro d'immatriculation est obligatoire."
                    )
                }
            )

        if "plate_number" in attrs or instance is None:
            attrs["plate_number"] = plate

        description = str(
            attrs.get(
                "description",
                getattr(instance, "description", ""),
            )
        ).strip()

        if instance is None and len(description) < 10:
            raise serializers.ValidationError(
                {
                    "description": (
                        "La description doit contenir "
                        "au moins 10 caractÃ¨res."
                    )
                }
            )

        if "description" in attrs or instance is None:
            attrs["description"] = description

        if is_alert_taxonomy_type(alert_type):
            attrs["specification"] = specification

        self._validate_evidence(attrs)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        evidence_file = validated_data.pop("evidence_file", None)
        evidence_type = validated_data.pop("evidence_type", None)
        duration = validated_data.pop(
            "evidence_duration_seconds",
            None,
        )
        metadata = validated_data.pop("evidence_metadata", {})

        alert = Alert.objects.create(**validated_data)

        if evidence_file is not None and evidence_type is not None:
            AlertEvidence.objects.create(
                alert=alert,
                evidence_type=evidence_type,
                file=evidence_file,
                mime_type=metadata.get(
                    "mime_type",
                    getattr(evidence_file, "content_type", "") or "",
                ),
                size_bytes=metadata.get(
                    "size_bytes",
                    getattr(evidence_file, "size", None),
                ),
                checksum_sha256=metadata.get("checksum_sha256", ""),
                duration_seconds=duration,
                created_by=validated_data["created_by"],
            )

        return alert


class AlertCloseSerializer(serializers.Serializer):
    note = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=500,
    )

    def validate_note(self, value):
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError(
                "La justification doit contenir au moins 5 caractÃ¨res."
            )
        return value
