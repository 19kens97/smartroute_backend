from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.viewsets import ModelViewSet

from apps.core.services import log_action
from .filters import AlertFilter
from .models import Alert
from .pagination import AlertPagination
from .permissions import AlertPermission
from .serializers import AlertSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Lister les alertes",
        parameters=[
            OpenApiParameter("alert_type", str, description="Code du type d'alerte."),
            OpenApiParameter("plate_number", str, description="Recherche exacte insensible à la casse."),
            OpenApiParameter("created_by", int, description="Identifiant du créateur."),
            OpenApiParameter("source", str, description="MANUAL ou SYSTEM."),
            OpenApiParameter("created_after", str, description="Date/heure ISO minimale."),
            OpenApiParameter("created_before", str, description="Date/heure ISO maximale."),
        ],
        responses={200: AlertSerializer(many=True), 401: OpenApiResponse(description="Authentification JWT requise.")},
    ),
    retrieve=extend_schema(summary="Consulter une alerte", responses={200: AlertSerializer, 401: OpenApiResponse(description="Authentification JWT requise."), 404: OpenApiResponse(description="Alerte introuvable.")}),
    create=extend_schema(summary="Créer une alerte manuelle", description="AGENT_SAISIE ou AGENT_TERRAIN selon le type. JUDICIAL_ALERT est toujours interdit.", responses={201: AlertSerializer, 400: OpenApiResponse(description="Données invalides."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé.")}),
    update=extend_schema(summary="Modifier une alerte manuelle", description="AGENT_SAISIE uniquement. Le type, l'origine et l'auteur sont immuables.", responses={200: AlertSerializer, 400: OpenApiResponse(description="Modification interdite ou invalide."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé."), 404: OpenApiResponse(description="Alerte introuvable.")}),
    partial_update=extend_schema(summary="Modifier partiellement une alerte manuelle", description="AGENT_SAISIE uniquement.", responses={200: AlertSerializer, 400: OpenApiResponse(description="Modification interdite ou invalide."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé."), 404: OpenApiResponse(description="Alerte introuvable.")}),
)
class AlertViewSet(ModelViewSet):
    queryset = Alert.objects.select_related("created_by").all().order_by("-id")
    serializer_class = AlertSerializer
    permission_classes = [AlertPermission]
    pagination_class = AlertPagination
    filterset_class = AlertFilter
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def perform_create(self, serializer):
        alert = serializer.save(created_by=self.request.user, source=Alert.SOURCE_MANUAL)
        log_action(self.request.user, alert, "CREATE")

    def perform_update(self, serializer):
        alert = serializer.save()
        log_action(self.request.user, alert, "UPDATE")