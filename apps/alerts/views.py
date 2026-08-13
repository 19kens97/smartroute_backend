from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.services import log_action

from .filters import AlertFilter
from .models import Alert, AlertReceipt
from .pagination import AlertPagination
from .permissions import AlertPermission
from .realtime import broadcast_alert_created
from .serializers import (
    AlertCloseSerializer,
    AlertListSerializer,
    AlertSerializer,
)
from .services import expire_field_alerts
from .taxonomy import alert_options_payload


class AlertViewSet(ModelViewSet):
    permission_classes = [AlertPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = AlertPagination
    filterset_class = AlertFilter
    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    def get_queryset(self):
        expire_field_alerts()

        queryset = Alert.objects.select_related(
            "created_by",
            "created_by__person",
            "vehicle",
            "subject_person",
            "resolved_by",
            "resolved_by__person",
        )

        if self.action != "list":
            queryset = queryset.prefetch_related("evidence")

        if self.request.user.is_authenticated:
            opened = AlertReceipt.objects.filter(
                alert_id=OuterRef("pk"),
                user=self.request.user,
                opened_at__isnull=False,
            )
            queryset = queryset.annotate(
                is_opened_for_user=Exists(opened)
            )

        queryset = queryset.order_by("-created_at", "-id")

        if self.request.user.is_authenticated:
            queryset = queryset.filter(
                Q(category=Alert.Category.AUTOMATIC, created_by__isnull=True)
                | Q(category=Alert.Category.AUTOMATIC, created_by=self.request.user)
                | ~Q(category=Alert.Category.AUTOMATIC)
            )

        # private automatic alerts stay visible only to the agent who triggered them

        if (
            self.action == "list"
            and self.request.query_params.get(
                "unread",
                "",
            ).lower() in {"1", "true", "yes"}
        ):
            queryset = self._unread_queryset(queryset)

        return queryset

    def get_serializer_class(self):
        if self.action in {"list", "recent_unread"}:
            return AlertListSerializer

        if self.action in {"resolve", "cancel"}:
            return AlertCloseSerializer

        return AlertSerializer

    def _unread_queryset(self, queryset):
        return (
            queryset
            .filter(is_opened_for_user=False)
            .exclude(created_by=self.request.user)
        )

    def perform_create(self, serializer):
        evidence_names = []

        try:
            with transaction.atomic():
                category = serializer.validated_data["category"]
                alert_type = serializer.validated_data["alert_type"]

                if category == Alert.Category.FIELD_REPORT:
                    severity = (
                        Alert.Severity.WARNING
                        if alert_type
                        in {
                            Alert.AlertType.TRAFFIC,
                            Alert.AlertType.ROAD_CONDITION,
                            Alert.AlertType.DANGEROUS_CONDITION,
                        }
                        else Alert.Severity.CRITICAL
                    )
                else:
                    severity = Alert.Severity.CRITICAL

                alert = serializer.save(
                    created_by=self.request.user,
                    source=Alert.Source.MANUAL,
                    severity=severity,
                    status=Alert.Status.ACTIVE,
                )

                evidence_names = [
                    item.file.name
                    for item in alert.evidence.all()
                    if item.file
                ]

                AlertReceipt.objects.create(
                    alert=alert,
                    user=self.request.user,
                    opened_at=timezone.now(),
                )

                log_action(
                    self.request.user,
                    alert,
                    "CREATE",
                    {"category": category},
                )

                transaction.on_commit(
                    lambda alert_id=alert.pk: broadcast_alert_created(
                        Alert.objects.select_related(
                            "created_by",
                            "created_by__person",
                        ).get(pk=alert_id)
                    )
                )
        except Exception:
            from .models import private_alert_evidence_storage

            for file_name in evidence_names:
                if private_alert_evidence_storage.exists(file_name):
                    private_alert_evidence_storage.delete(file_name)

            raise

    def perform_update(self, serializer):
        alert = serializer.save()
        log_action(
            self.request.user,
            alert,
            "UPDATE",
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="options",
    )
    def options(self, request):
        return api_response(
            True,
            "Options d'alertes recuperees.",
            alert_options_payload(),
            status_code=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="recent-unread",
    )
    def recent_unread(self, request):
        queryset = self._unread_queryset(self.get_queryset())
        unread_count = queryset.count()

        results = AlertListSerializer(
            queryset[:5],
            many=True,
            context={"request": request},
        ).data

        return api_response(
            True,
            "Alertes non consultées récupérées.",
            {
                "unread_count": unread_count,
                "results": results,
            },
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="mark-opened",
    )
    def mark_opened(self, request, pk=None):
        alert = self.get_object()

        receipt, _ = AlertReceipt.objects.get_or_create(
            alert=alert,
            user=request.user,
        )

        if receipt.opened_at is None:
            receipt.opened_at = timezone.now()
            receipt.save(
                update_fields=(
                    "opened_at",
                    "updated_at",
                )
            )

        return api_response(
            True,
            "Alerte marquée comme consultée.",
            {
                "alert_id": alert.pk,
                "is_opened": True,
                "opened_at": receipt.opened_at,
            },
            status_code=status.HTTP_200_OK,
        )

    def _close_alert(self, *, request, alert, target_status, action_name):
        if alert.category == Alert.Category.AUTOMATIC:
            return api_response(
                False,
                "Une alerte automatique est gérée par le système.",
                {},
                {
                    "status": [
                        "Cette alerte ne peut pas être clôturée manuellement."
                    ]
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if alert.is_terminal:
            return api_response(
                False,
                "Cette alerte est déjà clôturée.",
                {},
                {
                    "status": [
                        f"Statut actuel : {alert.status}."
                    ]
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AlertCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        alert.status = target_status
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.resolution_note = serializer.validated_data["note"]
        alert.save(
            update_fields=(
                "status",
                "resolved_at",
                "resolved_by",
                "resolution_note",
                "updated_at",
            )
        )

        log_action(
            request.user,
            alert,
            action_name,
            {"note": alert.resolution_note},
        )

        return api_response(
            True,
            "Alerte clôturée avec succès.",
            AlertSerializer(
                alert,
                context={"request": request},
            ).data,
            status_code=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="resolve",
    )
    def resolve(self, request, pk=None):
        return self._close_alert(
            request=request,
            alert=self.get_object(),
            target_status=Alert.Status.RESOLVED,
            action_name="RESOLVE",
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="cancel",
    )
    def cancel(self, request, pk=None):
        return self._close_alert(
            request=request,
            alert=self.get_object(),
            target_status=Alert.Status.CANCELLED,
            action_name="CANCEL",
        )

    @extend_schema(parameters=[OpenApiParameter("evidence_pk", OpenApiTypes.INT, OpenApiParameter.PATH)], responses={200: OpenApiResponse(response=OpenApiTypes.BINARY, description="Fichier de preuve")})
    @action(
        detail=True,
        methods=["get"],
        url_path=r"evidence/(?P<evidence_pk>[^/.]+)",
    )
    def evidence(self, request, pk=None, evidence_pk=None):
        alert = self.get_object()

        evidence = alert.evidence.filter(
            pk=evidence_pk
        ).first()

        if evidence is None or not evidence.file:
            raise Http404

        try:
            evidence.file.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404

        response = FileResponse(
            evidence.file,
            content_type=(
                evidence.mime_type
                or "application/octet-stream"
            ),
        )
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = (
            f'inline; filename="alert-evidence-{evidence.pk}"'
        )
        return response
