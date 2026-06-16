from pathlib import Path
from django.conf import settings
from rest_framework import serializers
from apps.infractions.models import Infraction
from .models import Ticket, TicketInfraction, TicketProof

class TicketProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketProof
        fields = ("id", "file", "caption", "created_at")

    def validate_file(self, value):
        ext = Path(value.name).suffix.lower()
        if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise serializers.ValidationError("Unsupported file extension.")
        if value.size > settings.SECURE_UPLOAD_MAX_MB * 1024 * 1024:
            raise serializers.ValidationError("File too large.")
        return value

class TicketSerializer(serializers.ModelSerializer):
    infraction_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=True)
    proofs = TicketProofSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = ("id", "client_uuid", "agent", "driver_license", "plate_number_snapshot", "vehicle", "status", "note", "barcode_value", "barcode_image", "infraction_ids", "proofs", "created_at", "updated_at")
        read_only_fields = ("agent", "barcode_value", "barcode_image")

    def validate_infraction_ids(self, value):
        if not value:
            raise serializers.ValidationError("At least one infraction is required.")
        if Infraction.objects.filter(id__in=value, active=True).count() != len(set(value)):
            raise serializers.ValidationError("One or more infractions are invalid.")
        return value

    def create(self, validated_data):
        ids = validated_data.pop("infraction_ids")
        ticket = Ticket.objects.create(**validated_data)
        for i in Infraction.objects.filter(id__in=ids):
            TicketInfraction.objects.create(ticket=ticket, infraction=i, amount_snapshot=i.amount)
        return ticket

    def update(self, instance, validated_data):
        validated_data.pop("infraction_ids", None)
        return super().update(instance, validated_data)
