from rest_framework import serializers

from apps.vehicles.models import normalize_plate_number
from .models import Alert

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


class AlertSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    created_by_role = serializers.CharField(source="created_by.role", read_only=True, allow_null=True)
    alert_type_display = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = (
            "id",
            "alert_type",
            "alert_type_display",
            "plate_number",
            "description",
            "created_by",
            "created_by_name",
            "created_by_role",
            "source",
            "subject_nif",
            "system_reasons",
            "control_period_start",
            "control_period_end",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_by",
            "created_by_name",
            "created_by_role",
            "alert_type_display",
            "source",
            "subject_nif",
            "system_reasons",
            "control_period_start",
            "control_period_end",
            "created_at",
            "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["alert_type"].required = False
        return fields

    def get_created_by_name(self, obj):
        if obj.created_by is None:
            return None
        return obj.created_by.get_full_name().strip() or obj.created_by.username

    def get_alert_type_display(self, obj):
        return ALERT_TYPE_LABELS.get(obj.alert_type, obj.alert_type)

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
        return attrs