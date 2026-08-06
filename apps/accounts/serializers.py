from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    TokenRefreshSerializer as SimpleJWTTokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.drivers.models import Driver

from .models import AgentProfile, Person, User


class DriverReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = [
            "dossier_number",
            "address",
            "sex",
            "blood_group",
            "license_type",
            "issue_place",
            "issue_date",
            "expires_at",
        ]


class PersonSerializer(serializers.ModelSerializer):
    driver_record = DriverReadSerializer(read_only=True)

    class Meta:
        model = Person
        fields = [
            "id",
            "nif",
            "first_name",
            "last_name",
            "birth_date",
            "full_name",
            "driver_record",
        ]
        read_only_fields = ["id", "full_name", "driver_record"]

    def validate_nif(self, value):
        return Person.normalize_nif(value) if value else None


class AgentProfileReadSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = AgentProfile
        fields = [
            "role",
            "role_label",
            "badge_number",
            "post",
            "precinct",
            "signature_updated_at",
            "is_active",
        ]


class UserReadSerializer(serializers.ModelSerializer):
    person = PersonSerializer(read_only=True)
    agent_profile = AgentProfileReadSerializer(read_only=True)
    account_type_label = serializers.CharField(
        source="get_account_type_display",
        read_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "account_type",
            "account_type_label",
            "is_active",
            "person",
            "agent_profile",
        ]


class ProfessionalLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        generic_error = "Email ou mot de passe incorrect."

        try:
            user = User.objects.select_related("agent_profile", "person").get(
                email__iexact=attrs["email"],
                account_type=User.AccountType.PROFESSIONAL,
            )
        except User.DoesNotExist:
            raise serializers.ValidationError(generic_error)

        if not user.check_password(attrs["password"]):
            raise serializers.ValidationError(generic_error)
        if not user.is_active:
            raise serializers.ValidationError("Ce compte professionnel est désactivé.")

        try:
            profile = user.agent_profile
        except AgentProfile.DoesNotExist:
            raise serializers.ValidationError(
                "Aucun profil agent n’est associé à ce compte."
            )

        if not profile.is_active:
            raise serializers.ValidationError("Le profil agent est désactivé.")

        attrs["user"] = user
        return attrs


class MobileLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False, allow_blank=False)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        identifier = attrs.get("email") or attrs.get("username")
        if not identifier:
            raise serializers.ValidationError({"email": "Email requis."})

        attrs["email"] = identifier.strip().lower()
        return attrs


class PersonalLoginSerializer(serializers.Serializer):
    dossier_number = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_dossier_number(self, value):
        return Driver.normalize_dossier_number(value)

    def validate(self, attrs):
        generic_error = "Numéro de dossier ou mot de passe incorrect."

        try:
            driver = Driver.objects.select_related("person").get(
                dossier_number__iexact=attrs["dossier_number"]
            )
        except Driver.DoesNotExist:
            raise serializers.ValidationError(generic_error)

        try:
            user = driver.person.accounts.get(
                account_type=User.AccountType.PERSONAL
            )
        except User.DoesNotExist:
            raise serializers.ValidationError(generic_error)

        if not user.check_password(attrs["password"]):
            raise serializers.ValidationError(generic_error)
        if not user.is_active:
            raise serializers.ValidationError("Ce compte personnel est désactivé.")

        attrs["user"] = user
        attrs["driver"] = driver
        return attrs


class AgentProfileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = ["role", "badge_number", "post", "precinct", "is_active"]


class DriverWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = [
            "dossier_number",
            "address",
            "sex",
            "blood_group",
            "license_type",
            "issue_place",
            "issue_date",
            "expires_at",
        ]


