from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.services import log_action

from .models import (
    Vehicle,
    normalize_plate_number,
    plate_number_lookup_variants,
)
from .permissions import VehiclePermission
from .serializers import (
    VehicleReadSerializer,
    VehicleWriteSerializer,
)


class VehiclePagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="Lister les véhicules",
        description=(
            "Lecture réservée aux comptes professionnels actifs "
            "ADMIN, AGENT_TERRAIN ou AGENT_SAISIE."
        ),
        responses={
            200: VehicleReadSerializer(many=True),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
        },
    ),
    retrieve=extend_schema(
        summary="Consulter un véhicule",
        responses={
            200: VehicleReadSerializer,
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
            404: OpenApiResponse(
                description="Véhicule introuvable."
            ),
        },
    ),
    create=extend_schema(
        summary="Créer un véhicule",
        description="Permission : AGENT_SAISIE uniquement.",
        request=VehicleWriteSerializer,
        responses={
            201: VehicleReadSerializer,
            400: OpenApiResponse(
                description="Données invalides."
            ),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Seul un agent de saisie est autorisé."
            ),
        },
    ),
    partial_update=extend_schema(
        summary="Modifier partiellement un véhicule",
        description=(
            "Permission : AGENT_SAISIE uniquement. "
            "PUT et DELETE ne sont pas disponibles."
        ),
        request=VehicleWriteSerializer,
        responses={
            200: VehicleReadSerializer,
            400: OpenApiResponse(
                description="Données invalides."
            ),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Seul un agent de saisie est autorisé."
            ),
            404: OpenApiResponse(
                description="Véhicule introuvable."
            ),
        },
    ),
)
class VehicleViewSet(ModelViewSet):
    permission_classes = [VehiclePermission]
    pagination_class = VehiclePagination
    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    filterset_fields = (
        "plate_number",
        "owner",
        "is_wanted",
        "brand",
        "model",
    )
    search_fields = (
        "plate_number",
        "brand",
        "model",
        "engine_number",
        "owner__person__first_name",
        "owner__person__last_name",
        "owner__person__nif",
    )

    def get_queryset(self):
        return (
            Vehicle.objects
            .select_related("owner", "owner__person")
            .order_by("-created_at", "-id")
        )

    def get_serializer_class(self):
        if self.action in {
            "create",
            "partial_update",
        }:
            return VehicleWriteSerializer

        return VehicleReadSerializer

    def perform_create(self, serializer):
        vehicle = serializer.save()
        log_action(
            self.request.user,
            vehicle,
            "CREATE",
        )

    def perform_update(self, serializer):
        vehicle = serializer.save()
        log_action(
            self.request.user,
            vehicle,
            "UPDATE",
        )

    @extend_schema(
        summary="Rechercher exactement un véhicule par plaque",
        description=(
            "Normalise les espaces, les tirets et la casse avant "
            "d'effectuer une recherche exacte."
        ),
        parameters=[
            OpenApiParameter(
                name="plate_number",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            )
        ],
        responses={
            200: VehicleReadSerializer,
            400: OpenApiResponse(
                description="Plaque vide ou invalide."
            ),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
            404: OpenApiResponse(
                description="Véhicule introuvable."
            ),
        },
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"by-plate/(?P<plate_number>[^/]+)",
    )
    def by_plate(self, request, plate_number=None):
        normalized = normalize_plate_number(
            plate_number
        )

        max_length = Vehicle._meta.get_field(
            "plate_number"
        ).max_length

        if (
            not normalized
            or len(normalized) > max_length
        ):
            return api_response(
                False,
                "Numéro d'immatriculation invalide.",
                {},
                {
                    "plate_number": [
                        (
                            "La plaque est obligatoire et ne peut "
                            f"pas dépasser {max_length} caractères."
                        )
                    ]
                },
                status.HTTP_400_BAD_REQUEST,
            )

        lookup = Q()

        for variant in plate_number_lookup_variants(
            normalized
        ):
            lookup |= Q(
                plate_number__iexact=variant
            )

        vehicle = get_object_or_404(
            self.get_queryset(),
            lookup,
        )

        return api_response(
            True,
            "Véhicule trouvé.",
            VehicleReadSerializer(
                vehicle,
                context={"request": request},
            ).data,
        )
