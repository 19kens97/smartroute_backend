from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import User


PASSWORD_RESET_PUBLIC_MESSAGE = (
    "Si un compte correspondant existe, les instructions de reinitialisation seront envoyees."
)
PASSWORD_RESET_EMAIL_SENT_MESSAGE = "Les instructions de reinitialisation ont ete envoyees."
PASSWORD_RESET_EMAIL_NOT_FOUND_MESSAGE = "Aucun compte n'est associe a ce mail."
PASSWORD_RESET_SUCCESS_MESSAGE = "Mot de passe reinitialise avec succes."
PASSWORD_RESET_INVALID_LINK_MESSAGE = (
    "Ce lien de reinitialisation n'est plus valide. Demandez un nouveau lien."
)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()

    def get_eligible_user(self):
        if not self.is_valid():
            return None
        email = self.validated_data["email"]
        return (
            User.objects.filter(
                account_type=User.AccountType.PROFESSIONAL,
                email__iexact=email,
                is_active=True,
            )
            .select_related("person", "agent_profile")
            .first()
        )


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        "invalid_link": PASSWORD_RESET_INVALID_LINK_MESSAGE,
    }

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Les deux nouveaux mots de passe ne correspondent pas."}
            )

        user = self._get_user(attrs["uid"])
        if (
            user is None
            or not user.is_active
            or user.account_type != User.AccountType.PROFESSIONAL
            or not default_token_generator.check_token(user, attrs["token"])
        ):
            raise serializers.ValidationError({"token": self.error_messages["invalid_link"]})

        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs

    def _get_user(self, uid):
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            return User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None
