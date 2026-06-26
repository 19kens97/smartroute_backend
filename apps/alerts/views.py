import logging
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.services import log_action
from .filters import AlertFilter
from .models import Alert, AlertReceipt
from .pagination import AlertPagination
from .permissions import AlertPermission
from .realtime import broadcast_alert_created
from .serializers import AlertListSerializer, AlertSerializer

logger = logging.getLogger(__name__)


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
    create=extend_schema(summary="Créer une alerte manuelle", description="AGENT_SAISIE ou AGENT_TERRAIN selon le type. Accepte JSON ou multipart/form-data avec une preuve audio/vidéo optionnelle.", responses={201: AlertSerializer, 400: OpenApiResponse(description="Données invalides."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé.")}),
    update=extend_schema(summary="Modifier une alerte manuelle", description="Permission: AGENT_SAISIE uniquement.", responses={200: AlertSerializer, 400: OpenApiResponse(description="Modification interdite ou invalide."), 401: OpenApiResponse(description="Authentification JWT requise."), 403: OpenApiResponse(description="Rôle non autorisé.")}),
    partial_update=extend_schema(summary="Modifier partiellement une alerte manuelle", description="Permission: AGENT_SAISIE uniquement.", responses={200: AlertSerializer}),
)
class AlertViewSet(ModelViewSet):
    queryset = Alert.objects.select_related("created_by").prefetch_related("evidence").all().order_by("-created_at", "-id")
    serializer_class = AlertSerializer
    permission_classes = [AlertPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = AlertPagination
    filterset_class = AlertFilter
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return AlertListSerializer
        return AlertSerializer

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
        evidence_file_names = []
        try:
            with transaction.atomic():
                alert = serializer.save(created_by=self.request.user, source=Alert.SOURCE_MANUAL)
                evidence_file_names = [item.file.name for item in alert.evidence.all() if item.file]
                AlertReceipt.objects.create(alert=alert, user=self.request.user, opened_at=timezone.now())
                log_action(self.request.user, alert, "CREATE")
                transaction.on_commit(
                    lambda alert_id=alert.pk: broadcast_alert_created(
                        Alert.objects.select_related("created_by").get(pk=alert_id)
                    )
                )
        except Exception:
            storage = None
            for file_name in evidence_file_names:
                if not storage:
                    from .models import private_alert_evidence_storage
                    storage = private_alert_evidence_storage
                if storage.exists(file_name):
                    storage.delete(file_name)
            raise

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

    @extend_schema(
        summary="Lire une preuve audio ou vidéo d'alerte",
        responses={200: OpenApiResponse(description="Flux média protégé."), 401: OpenApiResponse(description="Authentification JWT requise."), 404: OpenApiResponse(description="Preuve introuvable.")},
    )
    @action(detail=True, methods=["get"], url_path=r"evidence/(?P<evidence_pk>[^/.]+)")
    def evidence(self, request, pk=None, evidence_pk=None):
        alert = self.get_object()
        evidence = alert.evidence.filter(pk=evidence_pk).first()
        if evidence is None or not evidence.file:
            raise Http404
        response = FileResponse(evidence.file.open("rb"), content_type=evidence.mime_type or "application/octet-stream")
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = f'inline; filename="alert-evidence-{evidence.pk}"'
        return response

