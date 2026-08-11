from rest_framework import serializers


class EmptyDataSerializer(serializers.Serializer):
    pass


class ApiEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.JSONField()
    errors = serializers.JSONField()


class EmptyEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = EmptyDataSerializer()
    errors = serializers.JSONField()


class AuthTokensSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField(required=False)
    account_type = serializers.CharField(required=False)
    role = serializers.CharField(required=False)
    user = serializers.JSONField(required=False)


class AuthEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = AuthTokensSerializer()
    errors = serializers.JSONField()


class DetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SignatureStatusSerializer(serializers.Serializer):
    has_signature = serializers.BooleanField()
    signature_updated_at = serializers.DateTimeField(allow_null=True)


class SignatureEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = SignatureStatusSerializer()
    errors = serializers.JSONField()


class ScanHistoryItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    agent = serializers.IntegerField()
    plate_number = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    image_url = serializers.CharField(allow_null=True)


class ScanHistoryEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = ScanHistoryItemSerializer(many=True)
    errors = serializers.JSONField()


class BinaryReferenceSerializer(serializers.Serializer):
    detail = serializers.CharField()
    scan = serializers.IntegerField(allow_null=True)
    ticket_proof = serializers.IntegerField(allow_null=True)
    alert_evidence = serializers.IntegerField(allow_null=True)


class GeminiScanResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField(required=False, allow_blank=True)
    raw_response = serializers.CharField(allow_blank=True)
    plate_number = serializers.CharField(allow_blank=True)
    plate_detected = serializers.BooleanField()
    model_used = serializers.CharField(allow_blank=True)
    vehicle = serializers.JSONField(allow_null=True)
    documents = serializers.JSONField()
    tickets = serializers.JSONField()
    scanned_at = serializers.CharField(allow_null=True)


class GeminiErrorResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    errors = serializers.JSONField(required=False)


class DashboardSummaryEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.JSONField()
    errors = serializers.JSONField()


class SyncPullDataSerializer(serializers.Serializer):
    request_uuid = serializers.UUIDField()
    status = serializers.CharField()
    cursor = serializers.DateTimeField(allow_null=True)
    next_cursor = serializers.DateTimeField(allow_null=True)
    has_more = serializers.BooleanField()
    items = serializers.JSONField()


class SyncPullEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = SyncPullDataSerializer()
    errors = serializers.JSONField()