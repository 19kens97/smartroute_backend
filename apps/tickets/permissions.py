from rest_framework.permissions import BasePermission

from apps.accounts.models import AgentProfile, User
from .models import Ticket, TicketVerbalization


class TicketPermission(BasePermission):
    message = "Vous n'êtes pas autorisé à effectuer cette opération."

    READ_ACTIONS = frozenset({
        "list",
        "retrieve",
        "find_open",
        "proof_download",
        "agent_signature",
    })

    def _profile(self, user):
        if not (
            user
            and user.is_authenticated
            and user.is_active
            and user.account_type == User.AccountType.PROFESSIONAL
        ):
            return None
        try:
            profile = user.agent_profile
        except AgentProfile.DoesNotExist:
            return None
        return profile if profile.is_active else None

    def has_permission(self, request, view):
        profile = self._profile(request.user)
        if profile is None:
            return False
        action = getattr(view, "action", None)

        if action in self.READ_ACTIONS:
            return profile.role in {
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_TERRAIN,
                AgentProfile.Role.AGENT_SAISIE,
            }
        if action == "create":
            return profile.role == AgentProfile.Role.AGENT_TERRAIN
        if action == "add_verbalization":
            return profile.role == AgentProfile.Role.AGENT_TERRAIN
        if action == "partial_update":
            return profile.role in {
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_SAISIE,
            }
        if action in {"close", "cancel", "cancel_verbalization"}:
            return profile.role == AgentProfile.Role.ADMIN
        if action == "add_proof":
            return profile.role == AgentProfile.Role.AGENT_TERRAIN
        return False

    def has_object_permission(self, request, view, obj):
        profile = self._profile(request.user)
        if profile is None:
            return False
        action = getattr(view, "action", None)

        if action in self.READ_ACTIONS:
            return True
        if action == "add_verbalization":
            return obj.status == Ticket.Status.OPEN
        if action == "partial_update":
            return obj.status != Ticket.Status.CANCELLED
        if action in {"close", "cancel"}:
            return obj.status == Ticket.Status.OPEN
        if action == "add_proof":
            return (
                isinstance(obj, TicketVerbalization)
                and obj.status == TicketVerbalization.Status.ACTIVE
                and obj.ticket.status == Ticket.Status.OPEN
                and obj.agent_id == request.user.id
            )
        if action == "cancel_verbalization":
            return (
                isinstance(obj, TicketVerbalization)
                and obj.status == TicketVerbalization.Status.ACTIVE
            )
        return False
