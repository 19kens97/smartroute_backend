from django.utils import timezone
from rest_framework import serializers

from .models import InsurancePolicy


class InsurancePolicySerializer(serializers.ModelSerializer):
    plate_number = serializers.CharField(source="vehicle.plate_number", read_only=True)
    owner_name = serializers.CharField(source="vehicle.owner.full_name", read_only=True, allow_null=True)
    is_currently_valid = serializers.SerializerMethodField()

    class Meta:
        model = InsurancePolicy
        fields = (
            "id",
            "vehicle",
            "plate_number",
            "owner_name",
            "insurer",
            "policy_number",
            "valid_until",
            "status",
            "is_currently_valid",
            "created_at",
            "updated_at",
        )

    def get_is_currently_valid(self, obj):
        return obj.status == InsurancePolicy.STATUS_VALID and obj.valid_until >= timezone.localdate()
