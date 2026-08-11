import hashlib
import json
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image, ImageDraw
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api import error_response, success_response
from apps.core.openapi import ApiEnvelopeSerializer, AuthEnvelopeSerializer, EmptyEnvelopeSerializer, SignatureEnvelopeSerializer
from apps.media_storage.services import scan_file_for_virus

from .models import AgentProfile, User
from .permissions import IsAdminOrAgentSaisie
from .serializers import (
    ChangePasswordSerializer,
    MobileLoginSerializer,
    PersonalLoginSerializer,
    ProfessionalLoginSerializer,
    SecureTokenRefreshSerializer,
    UserCreateSerializer,
    UserProfileUpdateSerializer,
    UserReadSerializer,
)
from .serializers_password_reset import (
    ForgotPasswordSerializer,
    PASSWORD_RESET_EMAIL_NOT_FOUND_MESSAGE,
    PASSWORD_RESET_EMAIL_SENT_MESSAGE,
    PASSWORD_RESET_PUBLIC_MESSAGE,
    PASSWORD_RESET_SUCCESS_MESSAGE,
    ResetPasswordSerializer,
)
from .services.token import revoke_all_user_refresh_tokens
from .throttles import ForgotPasswordThrottle, LoginIdentifierRateThrottle, LoginIpRateThrottle, ResetPasswordThrottle


def build_auth_payload(user):
    if not user.is_active:
        raise AuthenticationFailed("Ce compte est désactivé.")

    if user.account_type == User.AccountType.PROFESSIONAL:
        try:
            profile = user.agent_profile
        except AgentProfile.DoesNotExist:
            raise AuthenticationFailed(
                "Aucun profil agent n’est associé à ce compte."
            )
        if not profile.is_active:
            raise AuthenticationFailed("Le profil agent est désactivé.")

    refresh = RefreshToken.for_user(user)
    refresh["account_type"] = user.account_type
    if user.account_type == User.AccountType.PROFESSIONAL:
        refresh["role"] = user.agent_profile.role

    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "user": UserReadSerializer(user).data,
    }



def build_password_reset_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    separator = "&" if "?" in settings.PASSWORD_RESET_MOBILE_URL else "?"
    return f"{settings.PASSWORD_RESET_MOBILE_URL}{separator}{urlencode({'uid': uid, 'token': token})}"


def send_password_reset_email(user):
    reset_link = build_password_reset_link(user)
    context = {
        "user": user,
        "reset_link": reset_link,
        "timeout_minutes": max(1, int(settings.PASSWORD_RESET_TIMEOUT / 60)),
    }
    subject = "SmartRoute - Reinitialisation du mot de passe"
    text_body = render_to_string("accounts/password_reset_email.txt", context)
    html_body = render_to_string("accounts/password_reset_email.html", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)

class BaseLoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginIpRateThrottle, LoginIdentifierRateThrottle]
    serializer_class = None

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return success_response(
            message="Connexion réussie",
            data=build_auth_payload(user),
        )


@extend_schema(tags=["Authentication"], request=ProfessionalLoginSerializer, responses={200: AuthEnvelopeSerializer})
class ProfessionalLoginAPIView(BaseLoginAPIView):
    serializer_class = ProfessionalLoginSerializer


@extend_schema(tags=["Authentication"], request=PersonalLoginSerializer, responses={200: AuthEnvelopeSerializer})
class PersonalLoginAPIView(BaseLoginAPIView):
    serializer_class = PersonalLoginSerializer


MOBILE_AUTH_REQUIRED_MESSAGE = "Seuls les agents de terrain actifs peuvent acceder a l'application mobile SmartRoute."
MOBILE_INACTIVE_MESSAGE = "Ce compte est inactif ou suspendu. Contactez un administrateur."
INVALID_CREDENTIALS_MESSAGE = "Identifiants incorrects."


def mobile_access_error(user):
    if not user.is_active:
        return MOBILE_INACTIVE_MESSAGE
    if user.account_type != User.AccountType.PROFESSIONAL:
        return MOBILE_AUTH_REQUIRED_MESSAGE
    try:
        profile = user.agent_profile
    except AgentProfile.DoesNotExist:
        return MOBILE_AUTH_REQUIRED_MESSAGE
    if not profile.is_active:
        return MOBILE_INACTIVE_MESSAGE
    if profile.role != AgentProfile.Role.AGENT_TERRAIN:
        return MOBILE_AUTH_REQUIRED_MESSAGE
    return None


