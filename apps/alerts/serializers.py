from rest_framework import serializers
from .models import Alert

FIELD_TYPES = {"FIELD_ESCAPE", "REFUSED_CONTROL", "SUSPICIOUS_BEHAVIOR"}
CRITICAL_TYPES = {"WANTED_VEHICLE", "STOLEN_PLATE", "JUDICIAL_ALERT"}

class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = ("created_by",)

    def validate_alert_type(self, value):
        user = self.context["request"].user
        if user.role == "AGENT_TERRAIN" and value not in FIELD_TYPES:
            raise serializers.ValidationError("Field agents can only create field alerts.")
        if value in CRITICAL_TYPES and user.role != "ADMIN":
            raise serializers.ValidationError("Critical alerts are reserved to ADMIN.")
        return value
