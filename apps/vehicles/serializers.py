from rest_framework import serializers

from .models import Vehicle, normalize_engine_number, normalize_plate_number


class VehicleSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.full_name", read_only=True, allow_null=True)

    class Meta:
        model = Vehicle
        fields = (
            "id", "plate_number", "brand", "model", "color", "year",
            "engine_number", "registration_valid_until", "is_wanted", "owner", "owner_name",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "owner_name", "created_at", "updated_at")

    def validate_plate_number(self, value):
        normalized = normalize_plate_number(value)
        if not normalized:
            raise serializers.ValidationError("Le numero d'immatriculation est requis.")
        matches = Vehicle.objects.filter(plate_number__iexact=normalized)
        if self.instance is not None:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError("Ce numero d'immatriculation existe deja.")
        return normalized

    def validate_engine_number(self, value):
        return normalize_engine_number(value)
