from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Person
from apps.core.models import AuditLog
from apps.core.services import create_audit_log

from .models import Owner, VehicleOwnership


class PersonInputSerializer(serializers.Serializer):
    nif = serializers.CharField(
        max_length=40,
        required=True,
        allow_blank=False,
    )
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    birth_date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    def validate_nif(self, value):
        normalized = Person.normalize_nif(value)
        if not normalized:
            raise serializers.ValidationError("Le NIF est invalide.")
        return normalized


class PersonSummarySerializer(serializers.ModelSerializer):
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


class OwnerSerializer(serializers.ModelSerializer):
    person = PersonSummarySerializer(read_only=True)
    person_id = serializers.PrimaryKeyRelatedField(
        source="person",
        queryset=Person.objects.all(),
        write_only=True,
        required=False,
    )
    person_data = PersonInputSerializer(
        write_only=True,
        required=False,
    )
    nif = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    birth_date = serializers.DateField(read_only=True)
    current_vehicle_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Owner
        fields = (
            "id",
            "person",
            "person_id",
            "person_data",
            "nif",
            "full_name",
            "birth_date",
            "phone",
            "address",
            "is_active",
            "current_vehicle_count",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_by",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        person = attrs.get("person")
        person_data = attrs.pop("person_data", None)

        if self.instance is None:
            if bool(person) == bool(person_data):
                raise serializers.ValidationError(
                    {
                        "person": (
                            "Fournissez soit person_id, soit person_data, "
                            "mais jamais les deux."
                        )
                    }
                )
        elif person or person_data:
            raise serializers.ValidationError(
                {
                    "person": (
                        "La personne d'un propriétaire existant "
                        "ne peut pas être remplacée."
                    )
                }
            )

        attrs["_person_data"] = person_data
        return attrs

    def _resolve_person(self, validated_data):
        person = validated_data.pop("person", None)
        person_data = validated_data.pop("_person_data", None)

        if person is not None:
            return person

        nif = person_data["nif"]
        defaults = {
            "first_name": person_data["first_name"],
            "last_name": person_data["last_name"],
            "birth_date": person_data.get("birth_date"),
        }

        person, created = Person.objects.get_or_create(
            nif=nif,
            defaults=defaults,
        )

        if not created:
            incoming_first = Person.normalize_name(
                person_data["first_name"]
            )
            incoming_last = Person.normalize_name(
                person_data["last_name"]
            )

            if (
                person.first_name.casefold() != incoming_first.casefold()
                or person.last_name.casefold() != incoming_last.casefold()
            ):
                raise serializers.ValidationError(
                    {
                        "person_data": (
                            "Une personne existe déjà avec ce NIF, "
                            "mais son nom ne correspond pas."
                        )
                    }
                )

            incoming_birth_date = person_data.get("birth_date")
            if (
                incoming_birth_date
                and person.birth_date
                and incoming_birth_date != person.birth_date
            ):
                raise serializers.ValidationError(
                    {
                        "person_data": (
                            "La date de naissance fournie ne correspond "
                            "pas à celle déjà enregistrée."
                        )
                    }
                )

            if incoming_birth_date and not person.birth_date:
                person.birth_date = incoming_birth_date
                person.save(update_fields=("birth_date", "updated_at"))

        return person

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        person = self._resolve_person(validated_data)

        if Owner.objects.filter(person=person).exists():
            raise serializers.ValidationError(
                {
                    "person": (
                        "Cette personne possède déjà un profil propriétaire."
                    )
                }
            )

        owner = Owner.objects.create(
            person=person,
            created_by=request.user,
            **validated_data,
        )

        create_audit_log(
            actor=request.user,
            action=AuditLog.Action.CREATE,
            instance=owner,
            request=request,
            payload={
                "person_id": person.id,
                "nif": person.nif,
            },
        )
        return owner

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context["request"]
        validated_data.pop("_person_data", None)
        changed_fields = []

        for field, value in validated_data.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                changed_fields.append(field)

        if changed_fields:
            instance.save()

            create_audit_log(
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                instance=instance,
                request=request,
                payload={"changed_fields": changed_fields},
            )

        return instance


class VehicleOwnershipSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(
        source="owner.full_name",
        read_only=True,
    )
    owner_nif = serializers.CharField(
        source="owner.nif",
        read_only=True,
    )
    vehicle_display = serializers.CharField(
        source="vehicle.__str__",
        read_only=True,
    )

    class Meta:
        model = VehicleOwnership
        fields = (
            "id",
            "vehicle",
            "vehicle_display",
            "owner",
            "owner_name",
            "owner_nif",
            "ownership_type",
            "start_date",
            "end_date",
            "is_current",
            "source_document_reference",
            "note",
            "created_by",
            "ended_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "end_date",
            "is_current",
            "created_by",
            "ended_by",
            "created_at",
            "updated_at",
        )

    def validate_owner(self, owner):
        if not owner.is_active:
            raise serializers.ValidationError(
                "Le propriétaire doit être actif."
            )
        return owner

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        vehicle = validated_data["vehicle"]
        start_date = validated_data["start_date"]

        current = (
            VehicleOwnership.objects
            .select_for_update()
            .filter(vehicle=vehicle, is_current=True)
            .first()
        )

        if current:
            if current.owner_id == validated_data["owner"].id:
                raise serializers.ValidationError(
                    {
                        "vehicle": (
                            "Ce propriétaire est déjà le propriétaire "
                            "actuel du véhicule."
                        )
                    }
                )

            if start_date < current.start_date:
                raise serializers.ValidationError(
                    {
                        "start_date": (
                            "La nouvelle propriété ne peut pas commencer "
                            "avant la propriété actuelle."
                        )
                    }
                )

            current.is_current = False
            current.end_date = start_date
            current.ended_by = request.user
            current.save()

            create_audit_log(
                actor=request.user,
                action=AuditLog.Action.STATUS_CHANGE,
                instance=current,
                request=request,
                payload={
                    "is_current": False,
                    "end_date": str(start_date),
                },
            )

        ownership = VehicleOwnership.objects.create(
            created_by=request.user,
            is_current=True,
            **validated_data,
        )

        create_audit_log(
            actor=request.user,
            action=AuditLog.Action.CREATE,
            instance=ownership,
            request=request,
            payload={
                "vehicle_id": vehicle.id,
                "owner_id": ownership.owner_id,
            },
        )
        return ownership


class EndVehicleOwnershipSerializer(serializers.Serializer):
    end_date = serializers.DateField()
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )

    def validate(self, attrs):
        ownership = self.context["ownership"]

        if not ownership.is_current:
            raise serializers.ValidationError(
                "Cette propriété est déjà terminée."
            )

        if attrs["end_date"] < ownership.start_date:
            raise serializers.ValidationError(
                {
                    "end_date": (
                        "La date de fin ne peut pas être antérieure "
                        "à la date de début."
                    )
                }
            )

        return attrs

    @transaction.atomic
    def save(self):
        ownership = (
            VehicleOwnership.objects
            .select_for_update()
            .get(pk=self.context["ownership"].pk)
        )
        request = self.context["request"]

        ownership.is_current = False
        ownership.end_date = self.validated_data["end_date"]
        ownership.ended_by = request.user

        note = self.validated_data.get("note", "").strip()
        if note:
            ownership.note = (
                f"{ownership.note}\n{note}".strip()
                if ownership.note
                else note
            )

        ownership.save()

        create_audit_log(
            actor=request.user,
            action=AuditLog.Action.STATUS_CHANGE,
            instance=ownership,
            request=request,
            payload={
                "is_current": False,
                "end_date": str(ownership.end_date),
            },
        )
        return ownership
