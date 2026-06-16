from rest_framework import serializers

from .models import InsurancePolicy


class InsurancePolicySerializer(serializers.ModelSerializer):
    plate_number = serializers.CharField(source="vehicle.plate_number", read_only=True)

    class Meta:
        model = InsurancePolicy
        fields = (
            "id",
            "vehicle",
            "plate_number",
            "insurer",
            "policy_number",
            "valid_until",
            "status",
            "created_at",
            "updated_at",
        )

