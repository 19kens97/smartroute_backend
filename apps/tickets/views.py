from io import BytesIO

from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.cache import invalidate_statistics_cache
from apps.core.services import log_action

from .models import Ticket, TicketProof, TicketVerbalization
from .pagination import TicketPagination
from .permissions import TicketPermission
from .serializers import (
    AddVerbalizationSerializer,
    ReasonSerializer,
    TicketListSerializer,
    TicketProofSerializer,
    TicketSerializer,
    TicketVerbalizationSerializer,
)
from .services import find_open_ticket


class TicketViewSet(ModelViewSet):
    permission_classes = [TicketPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = TicketPagination
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = (
        "status",
        "sync_status",
        "pricing_status",
        "opened_by",
        "driver",
        "client_uuid",
    )
    search_fields = (
        "ticket_number",
        "barcode_value",
        "driver_dossier_snapshot",
        "driver_name_snapshot",
        "driver_nif_snapshot",
        "verbalizations__plate_number_snapshot",
        "verbalizations__location_label",
    )

    def get_queryset(self):
        return (
            Ticket.objects
            .select_related(
                "driver",
                "driver__person",
                "opened_by",
                "opened_by__person",
                "closed_by",
                "cancelled_by",
            )
            .prefetch_related(
                "verbalizations__agent",
                "verbalizations__agent__person",
                "verbalizations__agent__agent_profile",
                "verbalizations__vehicle",
                "verbalizations__infractions__infraction",
                "verbalizations__proofs",
            )
            .order_by("-opened_at", "-id")
        )

    def get_serializer_class(self):
        if self.action == "list":
            return TicketListSerializer
        return TicketSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        ticket = serializer.save()
        log_action(self.request.user, ticket, "CREATE_TICKET")
        first = ticket.verbalizations.order_by("sequence_number").first()
        if first:
            log_action(
                self.request.user,
                first,
                "CREATE_VERBALIZATION",
                {"ticket_number": ticket.ticket_number, "sequence_number": 1},
            )
        transaction.on_commit(invalidate_statistics_cache)
        self._evaluate_alerts(ticket, first)

    def perform_update(self, serializer):
        ticket = serializer.save()
        log_action(self.request.user, ticket, "UPDATE_TICKET")
        transaction.on_commit(invalidate_statistics_cache)

    def _evaluate_alerts(self, ticket, verbalization=None):
        vehicle = getattr(verbalization, "vehicle", None)
        if not vehicle:
            return
        from apps.alerts.services import (
            evaluate_document_expiry_warnings,
            evaluate_judicial_alert,
        )
        evaluate_document_expiry_warnings(
            driver=ticket.driver,
            vehicle=vehicle,
            actor=self.request.user,
        )
        evaluate_judicial_alert(
            driver=ticket.driver,
            vehicle=vehicle,
            actor=self.request.user,
        )

    @action(detail=False, methods=["get"], url_path="open")
    def find_open(self, request):
        ticket = find_open_ticket(
            dossier_number=request.query_params.get("dossier_number"),
            nif=request.query_params.get("nif"),
            ticket_number=request.query_params.get("ticket_number"),
        )
        if ticket is None:
            return api_response(True, "Aucun PV en cours.", {"found": False, "ticket": None})
        hydrated = self.get_queryset().get(pk=ticket.pk)
        return api_response(
            True,
            "PV en cours trouvé.",
            {
                "found": True,
                "ticket": TicketSerializer(hydrated, context={"request": request}).data,
            },
        )

    @action(detail=True, methods=["post"], url_path="verbalizations")
    def add_verbalization(self, request, pk=None):
        ticket = self.get_object()
        serializer = AddVerbalizationSerializer(
            data=request.data,
            context={"request": request, "ticket": ticket},
        )
        serializer.is_valid(raise_exception=True)
        verbalization = serializer.save()
        log_action(
            request.user,
            verbalization,
            "CREATE_VERBALIZATION",
            {
                "ticket_number": ticket.ticket_number,
                "sequence_number": verbalization.sequence_number,
            },
        )
        transaction.on_commit(invalidate_statistics_cache)
        self._evaluate_alerts(ticket, verbalization)
        return api_response(
            True,
            "Nouvelle verbalisation ajoutée au PV en cours.",
            TicketVerbalizationSerializer(
                verbalization,
                context={"request": request},
            ).data,
        )

    def _get_verbalization(self, ticket, verbalization_id):
        verbalization = ticket.verbalizations.filter(pk=verbalization_id).first()
        if verbalization is None:
            raise Http404
        self.check_object_permissions(self.request, verbalization)
        return verbalization

    @action(
        detail=True,
        methods=["post"],
        url_path=r"verbalizations/(?P<verbalization_id>[^/.]+)/cancel",
    )
    def cancel_verbalization(self, request, pk=None, verbalization_id=None):
        ticket = self.get_object()
        verbalization = self._get_verbalization(ticket, verbalization_id)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verbalization.status = TicketVerbalization.Status.CANCELLED
        verbalization.cancelled_at = timezone.now()
        verbalization.cancelled_by = request.user
        verbalization.cancellation_reason = serializer.validated_data["reason"]
        verbalization.save(
            update_fields=(
                "status",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "updated_at",
            )
        )
        log_action(request.user, verbalization, "CANCEL_VERBALIZATION")
        transaction.on_commit(invalidate_statistics_cache)
        return api_response(
            True,
            "Verbalisation annulée.",
            TicketVerbalizationSerializer(verbalization, context={"request": request}).data,
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        ticket = self.get_object()
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket.status = Ticket.Status.CLOSED
        ticket.closed_at = timezone.now()
        ticket.closed_by = request.user
        ticket.closure_reason = serializer.validated_data["reason"]
        ticket.save(
            update_fields=(
                "status",
                "closed_at",
                "closed_by",
                "closure_reason",
                "updated_at",
            )
        )
        log_action(request.user, ticket, "CLOSE_TICKET")
        transaction.on_commit(invalidate_statistics_cache)
        return api_response(
            True,
            "PV clôturé.",
            TicketSerializer(ticket, context={"request": request}).data,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        ticket = self.get_object()
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket.status = Ticket.Status.CANCELLED
        ticket.cancelled_at = timezone.now()
        ticket.cancelled_by = request.user
        ticket.cancellation_reason = serializer.validated_data["reason"]
        ticket.save(
            update_fields=(
                "status",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "updated_at",
            )
        )
        log_action(request.user, ticket, "CANCEL_TICKET")
        transaction.on_commit(invalidate_statistics_cache)
        return api_response(
            True,
            "PV annulé.",
            TicketSerializer(ticket, context={"request": request}).data,
        )

    @action(detail=True, methods=["get"], url_path="barcode")
    def barcode(self, request, pk=None):
        try:
            from reportlab.graphics import renderSVG
            from reportlab.graphics.barcode import createBarcodeDrawing
        except ImportError:
            return api_response(
                False,
                "Le module de génération du code-barres n'est pas disponible.",
                {},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        ticket = self.get_object()
        drawing = createBarcodeDrawing(
            "Code128",
            value=ticket.barcode_value,
            barHeight=44,
            barWidth=1.1,
        )
        content = renderSVG.drawToString(drawing)
        response = HttpResponse(content, content_type="image/svg+xml")
        response["Cache-Control"] = "private, max-age=3600"
        response["Content-Disposition"] = f'inline; filename="pv-{ticket.ticket_number}-barcode.svg"'
        return response

    @action(
        detail=True,
        methods=["post"],
        url_path=r"verbalizations/(?P<verbalization_id>[^/.]+)/proofs",
    )
    def add_proof(self, request, pk=None, verbalization_id=None):
        ticket = self.get_object()
        verbalization = self._get_verbalization(ticket, verbalization_id)
        serializer = TicketProofSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        proof = serializer.save(verbalization=verbalization, created_by=request.user)
        log_action(request.user, verbalization, "ADD_PROOF", {"proof_id": proof.pk})
        return api_response(
            True,
            "Preuve ajoutée.",
            TicketProofSerializer(proof, context={"request": request}).data,
        )

    @action(
        detail=True,
        methods=["get"],
        url_path=(
            r"verbalizations/(?P<verbalization_id>[^/.]+)/"
            r"proofs/(?P<proof_id>[^/.]+)/download"
        ),
    )
    def proof_download(self, request, pk=None, verbalization_id=None, proof_id=None):
        ticket = self.get_object()
        verbalization = self._get_verbalization(ticket, verbalization_id)
        proof = verbalization.proofs.filter(pk=proof_id).first()
        if proof is None or not proof.file:
            raise Http404
        try:
            proof.file.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404
        response = FileResponse(
            proof.file,
            content_type=proof.mime_type or "application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = f'inline; filename="ticket-proof-{proof.pk}"'
        return response

    @action(detail=True, methods=["get"], url_path="agent-signature")
    def agent_signature(self, request, pk=None):
        ticket = self.get_object()
        first = ticket.verbalizations.order_by("sequence_number").first()
        if first is None:
            raise Http404
        profile = getattr(first.agent, "agent_profile", None)
        signature = getattr(profile, "signature_file", None) or getattr(profile, "signature", None)
        if not signature:
            raise Http404("Signature introuvable.")
        try:
            signature.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404
        response = FileResponse(signature, content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        return response
