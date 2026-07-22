from django.db.models import Q
from rest_framework import serializers

from .models import (
    Vehicle,
    normalize_engine_number,
    normalize_plate_number,
    plate_number_lookup_variants,
)


class VehicleReadSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "plate_number",
            "brand",
            "model",
            "color",
            "year",
            "engine_number",
            "registration_valid_until",
            "is_wanted",
            "owner",
            "owner_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_owner_name(self, obj):
        owner = getattr(obj, "owner", None)
        return getattr(owner, "full_name", None) if owner else None


class VehicleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = (
            "plate_number",
            "brand",
            "model",
            "color",
            "year",
            "engine_number",
            "registration_valid_until",
            "is_wanted",
            "owner",
        )
        extra_kwargs = {
            field: {"required": False}
            for field in (
                "brand",
                "model",
                "color",
                "year",
                "engine_number",
                "registration_valid_until",
                "is_wanted",
                "owner",
            )
        }

    def validate_plate_number(self, value):
        normalized = normalize_plate_number(value)

        if not normalized:
            raise serializers.ValidationError(
                "Le numéro d'immatriculation est requis."
            )

        lookup = Q()

        for variant in plate_number_lookup_variants(
            normalized
        ):
            lookup |= Q(
                plate_number__iexact=variant
            )

        matches = Vehicle.objects.filter(lookup)

        if self.instance is not None:
            matches = matches.exclude(
                pk=self.instance.pk
            )

        if matches.exists():
            raise serializers.ValidationError(
                "Ce numéro d'immatriculation existe déjà."
            )

        return normalized

    def validate_engine_number(self, value):
        return normalize_engine_number(value)

    def to_representation(self, instance):
        return VehicleReadSerializer(
            instance,
            context=self.context,
        ).data
