from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsAdminOrEntryAgentRole, IsEntryAgentRole
from apps.core.api import api_response
from apps.core.services import log_action

from .models import Vehicle, normalize_plate_number
from .serializers import VehicleSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les vehicules", responses={200: VehicleSerializer(many=True), 401: OpenApiResponse(description="Authentification JWT requise.")}),
    retrieve=extend_schema(summary="Consulter un vehicule", responses={200: VehicleSerializer, 401: OpenApiResponse(description="Authentification JWT requise."), 404: OpenApiResponse(description="Vehicule introuvable.")}),
    create=extend_schema(summary="Creer un vehicule", description="Permission: AGENT_SAISIE uniquement.", responses={201: VehicleSerializer, 400: OpenApiResponse(description="Donnees invalides."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Role non autorise.")}),
    update=extend_schema(summary="Modifier un vehicule", description="Permission: ADMIN ou AGENT_SAISIE.", responses={200: VehicleSerializer, 400: OpenApiResponse(description="Donnees invalides."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Role non autorise."), 404: OpenApiResponse(description="Vehicule introuvable.")}),
    partial_update=extend_schema(summary="Modifier partiellement un vehicule", description="Permission: ADMIN ou AGENT_SAISIE.", responses={200: VehicleSerializer, 400: OpenApiResponse(description="Donnees invalides."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Role non autorise."), 404: OpenApiResponse(description="Vehicule introuvable.")}),
)
class VehicleViewSet(ModelViewSet):
    queryset = Vehicle.objects.select_related("owner").all().order_by("-id")
    serializer_class = VehicleSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    filterset_fields = ("plate_number", "is_wanted")
    search_fields = ("plate_number", "brand", "model")

    def get_permissions(self):
        if self.action == "create":
            permission_classes = [IsEntryAgentRole]
        elif self.action in {"update", "partial_update"}:
            permission_classes = [IsAdminOrEntryAgentRole]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(self.request.user, obj, "CREATE")

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(self.request.user, obj, "UPDATE")

    @extend_schema(
        summary="Rechercher exactement un vehicule par plaque",
        description="Normalise les espaces et la casse, puis effectue une recherche exacte insensible a la casse.",
        parameters=[OpenApiParameter(name="plate_number", required=True, type=str, location=OpenApiParameter.PATH)],
        responses={200: VehicleSerializer, 400: OpenApiResponse(description="Plaque vide ou invalide."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Acces refuse."), 404: OpenApiResponse(description="Vehicule introuvable.")},
    )
    @action(detail=False, methods=["get"], url_path=r"by-plate/(?P<plate_number>[^/]+)")
    def by_plate(self, request, plate_number=None):
        normalized = normalize_plate_number(plate_number)
        if not normalized or len(normalized) > Vehicle._meta.get_field("plate_number").max_length:
            return api_response(False, "Numero d'immatriculation invalide.", {}, {"plate_number": ["La plaque est requise et ne peut pas depasser 20 caracteres."]}, status.HTTP_400_BAD_REQUEST)
        vehicle = get_object_or_404(self.get_queryset(), plate_number__iexact=normalized)
        return api_response(True, "Vehicule trouve.", self.get_serializer(vehicle).data)
