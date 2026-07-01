import logging

from django.http import FileResponse, Http404
from django.db import transaction
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.cache import invalidate_statistics_cache
from apps.core.services import log_action

from .models import Ticket
from .permissions import TicketPermission
from .serializers import TicketProofSerializer, TicketSerializer

logger = logging.getLogger(__name__)


class TicketViewSet(ModelViewSet):
    queryset = Ticket.objects.select_related("agent", "vehicle").prefetch_related("ticket_infractions__infraction", "proofs").all().order_by("-id")
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, TicketPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ("status", "agent_id", "client_uuid")

    @transaction.atomic
    def perform_create(self, serializer):
        request_id = getattr(self.request, "request_id", "-")
        infraction_count = len(serializer.validated_data.get("infraction_codes", []))
        logger.info(
            "event=ticket_submission_started request_id=%s user_id=%s",
            request_id,
            self.request.user.pk,
        )
        logger.info(
            "event=ticket_validation_succeeded request_id=%s user_id=%s infraction_count=%s evidence_count=0",
            request_id,
            self.request.user.pk,
            infraction_count,
        )
        ticket = serializer.save(agent=self.request.user)
        logger.info(
            "event=ticket_number_generated request_id=%s user_id=%s ticket_id=%s ticket_number=%s status=%s",
            request_id,
            self.request.user.pk,
            ticket.pk,
            ticket.ticket_number,
            ticket.status,
        )
        log_action(self.request.user, ticket, "CREATE")
        def log_committed_ticket():
            invalidate_statistics_cache()
            logger.info(
                "event=ticket_created request_id=%s ticket_id=%s user_id=%s ticket_number=%s sync_status=%s infraction_count=%s evidence_count=0",
                request_id,
                ticket.pk,
                self.request.user.pk,
                ticket.ticket_number,
                "pending" if ticket.status == "PENDING_SYNC" else "synced",
                ticket.ticket_infractions.count(),
            )
            logger.info(
                "event=transaction_committed request_id=%s ticket_id=%s user_id=%s ticket_number=%s status=%s",
                request_id,
                ticket.pk,
                self.request.user.pk,
                ticket.ticket_number,
                ticket.status,
            )

        transaction.on_commit(log_committed_ticket)
        if ticket.vehicle_id:
            from apps.alerts.services import evaluate_judicial_alert

            evaluate_judicial_alert(vehicle=ticket.vehicle, actor=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        ticket = self.get_object()
        serializer = self.get_serializer(ticket)
        logger.info(
            "event=ticket_receipt_requested request_id=%s ticket_id=%s user_id=%s ticket_number=%s status=%s",
            getattr(request, "request_id", "-"),
            ticket.pk,
            request.user.pk,
            ticket.ticket_number,
            ticket.status,
        )
        return Response(serializer.data)

    def perform_update(self, serializer):
        before = self.get_object().status
        ticket = serializer.save()
        action = "STATUS_CHANGE" if before != ticket.status else "UPDATE"
        log_action(self.request.user, ticket, action, {"from": before, "to": ticket.status})
        logger.info(
            "event=ticket_updated request_id=%s ticket_id=%s user_id=%s action=%s from_status=%s to_status=%s",
            getattr(self.request, "request_id", "-"),
            ticket.pk,
            self.request.user.pk,
            action,
            before,
            ticket.status,
        )
        transaction.on_commit(invalidate_statistics_cache)
        if ticket.vehicle_id:
            from apps.alerts.services import evaluate_judicial_alert

            evaluate_judicial_alert(vehicle=ticket.vehicle, actor=self.request.user)

    @action(detail=True, methods=["post"], url_path="proofs")
    def add_proof(self, request, pk=None):
        ticket = self.get_object()
        evidence_type = request.data.get("evidence_type", "PHOTO")
        logger.info(
            "event=media_upload_started request_id=%s ticket_id=%s user_id=%s media_context=ticket_proof evidence_type=%s evidence_count=1",
            getattr(request, "request_id", "-"),
            ticket.pk,
            request.user.pk,
            evidence_type,
        )
        serializer = TicketProofSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        proof = serializer.save(ticket=ticket, created_by=request.user)
        logger.info(
            "event=media_saved request_id=%s ticket_id=%s proof_id=%s evidence_type=%s user_id=%s status=saved checksum_sha256=%s",
            getattr(request, "request_id", "-"),
            ticket.pk,
            proof.pk,
            proof.evidence_type,
            request.user.pk,
            proof.checksum_sha256[:12],
        )
        return api_response(True, "Proof added", TicketProofSerializer(proof, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path=r"proofs/(?P<proof_id>[^/.]+)/download")
    def proof_download(self, request, pk=None, proof_id=None):
        ticket = self.get_object()
        proof = ticket.proofs.filter(pk=proof_id).first()
        if proof is None or not proof.file:
            logger.warning(
                "event=media_access_denied request_id=%s ticket_id=%s proof_id=%s user_id=%s reason=not_found",
                getattr(request, "request_id", "-"),
                ticket.pk,
                proof_id,
                request.user.pk,
            )
            raise Http404
        response = FileResponse(proof.file.open("rb"), content_type=proof.mime_type or "application/octet-stream")
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = f'inline; filename="ticket-proof-{proof.pk}"'
        logger.info(
            "event=media_downloaded request_id=%s ticket_id=%s proof_id=%s user_id=%s media_context=ticket_proof",
            getattr(request, "request_id", "-"),
            ticket.pk,
            proof.pk,
            request.user.pk,
        )
        return response

    @action(detail=True, methods=["get"], url_path="agent-signature")
    def agent_signature(self, request, pk=None):
        ticket = self.get_object()
        signature = getattr(ticket.agent, "signature_file", None)
        if not signature:
            raise Http404("Signature not found")
        response = FileResponse(signature.open("rb"), content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        return response

