from django.db.models import Q
from rest_framework import serializers

from apps.owners.services import set_current_vehicle_owner

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


    def _ownership_actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None) if request else None

    def create(self, validated_data):
        owner = validated_data.pop("owner", None)
        vehicle = Vehicle.objects.create(**validated_data)
        if owner is not None:
            set_current_vehicle_owner(
                vehicle=vehicle,
                owner=owner,
                created_by=self._ownership_actor(),
            )
            vehicle.refresh_from_db(fields=("owner", "updated_at"))
        return vehicle

    def update(self, instance, validated_data):
        owner_was_provided = "owner" in validated_data
        owner = validated_data.pop("owner", None)

        if owner_was_provided and owner is None:
            raise serializers.ValidationError(
                {
                    "owner": (
                        "Utilisez l'historique de propriete pour terminer "
                        "une propriete; owner ne peut pas etre vide ici."
                    )
                }
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if validated_data:
            instance.save()

        if owner_was_provided:
            set_current_vehicle_owner(
                vehicle=instance,
                owner=owner,
                created_by=self._ownership_actor(),
            )
            instance.refresh_from_db(fields=("owner", "updated_at"))

        return instance

    def to_representation(self, instance):
        return VehicleReadSerializer(
            instance,
            context=self.context,
        ).data
