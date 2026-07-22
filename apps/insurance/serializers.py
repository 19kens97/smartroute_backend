from django.db.models import Q
from rest_framework import serializers

from .models import InsurancePolicy


class InsurancePolicyReadSerializer(
    serializers.ModelSerializer
):
    plate_number = serializers.CharField(
        source="vehicle.plate_number",
        read_only=True,
    )
    owner_name = serializers.CharField(
        source="vehicle.owner.full_name",
        read_only=True,
        allow_null=True,
    )
    is_currently_valid = serializers.BooleanField(
        read_only=True,
    )
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = InsurancePolicy
        fields = (
            "id",
            "vehicle",
            "plate_number",
            "owner_name",
            "insurer",
            "policy_number",
            "valid_from",
            "valid_until",
            "status",
            "status_label",
            "is_currently_valid",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class InsurancePolicyWriteSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = InsurancePolicy
        fields = (
            "vehicle",
            "insurer",
            "policy_number",
            "valid_from",
            "valid_until",
            "status",
        )
        extra_kwargs = {
            "vehicle": {"required": False},
            "insurer": {"required": False},
            "policy_number": {"required": False},
            "valid_from": {"required": False},
            "valid_until": {"required": False},
            "status": {"required": False},
        }

    def validate_policy_number(self, value):
        normalized = (
            InsurancePolicy.normalize_policy_number(
                value
            )
        )

        if not normalized:
            raise serializers.ValidationError(
                "Le numéro de police est obligatoire."
            )

        matches = InsurancePolicy.objects.filter(
            policy_number__iexact=normalized
        )

        if self.instance is not None:
            matches = matches.exclude(
                pk=self.instance.pk
            )

        if matches.exists():
            raise serializers.ValidationError(
                "Ce numéro de police existe déjà."
            )

        return normalized

    def validate_insurer(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Le nom de l'assureur est obligatoire."
            )

        return value

    def validate(self, attrs):
        valid_from = attrs.get(
            "valid_from",
            getattr(
                self.instance,
                "valid_from",
                None,
            ),
        )
        valid_until = attrs.get(
            "valid_until",
            getattr(
                self.instance,
                "valid_until",
                None,
            ),
        )

        if (
            valid_from
            and valid_until
            and valid_until < valid_from
        ):
            raise serializers.ValidationError(
                {
                    "valid_until": (
                        "La date de fin ne peut pas être antérieure "
                        "à la date de début."
                    )
                }
            )

        if self.instance is None:
            required_fields = (
                "vehicle",
                "insurer",
                "policy_number",
                "valid_until",
            )

            missing = [
                field
                for field in required_fields
                if attrs.get(field) in (None, "")
            ]

            if missing:
                raise serializers.ValidationError(
                    {
                        field: (
                            "Ce champ est obligatoire."
                        )
                        for field in missing
                    }
                )

        return attrs

    def to_representation(self, instance):
        return InsurancePolicyReadSerializer(
            instance,
            context=self.context,
        ).data
