from rest_framework import serializers
from .models import Driver
from .services import get_license_validity_state

class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")


class DriverLicenseReadSerializer(serializers.ModelSerializer):
    is_currently_valid = serializers.SerializerMethodField()
    validity_state = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = (
            "id",
            "dossier_number",
            "nif",
            "full_name",
            "address",
            "birth_date",
            "sex",
            "blood_group",
            "license_type",
            "issue_place",
            "issue_date",
            "expires_at",
            "created_at",
            "updated_at",
            "is_currently_valid",
            "validity_state",
        )
        read_only_fields = fields

    def get_validity_state(self, obj):
        return get_license_validity_state(obj)

    def get_is_currently_valid(self, obj):
        return self.get_validity_state(obj) == "VALID"


class DriverDossierSearchQuerySerializer(serializers.Serializer):
    dossier_number = serializers.CharField(required=True, allow_blank=False, max_length=50, trim_whitespace=True)


class DriverNIFSearchQuerySerializer(serializers.Serializer):
    nif = serializers.CharField(required=True, allow_blank=False, max_length=40, trim_whitespace=True)
