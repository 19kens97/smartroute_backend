from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or obj.username

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "badge_number",
            "phone",
            "precinct",
            "post",
            "nif",
        )


class ProfileUpdateSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False, allow_blank=False, max_length=30)
    email = serializers.EmailField(required=False, allow_blank=False, max_length=254)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Aucun champ modifiable fourni.")
        return attrs

    def validate_phone(self, value):
        normalized = "".join(str(value).strip().replace("-", " ").split())
        if normalized.startswith("+"):
            digits = normalized[1:]
            prefix = "+"
        else:
            digits = normalized
            prefix = ""
        if not digits.isdigit():
            raise serializers.ValidationError("Le numero de telephone n'est pas valide.")
        if prefix == "+" and not digits.startswith("509"):
            raise serializers.ValidationError("Le numero de telephone doit utiliser l'indicatif +509.")
        if digits.startswith("509"):
            local = digits[3:]
        else:
            local = digits
        if len(local) != 8:
            raise serializers.ValidationError("Le numero de telephone doit contenir 8 chiffres locaux.")
        return f"+509{local}"

    def validate_email(self, value):
        normalized = str(value).strip().lower()
        try:
            validate_email(normalized)
        except DjangoValidationError:
            raise serializers.ValidationError("L'adresse e-mail n'est pas valide.") from None
        user = self.context["request"].user
        if User.objects.exclude(pk=user.pk).filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("Cette adresse e-mail est deja utilisee.")
        return normalized

    def update(self, instance, validated_data):
        update_fields = []
        for field in ("phone", "email"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
                update_fields.append(field)
        if update_fields:
            instance.save(update_fields=update_fields)
        return instance


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("L'ancien mot de passe est incorrect.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")
        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": ["Les deux nouveaux mots de passe ne correspondent pas."]})
        if user.check_password(new_password):
            raise serializers.ValidationError({"new_password": ["Le nouveau mot de passe doit etre different de l'ancien."]})
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from None
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