@extend_schema(tags=["Authentication"], request=MobileLoginSerializer, responses={200: AuthEnvelopeSerializer})
class MobileLoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginIpRateThrottle, LoginIdentifierRateThrottle]

    def post(self, request):
        serializer = MobileLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message=INVALID_CREDENTIALS_MESSAGE,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        try:
            user = User.objects.select_related("agent_profile", "person").get(
                email__iexact=email,
                account_type=User.AccountType.PROFESSIONAL,
            )
        except User.DoesNotExist:
            return error_response(
                message=INVALID_CREDENTIALS_MESSAGE,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.check_password(password):
            return error_response(
                message=INVALID_CREDENTIALS_MESSAGE,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        access_error = mobile_access_error(user)
        if access_error:
            return error_response(
                message=access_error,
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return success_response(
            message="Connexion mobile reussie",
            data=build_auth_payload(user),
        )


class MobileTokenRefreshView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SecureTokenRefreshSerializer,
        responses={200: dict},
        tags=["Authentication"],
    )
    def post(self, request):
        raw_refresh = request.data.get("refresh")
        try:
            refresh = RefreshToken(raw_refresh)
            user_id = refresh.get("user_id")
            user = User.objects.select_related("agent_profile").get(pk=user_id)
        except (TokenError, TypeError, User.DoesNotExist):
            raise AuthenticationFailed("Refresh token invalide.")

        access_error = mobile_access_error(user)
        if access_error:
            return error_response(
                message=access_error,
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = SecureTokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        response_data = {
            "access_token": data["access"],
            "account_type": data["account_type"],
            "role": user.agent_profile.role,
        }
        if "refresh" in data:
            response_data["refresh_token"] = data["refresh"]

        return success_response(
            message="Tokens mobiles renouveles avec succes",
            data=response_data,
        )


class CustomTokenView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SecureTokenRefreshSerializer,
        responses={200: dict},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = SecureTokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        response_data = {
            "access_token": data["access"],
            "account_type": data["account_type"],
        }
        if "refresh" in data:
            response_data["refresh_token"] = data["refresh"]

        return success_response(
            message="Tokens renouvelés avec succès",
            data=response_data,
        )



@extend_schema(tags=["Authentication"], request=ForgotPasswordSerializer, responses={200: EmptyEnvelopeSerializer})
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ForgotPasswordThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.get_eligible_user()
        if user is not None:
            send_password_reset_email(user)
            return success_response(
                message=PASSWORD_RESET_EMAIL_SENT_MESSAGE,
                data={"email_found": True},
            )
        return success_response(
            message=PASSWORD_RESET_EMAIL_NOT_FOUND_MESSAGE,
            data={"email_found": False},
        )


@extend_schema(tags=["Authentication"], request=ResetPasswordSerializer, responses={200: ApiEnvelopeSerializer})
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ResetPasswordThrottle]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        revoked_tokens = revoke_all_user_refresh_tokens(user)
        return success_response(
            message=PASSWORD_RESET_SUCCESS_MESSAGE,
            data={"revoked_refresh_tokens": revoked_tokens},
        )

class UserListView(generics.ListAPIView):
    serializer_class = UserReadSerializer
    permission_classes = [IsAuthenticated, IsAdminOrAgentSaisie]

    def get_queryset(self):
        return User.objects.select_related(
            "person",
            "person__driver_record",
            "agent_profile",
        ).order_by("id")


class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserReadSerializer
    permission_classes = [IsAuthenticated, IsAdminOrAgentSaisie]

    def get_queryset(self):
        return User.objects.select_related(
            "person",
            "person__driver_record",
            "agent_profile",
        )


class UserCreateAPIView(generics.CreateAPIView):
    serializer_class = UserCreateSerializer
    permission_classes = [IsAuthenticated, IsAdminOrAgentSaisie]


class UserDeactivateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAgentSaisie]

    @extend_schema(request=None, responses={200: ApiEnvelopeSerializer}, tags=["Users"])
    def patch(self, request, pk):
        target = get_object_or_404(
            User.objects.select_related("person", "agent_profile"),
            pk=pk,
        )

        if target.pk == request.user.pk:
            return error_response(
                message="Vous ne pouvez pas désactiver votre propre compte.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        creator_profile = request.user.agent_profile
        target_profile = getattr(target, "agent_profile", None)
        if (
            creator_profile.role == AgentProfile.Role.AGENT_SAISIE
            and target_profile is not None
            and target_profile.role == AgentProfile.Role.ADMIN
        ):
            return error_response(
                message="Un agent de saisie ne peut pas désactiver un administrateur.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not target.is_active:
            return success_response(
                message="Ce compte est déjà désactivé",
                data=UserReadSerializer(target).data,
            )

        target.is_active = False
        target.save(update_fields=["is_active"])
        revoked_tokens = revoke_all_user_refresh_tokens(target)

        return success_response(
            message="Compte désactivé avec succès",
            data={
                "user": UserReadSerializer(target).data,
                "revoked_refresh_tokens": revoked_tokens,
            },
        )


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserReadSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return UserProfileUpdateSerializer
        return UserReadSerializer

    def get_object(self):
        return User.objects.select_related(
            "person",
            "person__driver_record",
            "agent_profile",
        ).get(pk=self.request.user.pk)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(
            message="Profil utilisateur récupéré",
            data=serializer.data,
        )


class UserProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=UserProfileUpdateSerializer,
        responses={200: UserReadSerializer},
        tags=["Users"],
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(
            message="Profil mis à jour avec succès",
            data=UserReadSerializer(request.user).data,
        )



class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses={200: EmptyEnvelopeSerializer}, tags=["auth"])
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return success_response(message="Mot de passe modifie avec succes", data={})


class AgentSignatureView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    max_signature_size = 1024 * 1024

    def _profile(self, request):
        try:
            profile = request.user.agent_profile
        except AgentProfile.DoesNotExist:
            return None
        return profile if profile.is_active else None

    def _payload(self, profile):
        return {
            "has_signature": bool(profile and profile.signature_file),
            "signature_updated_at": profile.signature_updated_at.isoformat() if profile and profile.signature_updated_at else None,
        }

    @extend_schema(responses={200: SignatureEnvelopeSerializer}, tags=["auth"])
    def get(self, request):
        profile = self._profile(request)
        if profile is None:
            return error_response("Profil agent requis.", {"profile": "AGENT_PROFILE_REQUIRED"}, status.HTTP_403_FORBIDDEN)
        return success_response("Statut signature", self._payload(profile))

    @extend_schema(request=ApiEnvelopeSerializer, responses={200: SignatureEnvelopeSerializer}, tags=["auth"])
    def put(self, request):
        profile = self._profile(request)
        if profile is None:
            return error_response("Profil agent requis.", {"profile": "AGENT_PROFILE_REQUIRED"}, status.HTTP_403_FORBIDDEN)
        uploaded = request.FILES.get("signature")
        payload = request.data.get("signature_payload")
        if uploaded is None and not payload:
            return error_response("Signature requise.", {"signature": "MISSING_SIGNATURE"}, status.HTTP_400_BAD_REQUEST)
        content = self._validate_uploaded_signature(uploaded) if uploaded is not None else self._render_signature_payload(payload)
        if isinstance(content, Response):
            return content
        old_name = profile.signature_file.name if profile.signature_file else ""
        if old_name and profile.signature_file.storage.exists(old_name):
            profile.signature_file.storage.delete(old_name)
        profile.signature_file.save("signature.png", ContentFile(content), save=False)
        profile.signature_sha256 = hashlib.sha256(content).hexdigest()
        profile.signature_updated_at = timezone.now()
        profile.save(update_fields=["signature_file", "signature_sha256", "signature_updated_at", "updated_at"])
        return success_response("Signature enregistree", self._payload(profile))

    @extend_schema(responses={200: SignatureEnvelopeSerializer}, tags=["auth"])
    def delete(self, request):
        profile = self._profile(request)
        if profile is None:
            return error_response("Profil agent requis.", {"profile": "AGENT_PROFILE_REQUIRED"}, status.HTTP_403_FORBIDDEN)
        if profile.signature_file:
            profile.signature_file.delete(save=False)
        profile.signature_file = None
        profile.signature_sha256 = ""
        profile.signature_updated_at = None
        profile.save(update_fields=["signature_file", "signature_sha256", "signature_updated_at", "updated_at"])
        return success_response("Signature supprimee", self._payload(profile))

    def _validate_uploaded_signature(self, uploaded):
        if uploaded.size > self.max_signature_size:
            return error_response("Fichier trop volumineux.", {"signature": "FILE_TOO_LARGE"}, status.HTTP_400_BAD_REQUEST)
        try:
            image = Image.open(uploaded)
            image.verify()
            uploaded.seek(0)
            image = Image.open(uploaded).convert("RGBA")
        except Exception:
            return error_response("Image invalide.", {"signature": "INVALID_IMAGE"}, status.HTTP_400_BAD_REQUEST)
        if not image.getbbox():
            return error_response("Signature vide.", {"signature": "EMPTY_SIGNATURE"}, status.HTTP_400_BAD_REQUEST)
        try:
            scan_file_for_virus(uploaded)
        except serializers.ValidationError:
            return error_response("Le fichier ne peut pas etre verifie actuellement.", {"signature": "SECURITY_SCAN_FAILED"}, status.HTTP_400_BAD_REQUEST)
        from io import BytesIO
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _render_signature_payload(self, payload):
        try:
            data = json.loads(payload)
            width = int(data.get("canvasWidth") or 240)
            height = int(data.get("canvasHeight") or 120)
            strokes = data.get("strokes") or []
        except (TypeError, ValueError, json.JSONDecodeError):
            return error_response("Signature invalide.", {"signature": "INVALID_SIGNATURE_PAYLOAD"}, status.HTTP_400_BAD_REQUEST)
        image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        for stroke in strokes:
            points = [(float(point["x"]), float(point["y"])) for point in stroke if "x" in point and "y" in point]
            if len(points) > 1:
                draw.line(points, fill=(7, 20, 45, 255), width=4)
        if not image.getbbox():
            return error_response("Signature vide.", {"signature": "EMPTY_SIGNATURE"}, status.HTTP_400_BAD_REQUEST)
        from io import BytesIO
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
        try:
            scan_file_for_virus(ContentFile(content, name="signature.png"))
        except serializers.ValidationError:
            return error_response("Le fichier ne peut pas etre verifie actuellement.", {"signature": "SECURITY_SCAN_FAILED"}, status.HTTP_400_BAD_REQUEST)
        return content

