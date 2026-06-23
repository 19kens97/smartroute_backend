from django.db.models import Exists, OuterRef
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.services import log_action
from .filters import AlertFilter
from .models import Alert, AlertReceipt
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
            OpenApiParameter("unread", bool, description="Alertes manuelles non ouvertes par l'utilisateur."),
            OpenApiParameter("created_after", str, description="Date/heure ISO minimale."),
            OpenApiParameter("created_before", str, description="Date/heure ISO maximale."),
        ],
        responses={200: AlertSerializer(many=True), 401: OpenApiResponse(description="Authentification JWT requise.")},
    ),
    retrieve=extend_schema(summary="Consulter une alerte", responses={200: AlertSerializer, 401: OpenApiResponse(description="Authentification JWT requise."), 404: OpenApiResponse(description="Alerte introuvable.")}),
    create=extend_schema(summary="Créer une alerte manuelle", description="AGENT_SAISIE ou AGENT_TERRAIN selon le type.", responses={201: AlertSerializer, 400: OpenApiResponse(description="Données invalides."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé.")}),
    update=extend_schema(summary="Modifier une alerte manuelle", description="Permission: AGENT_SAISIE uniquement.", responses={200: AlertSerializer, 400: OpenApiResponse(description="Modification interdite ou invalide."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé.")}),
    partial_update=extend_schema(summary="Modifier partiellement une alerte manuelle", description="Permission: AGENT_SAISIE uniquement.", responses={200: AlertSerializer}),
)
class AlertViewSet(ModelViewSet):
    queryset = Alert.objects.select_related("created_by").all().order_by("-id")
    serializer_class = AlertSerializer
    permission_classes = [AlertPermission]
    pagination_class = AlertPagination
    filterset_class = AlertFilter
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_authenticated:
            opened_receipts = AlertReceipt.objects.filter(
                alert_id=OuterRef("pk"), user=user, opened_at__isnull=False
            )
            queryset = queryset.annotate(is_opened_for_user=Exists(opened_receipts))
        if self.action == "list" and self.request.query_params.get("unread", "").lower() in {"1", "true", "yes"}:
            queryset = self._unread_queryset(queryset)
        return queryset

    def _unread_queryset(self, queryset=None):
        queryset = queryset if queryset is not None else self.get_queryset()
        return queryset.filter(
            source=Alert.SOURCE_MANUAL,
            is_opened_for_user=False,
        ).exclude(created_by=self.request.user)

    def perform_create(self, serializer):
        alert = serializer.save(created_by=self.request.user, source=Alert.SOURCE_MANUAL)
        AlertReceipt.objects.create(alert=alert, user=self.request.user, opened_at=timezone.now())
        log_action(self.request.user, alert, "CREATE")

    def perform_update(self, serializer):
        alert = serializer.save()
        log_action(self.request.user, alert, "UPDATE")

    @extend_schema(
        summary="Récupérer les alertes manuelles récentes non consultées",
        responses={200: OpenApiResponse(description="Compteur total et cinq alertes maximum.")},
    )
    @action(detail=False, methods=["get"], url_path="recent-unread")
    def recent_unread(self, request):
        queryset = self._unread_queryset(self.get_queryset())
        unread_count = queryset.count()
        results = self.get_serializer(queryset[:5], many=True).data
        return api_response(True, "Alertes non consultées récupérées.", {
            "unread_count": unread_count,
            "results": results,
        })

    @extend_schema(
        summary="Marquer une alerte comme consultée pour l'utilisateur connecté",
        request=None,
        responses={200: OpenApiResponse(description="Alerte marquée comme consultée."), 404: OpenApiResponse(description="Alerte introuvable.")},
    )
    @action(detail=True, methods=["post"], url_path="mark-opened")
    def mark_opened(self, request, pk=None):
        alert = self.get_object()
        receipt, _ = AlertReceipt.objects.get_or_create(alert=alert, user=request.user)
        if receipt.opened_at is None:
            receipt.opened_at = timezone.now()
            receipt.save(update_fields=("opened_at", "updated_at"))
        return api_response(True, "Alerte marquée comme consultée.", {
            "alert_id": alert.pk,
            "is_opened": True,
            "opened_at": receipt.opened_at,
        }, status_code=status.HTTP_200_OK)
