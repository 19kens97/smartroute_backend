from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api import error_response, success_response

from .models import AgentProfile, User
from .permissions import IsAdminOrAgentSaisie
from .serializers import (
    PersonalLoginSerializer,
    ProfessionalLoginSerializer,
    SecureTokenRefreshSerializer,
    UserCreateSerializer,
    UserProfileUpdateSerializer,
    UserReadSerializer,
)
from .services.token import revoke_all_user_refresh_tokens


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

    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "user": UserReadSerializer(user).data,
    }


class BaseLoginAPIView(APIView):
    permission_classes = [AllowAny]
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


@extend_schema(tags=["Authentication"], request=ProfessionalLoginSerializer)
class ProfessionalLoginAPIView(BaseLoginAPIView):
    serializer_class = ProfessionalLoginSerializer


@extend_schema(tags=["Authentication"], request=PersonalLoginSerializer)
class PersonalLoginAPIView(BaseLoginAPIView):
    serializer_class = PersonalLoginSerializer


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

    @extend_schema(responses={200: dict}, tags=["Users"])
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


class UserProfileView(generics.RetrieveAPIView):
    serializer_class = UserReadSerializer
    permission_classes = [IsAuthenticated]

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
