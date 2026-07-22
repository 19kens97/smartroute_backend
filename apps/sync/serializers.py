from rest_framework import serializers

from .models import SyncDevice, SyncItemLog, SyncSession


class SyncDeviceRegisterSerializer(serializers.Serializer):
    device_uuid = serializers.UUIDField()
    device_name = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        default="",
    )
    platform = serializers.ChoiceField(
        choices=SyncDevice.Platform.choices,
        required=False,
        default=SyncDevice.Platform.ANDROID,
    )
    app_version = serializers.CharField(
        max_length=40,
        required=False,
        allow_blank=True,
        default="",
    )


class SyncDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncDevice
        fields = (
            "id",
            "device_uuid",
            "device_name",
            "platform",
            "app_version",
            "last_seen_at",
            "is_active",
            "revoked_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SyncDeviceRevokeSerializer(serializers.Serializer):
    device_uuid = serializers.UUIDField()


class SyncPushItemSerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(
        choices=SyncItemLog.EntityType.choices
    )
    operation = serializers.ChoiceField(
        choices=SyncItemLog.Operation.choices
    )
    client_uuid = serializers.UUIDField()
    base_version = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )
    data = serializers.JSONField()

    def validate_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Le champ data doit être un objet JSON."
            )
        return value


class SyncPushRequestSerializer(serializers.Serializer):
    device_uuid = serializers.UUIDField()
    request_uuid = serializers.UUIDField()
    items = SyncPushItemSerializer(
        many=True,
        allow_empty=True,
    )

    def validate_items(self, value):
        maximum = 100
        if len(value) > maximum:
            raise serializers.ValidationError(
                f"Un lot ne peut pas dépasser {maximum} éléments."
            )

        keys = [
            (
                item["entity_type"],
                str(item["client_uuid"]),
                item["operation"],
            )
            for item in value
        ]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError(
                "Le lot contient des opérations dupliquées."
            )
        return value


class SyncPullRequestSerializer(serializers.Serializer):
    device_uuid = serializers.UUIDField()
    request_uuid = serializers.UUIDField()
    cursor = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )
    entity_types = serializers.ListField(
        child=serializers.ChoiceField(
            choices=SyncItemLog.EntityType.choices
        ),
        required=False,
        allow_empty=True,
        default=list,
    )
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=200,
        default=100,
    )


class SyncStatusQuerySerializer(serializers.Serializer):
    request_uuid = serializers.UUIDField()


class SyncItemResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncItemLog
        fields = (
            "entity_type",
            "operation",
            "client_uuid",
            "server_id",
            "status",
            "base_version",
            "server_version",
            "error_code",
            "error_message",
            "processed_at",
        )
        read_only_fields = fields


class SyncSessionSerializer(serializers.ModelSerializer):
    items = SyncItemResultSerializer(
        many=True,
        read_only=True,
    )
    device_uuid = serializers.UUIDField(
        source="device.device_uuid",
        read_only=True,
    )

    class Meta:
        model = SyncSession
        fields = (
            "request_uuid",
            "device_uuid",
            "direction",
            "status",
            "cursor",
            "next_cursor",
            "item_count",
            "success_count",
            "failure_count",
            "conflict_count",
            "started_at",
            "completed_at",
            "error_code",
            "error_message",
            "items",
        )
        read_only_fields = fields
