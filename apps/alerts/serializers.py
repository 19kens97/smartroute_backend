from pathlib import Path

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.vehicles.models import normalize_plate_number
from .models import Alert, AlertEvidence

ENTRY_AGENT_TYPES = {Alert.TYPE_WANTED_VEHICLE, Alert.TYPE_STOLEN_PLATE}
FIELD_AGENT_TYPES = {
    Alert.TYPE_FIELD_ESCAPE,
    Alert.TYPE_REFUSED_CONTROL,
    Alert.TYPE_SUSPICIOUS_BEHAVIOR,
}
SYSTEM_ONLY_TYPES = {Alert.TYPE_JUDICIAL}
PLATE_REQUIRED_TYPES = {
    Alert.TYPE_WANTED_VEHICLE,
    Alert.TYPE_STOLEN_PLATE,
    Alert.TYPE_JUDICIAL,
}
ALERT_TYPE_LABELS = {
    Alert.TYPE_FIELD_ESCAPE: "Fuite lors du contrôle",
    Alert.TYPE_REFUSED_CONTROL: "Refus de contrôle",
    Alert.TYPE_SUSPICIOUS_BEHAVIOR: "Comportement suspect",
    Alert.TYPE_WANTED_VEHICLE: "Véhicule volé ou recherché",
    Alert.TYPE_STOLEN_PLATE: "Plaque volée",
    Alert.TYPE_JUDICIAL: "Alerte judiciaire",
}
ALERT_SEVERITIES = {
    Alert.TYPE_FIELD_ESCAPE: "CRITICAL",
    Alert.TYPE_REFUSED_CONTROL: "CRITICAL",
    Alert.TYPE_SUSPICIOUS_BEHAVIOR: "WARNING",
    Alert.TYPE_WANTED_VEHICLE: "CRITICAL",
    Alert.TYPE_STOLEN_PLATE: "CRITICAL",
    Alert.TYPE_JUDICIAL: "CRITICAL",
}


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
            "url",
            "created_at",
        )
        read_only_fields = fields

    def get_url(self, obj):
        request = self.context.get("request")
        path = f"/api/alerts/{obj.alert_id}/evidence/{obj.pk}/"
        return request.build_absolute_uri(path) if request is not None else path


class AlertPresentationMixin:
    def get_alert_type_display(self, obj):
        return ALERT_TYPE_LABELS.get(obj.alert_type, obj.alert_type)

    def get_severity(self, obj):
        return ALERT_SEVERITIES.get(obj.alert_type, "INFO")

    def get_is_opened(self, obj):
        return bool(getattr(obj, "is_opened_for_user", False))



class AlertListSerializer(AlertPresentationMixin, serializers.ModelSerializer):
    alert_type_display = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    is_opened = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = (
            "id",
            "alert_type",
            "alert_type_display",
            "severity",
            "plate_number",
            "source",
            "is_opened",
            "created_at",
        )
        read_only_fields = fields


