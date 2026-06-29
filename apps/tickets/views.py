import logging

from django.http import FileResponse, Http404
from django.db import transaction
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from apps.core.cache import invalidate_statistics_cache
from apps.core.services import log_action

from .models import Ticket
from .permissions import TicketPermission
from .serializers import TicketProofSerializer, TicketSerializer
from .services import generate_ticket_barcode

logger = logging.getLogger(__name__)


class TicketViewSet(ModelViewSet):
    queryset = Ticket.objects.select_related("agent", "vehicle").prefetch_related("ticket_infractions__infraction", "proofs").all().order_by("-id")
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, TicketPermission]
    filterset_fields = ("status", "agent_id", "client_uuid")

    @transaction.atomic
    def perform_create(self, serializer):
        logger.info(
            "event=ticket_creation_started request_id=%s user_id=%s",
            getattr(self.request, "request_id", "-"),
            self.request.user.pk,
        )
        ticket = serializer.save(agent=self.request.user)
        generate_ticket_barcode(ticket)
        ticket.save()
        log_action(self.request.user, ticket, "CREATE")
        transaction.on_commit(invalidate_statistics_cache)
        logger.info(
            "event=ticket_created request_id=%s ticket_id=%s user_id=%s sync_status=%s",
            getattr(self.request, "request_id", "-"),
            ticket.pk,
            self.request.user.pk,
            "pending" if ticket.status == "PENDING_SYNC" else "synced",
        )
        if ticket.vehicle_id:
            from apps.alerts.services import evaluate_judicial_alert

            evaluate_judicial_alert(vehicle=ticket.vehicle, actor=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        logger.info(
            "event=receipt_requested request_id=%s ticket_id=%s user_id=%s",
            getattr(request, "request_id", "-"),
            kwargs.get("pk"),
            request.user.pk,
        )
        return response

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
        serializer = TicketProofSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        proof = serializer.save(ticket=ticket)
        logger.info(
            "event=ticket_evidence_saved request_id=%s ticket_id=%s proof_id=%s evidence_type=%s user_id=%s",
            getattr(request, "request_id", "-"),
            ticket.pk,
            proof.pk,
            proof.evidence_type,
            request.user.pk,
        )
        return api_response(True, "Proof added", TicketProofSerializer(proof, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="agent-signature")
    def agent_signature(self, request, pk=None):
        ticket = self.get_object()
        signature = getattr(ticket.agent, "signature_file", None)
        if not signature:
            raise Http404("Signature not found")
        response = FileResponse(signature.open("rb"), content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        return response
