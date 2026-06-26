import logging

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
    queryset = Ticket.objects.select_related("agent", "vehicle").prefetch_related("ticket_infractions", "proofs").all().order_by("-id")
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, TicketPermission]
    filterset_fields = ("status", "agent_id", "client_uuid")

    def perform_create(self, serializer):
        ticket = serializer.save(agent=self.request.user)
        generate_ticket_barcode(ticket)
        ticket.save()
        log_action(self.request.user, ticket, "CREATE")
        transaction.on_commit(invalidate_statistics_cache)
        if ticket.vehicle_id:
            from apps.alerts.services import evaluate_judicial_alert

            evaluate_judicial_alert(vehicle=ticket.vehicle, actor=self.request.user)

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
        serializer = TicketProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        proof = serializer.save(ticket=ticket)
        return api_response(True, "Proof added", TicketProofSerializer(proof).data)