class UserCreateSerializer(serializers.Serializer):
    person = PersonSerializer(required=False)
    person_id = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(),
        required=False,
        write_only=True,
    )
    account_type = serializers.ChoiceField(choices=User.AccountType.choices)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        trim_whitespace=False,
    )
    agent_profile = AgentProfileWriteSerializer(required=False)
    driver = DriverWriteSerializer(required=False, write_only=True)

    def validate_email(self, value):
        return value.strip().lower() if value else ""

    def validate(self, attrs):
        account_type = attrs["account_type"]
        person_data = attrs.get("person")
        existing_person = attrs.get("person_id")
        email = attrs.get("email", "")
        agent_data = attrs.get("agent_profile")
        driver_data = attrs.get("driver")

        if (person_data is not None) == (existing_person is not None):
            raise serializers.ValidationError(
                {
                    "person": (
                        "Fournissez soit 'person' pour créer une nouvelle personne, "
                        "soit 'person_id' pour utiliser une personne existante, "
                        "mais pas les deux."
                    )
                }
            )

        if person_data is not None:
            nif = person_data.get("nif")
            if nif:
                existing_by_nif = Person.objects.filter(
                    nif=Person.normalize_nif(nif)
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

        if existing_person and existing_person.accounts.filter(
            account_type=account_type
        ).exists():
            raise serializers.ValidationError(
                {"account_type": "Cette personne possède déjà un compte de ce type."}
            )

        if account_type == User.AccountType.PROFESSIONAL:
            self._validate_professional_account(
                email=email,
                agent_data=agent_data,
                driver_data=driver_data,
            )
        else:
            self._validate_personal_account(
                email=email,
                agent_data=agent_data,
                driver_data=driver_data,
                person=existing_person,
            )

        return attrs

    def _validate_professional_account(self, *, email, agent_data, driver_data):
        errors = {}
        if not email:
            errors["email"] = "L’adresse email est obligatoire pour un compte professionnel."
        if not agent_data:
            errors["agent_profile"] = "Le profil agent est obligatoire pour un compte professionnel."
        if driver_data:
            errors["driver"] = "Le dossier conducteur ne doit pas être fourni pour un compte professionnel."
        if email and User.objects.filter(
            account_type=User.AccountType.PROFESSIONAL,
            email__iexact=email,
        ).exists():
            errors["email"] = "Un compte professionnel utilise déjà cette adresse email."

        request = self.context["request"]
        try:
            creator_profile = request.user.agent_profile
        except AgentProfile.DoesNotExist:
            errors["creator"] = "Le compte connecté ne possède aucun profil agent actif."
        else:
            if not creator_profile.is_active:
                errors["creator"] = "Le profil agent du compte connecté est désactivé."
            elif (
                agent_data
                and creator_profile.role == AgentProfile.Role.AGENT_SAISIE
                and agent_data.get("role") == AgentProfile.Role.ADMIN
            ):
                errors["agent_profile"] = "Un agent de saisie ne peut pas créer un compte administrateur."

        if errors:
            raise serializers.ValidationError(errors)

    def _validate_personal_account(self, *, email, agent_data, driver_data, person):
        errors = {}
        if email:
            errors["email"] = "L’adresse email n’est pas utilisée pour un compte personnel."
        if agent_data:
            errors["agent_profile"] = "Un profil agent ne peut pas être associé à un compte personnel."

        if person is None:
            if not driver_data:
                errors["driver"] = "Le dossier conducteur est obligatoire pour une nouvelle personne personnelle."
        else:
            existing_driver = getattr(person, "driver_record", None)
            if existing_driver is None and not driver_data:
                errors["driver"] = "Cette personne ne possède aucun dossier conducteur; fournissez les données du dossier."
            elif existing_driver is not None and driver_data:
                errors["driver"] = "Cette personne possède déjà un dossier conducteur."

        if errors:
            raise serializers.ValidationError(errors)

    @transaction.atomic
    def create(self, validated_data):
        person_data = validated_data.pop("person", None)
        person = validated_data.pop("person_id", None)
        account_type = validated_data.pop("account_type")
        email = validated_data.pop("email", "")
        password = validated_data.pop("password")
        agent_data = validated_data.pop("agent_profile", None)
        driver_data = validated_data.pop("driver", None)

        if person is None:
            person = Person.objects.create(**person_data)

        if person.accounts.filter(account_type=account_type).exists():
            raise serializers.ValidationError(
                {"account_type": "Cette personne possède déjà un compte de ce type."}
            )

        if account_type == User.AccountType.PERSONAL:
            existing_driver = getattr(person, "driver_record", None)
            if existing_driver is None:
                Driver.objects.create(person=person, **driver_data)
            elif driver_data:
                raise serializers.ValidationError(
                    {"driver": "Cette personne possède déjà un dossier conducteur."}
                )

        user = User(
            person=person,
            account_type=account_type,
            email=email if account_type == User.AccountType.PROFESSIONAL else "",
            created_by=self.context["request"].user,
        )
        user.set_password(password)
        user.username = user.generate_internal_username()
        user.full_clean()
        user.save()

        if account_type == User.AccountType.PROFESSIONAL:
            AgentProfile.objects.create(user=user, **agent_data)

        return user

    def to_representation(self, instance):
        return UserReadSerializer(instance, context=self.context).data


class UserProfileUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=False)

    def validate_email(self, value):
        user = self.instance
        if user.account_type != User.AccountType.PROFESSIONAL:
            raise serializers.ValidationError(
                "Un compte personnel ne peut pas modifier un email de connexion."
            )

        value = value.strip().lower()
        if User.objects.filter(
            account_type=User.AccountType.PROFESSIONAL,
            email__iexact=value,
        ).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Cette adresse email est déjà utilisée.")
        return value

    def update(self, instance, validated_data):
        if "email" in validated_data:
            instance.email = validated_data["email"]
            instance.full_clean()
            instance.save(update_fields=["email"])
        return instance

    def create(self, validated_data):
        raise NotImplementedError


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Les deux nouveaux mots de passe ne correspondent pas."})
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "Le nouveau mot de passe doit etre different de l'ancien."})
        password_validation.validate_password(attrs["new_password"], self.context["request"].user)
        return attrs


class SecureTokenRefreshSerializer(SimpleJWTTokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        simple_jwt_settings = getattr(settings, "SIMPLE_JWT", {})
        user_id_claim = simple_jwt_settings.get("USER_ID_CLAIM", "user_id")
        user_id = refresh.get(user_id_claim)

        if user_id is None:
            raise AuthenticationFailed("Refresh token invalide.", code="token_not_valid")

        try:
            user = User.objects.select_related("agent_profile").get(pk=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed("Le compte associé à ce token n’existe plus.")

        if not user.is_active:
            raise AuthenticationFailed("Le compte associé à ce token est désactivé.")

        if user.account_type == User.AccountType.PROFESSIONAL:
            try:
                profile = user.agent_profile
            except AgentProfile.DoesNotExist:
                raise AuthenticationFailed(
                    "Aucun profil agent n’est associé à ce compte professionnel."
                )
            if not profile.is_active:
                raise AuthenticationFailed("Le profil agent associé est désactivé.")

        data = super().validate(attrs)
        data["account_type"] = user.account_type
        return data

