from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Person

from .models import Driver
from .services import get_license_validity_state


class PersonDriverReadSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Person
        fields = (
            "id",
            "nif",
            "first_name",
            "last_name",
            "full_name",
            "birth_date",
        )
        read_only_fields = fields


class PersonDriverWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = (
            "nif",
            "first_name",
            "last_name",
            "birth_date",
        )

    def validate_nif(self, value):
        return Person.normalize_nif(value) if value else None


class DriverLicenseReadSerializer(serializers.ModelSerializer):
    person = PersonDriverReadSerializer(read_only=True)
    nif = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    birth_date = serializers.DateField(read_only=True)
    is_currently_valid = serializers.SerializerMethodField()
    validity_state = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = (
            "id",
            "person",
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

    @extend_schema_field(serializers.CharField())
    def get_validity_state(self, obj):
        return get_license_validity_state(obj)

    @extend_schema_field(serializers.BooleanField())
    def get_is_currently_valid(self, obj):
        return self.get_validity_state(obj) == "VALID"


class DriverCreateSerializer(serializers.ModelSerializer):
    """
    Crée un Driver avec :
    - soit `person` pour créer une nouvelle Person ;
    - soit `person_id` pour utiliser une Person existante.
    """

    person = PersonDriverWriteSerializer(required=False, write_only=True)
    person_id = serializers.PrimaryKeyRelatedField(
        source="existing_person",
        queryset=Person.objects.all(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Driver
        fields = (
            "person",
            "person_id",
            "dossier_number",
            "address",
            "sex",
            "blood_group",
            "license_type",
            "issue_place",
            "issue_date",
            "expires_at",
        )

    def validate_dossier_number(self, value):
        return Driver.normalize_dossier_number(value)

    def validate(self, attrs):
        person_data = attrs.get("person")
        existing_person = attrs.get("existing_person")

        has_person_data = person_data is not None
        has_person_id = existing_person is not None

        if has_person_data == has_person_id:
            raise serializers.ValidationError(
                {
                    "person": (
                        "Fournissez soit 'person' pour créer une nouvelle "
                        "personne, soit 'person_id' pour utiliser une personne "
                        "existante, mais pas les deux."
                    )
                }
            )

        if person_data:
            nif = person_data.get("nif")
            if nif:
                normalized_nif = Person.normalize_nif(nif)
                existing_by_nif = Person.objects.filter(
                    nif=normalized_nif
                ).first()
                if existing_by_nif:
                    raise serializers.ValidationError(
                        {
                            "person": (
                                "Une personne possède déjà ce NIF. "
                                f"Utilisez person_id={existing_by_nif.pk}."
                            )
                        }
                    )

        if (
            existing_person
            and hasattr(existing_person, "driver_record")
        ):
            raise serializers.ValidationError(
                {
                    "person_id": (
                        "Cette personne possède déjà un dossier conducteur."
                    )
                }
            )

        issue_date = attrs.get("issue_date")
        expires_at = attrs.get("expires_at")

        if issue_date and expires_at and expires_at < issue_date:
            raise serializers.ValidationError(
                {
                    "expires_at": (
                        "La date d'expiration ne peut pas être antérieure "
                        "à la date de délivrance."
                    )
                }
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        person_data = validated_data.pop("person", None)
        existing_person = validated_data.pop("existing_person", None)

        person = (
            existing_person
            if existing_person is not None
            else Person.objects.create(**person_data)
        )

        return Driver.objects.create(
            person=person,
            **validated_data,
        )

    def to_representation(self, instance):
        return DriverLicenseReadSerializer(
            instance,
            context=self.context,
        ).data


class DriverUpdateSerializer(serializers.ModelSerializer):
    """
    PATCH du dossier conducteur.

    Les données civiles de Person ne sont pas modifiées par cet endpoint.
    """

    class Meta:
        model = Driver
        fields = (
            "dossier_number",
            "address",
            "sex",
            "blood_group",
            "license_type",
            "issue_place",
            "issue_date",
            "expires_at",
        )
        extra_kwargs = {
            field: {"required": False}
            for field in fields
        }

    def validate_dossier_number(self, value):
        return Driver.normalize_dossier_number(value)

    def validate(self, attrs):
        issue_date = attrs.get(
            "issue_date",
            getattr(self.instance, "issue_date", None),
        )
        expires_at = attrs.get(
            "expires_at",
            getattr(self.instance, "expires_at", None),
        )

        if issue_date and expires_at and expires_at < issue_date:
            raise serializers.ValidationError(
                {
                    "expires_at": (
                        "La date d'expiration ne peut pas être antérieure "
                        "à la date de délivrance."
                    )
                }
            )

        return attrs

    def to_representation(self, instance):
        return DriverLicenseReadSerializer(
            instance,
            context=self.context,
        ).data


class DriverDossierSearchQuerySerializer(serializers.Serializer):
    dossier_number = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=50,
        trim_whitespace=True,
    )

    def validate_dossier_number(self, value):
        return Driver.normalize_dossier_number(value)


class DriverNIFSearchQuerySerializer(serializers.Serializer):
    nif = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=40,
        trim_whitespace=True,
    )