class AlertSerializer(AlertPresentationMixin, serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    created_by_role = serializers.CharField(source="created_by.role", read_only=True, allow_null=True)
    alert_type_display = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    is_opened = serializers.SerializerMethodField()
    evidence = AlertEvidenceSerializer(many=True, read_only=True)
    evidence_type = serializers.ChoiceField(
        choices=[AlertEvidence.TYPE_AUDIO, AlertEvidence.TYPE_VIDEO],
        write_only=True,
        required=False,
    )
    evidence_file = serializers.FileField(write_only=True, required=False)
    evidence_duration_seconds = serializers.IntegerField(write_only=True, required=False, min_value=0)

    class Meta:
        model = Alert
        fields = (
            "id", "alert_type", "alert_type_display", "severity", "plate_number",
            "description", "created_by", "created_by_name", "created_by_role",
            "source", "subject_nif", "system_reasons", "control_period_start",
            "control_period_end", "is_opened", "evidence", "evidence_type",
            "evidence_file", "evidence_duration_seconds", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "created_by", "created_by_name", "created_by_role",
            "alert_type_display", "severity", "source", "subject_nif",
            "system_reasons", "control_period_start", "control_period_end",
            "is_opened", "evidence", "created_at", "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["alert_type"].required = False
            fields["evidence_type"].required = False
            fields["evidence_file"].required = False
        return fields

    def get_created_by_name(self, obj):
        if obj.created_by is None:
            return None
        return obj.created_by.get_full_name().strip() or obj.created_by.username


    def _validate_evidence(self, attrs):
        evidence_file = attrs.get("evidence_file")
        evidence_type = attrs.get("evidence_type")
        duration = attrs.get("evidence_duration_seconds")

        if evidence_file is None and evidence_type is None:
            return
        if evidence_file is None:
            raise serializers.ValidationError({"evidence_file": "Le fichier de preuve est requis."})
        if evidence_type is None:
            raise serializers.ValidationError({"evidence_type": "Le type de preuve est requis."})

        mime_type = (getattr(evidence_file, "content_type", "") or "").lower()
        extension = Path(evidence_file.name or "").suffix.lower()
        if evidence_type == AlertEvidence.TYPE_AUDIO:
            allowed_mime_types = set(settings.ALERT_EVIDENCE_ALLOWED_AUDIO_MIME_TYPES)
            allowed_extensions = set(settings.ALERT_EVIDENCE_ALLOWED_AUDIO_EXTENSIONS)
            max_size = settings.ALERT_EVIDENCE_AUDIO_MAX_MB * 1024 * 1024
            max_duration = settings.ALERT_EVIDENCE_AUDIO_MAX_DURATION_SECONDS
        else:
            allowed_mime_types = set(settings.ALERT_EVIDENCE_ALLOWED_VIDEO_MIME_TYPES)
            allowed_extensions = set(settings.ALERT_EVIDENCE_ALLOWED_VIDEO_EXTENSIONS)
            max_size = settings.ALERT_EVIDENCE_VIDEO_MAX_MB * 1024 * 1024
            max_duration = settings.ALERT_EVIDENCE_VIDEO_MAX_DURATION_SECONDS

        if mime_type not in allowed_mime_types:
            raise serializers.ValidationError({"evidence_file": "Type MIME de preuve non autorisé."})
        if extension not in allowed_extensions:
            raise serializers.ValidationError({"evidence_file": "Extension de preuve non autorisée."})
        if evidence_file.size > max_size:
            raise serializers.ValidationError({"evidence_file": "Le fichier de preuve est trop volumineux."})
        if duration is not None and duration > max_duration:
            raise serializers.ValidationError({"evidence_duration_seconds": "La durée de la preuve dépasse la limite autorisée."})

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        role = getattr(user, "role", None)
        instance = self.instance
        incoming_type = attrs.get("alert_type")
        alert_type = incoming_type or getattr(instance, "alert_type", None)

        if instance is None:
            if alert_type in SYSTEM_ONLY_TYPES:
                raise serializers.ValidationError({"alert_type": "Une alerte judiciaire ne peut être créée que par le système."})
            allowed_types = ENTRY_AGENT_TYPES if role == "AGENT_SAISIE" else FIELD_AGENT_TYPES if role == "AGENT_TERRAIN" else set()
            if alert_type not in allowed_types:
                raise serializers.ValidationError({"alert_type": "Ce type d'alerte n'est pas autorisé pour votre rôle."})
        else:
            if instance.source == Alert.SOURCE_SYSTEM or instance.alert_type == Alert.TYPE_JUDICIAL:
                raise serializers.ValidationError("Une alerte judiciaire automatique ne peut pas être modifiée manuellement.")
            if incoming_type is not None and incoming_type != instance.alert_type:
                raise serializers.ValidationError({"alert_type": "Le type d'une alerte existante ne peut pas être modifié."})
            if attrs.get("evidence_file") is not None or attrs.get("evidence_type") is not None:
                raise serializers.ValidationError({"evidence_file": "La preuve ne peut être ajoutée qu'à la création de l'alerte."})

        plate_number = normalize_plate_number(attrs.get("plate_number", getattr(instance, "plate_number", "")))
        if alert_type in PLATE_REQUIRED_TYPES and not plate_number:
            raise serializers.ValidationError({"plate_number": "Le numéro d'immatriculation est obligatoire pour ce type d'alerte."})
        if len(plate_number) > 20:
            raise serializers.ValidationError({"plate_number": "Le numéro d'immatriculation ne peut pas dépasser 20 caractères."})
        if "plate_number" in attrs or instance is None:
            attrs["plate_number"] = plate_number

        description = str(attrs.get("description", getattr(instance, "description", ""))).strip()
        if instance is None and len(description) < 10:
            raise serializers.ValidationError({"description": "La description doit contenir au moins 10 caractères."})
        if "description" in attrs or instance is None:
            attrs["description"] = description

        self._validate_evidence(attrs)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        evidence_file = validated_data.pop("evidence_file", None)
        evidence_type = validated_data.pop("evidence_type", None)
        duration = validated_data.pop("evidence_duration_seconds", None)
        alert = Alert.objects.create(**validated_data)
        if evidence_file is not None and evidence_type is not None:
            AlertEvidence.objects.create(
                alert=alert,
                evidence_type=evidence_type,
                file=evidence_file,
                mime_type=(getattr(evidence_file, "content_type", "") or ""),
                size_bytes=getattr(evidence_file, "size", None),
                duration_seconds=duration,
                created_by=validated_data["created_by"],
            )
        return alert
