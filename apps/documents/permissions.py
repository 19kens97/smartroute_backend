from rest_framework.permissions import BasePermission

from apps.accounts.models import AgentProfile, User


class DocumentPermission(BasePermission):
    message = "Vous n'êtes pas autorisé à effectuer cette opération."

    READ_ACTIONS = frozenset({"list", "retrieve", "download"})
    WRITE_ACTIONS = frozenset({"create", "partial_update"})

    def has_permission(self, request, view):
        if request.method.lower() not in getattr(view, "http_method_names", []):
            return True

        user = request.user

        if not (
            user
            and user.is_authenticated
            and user.is_active
            and user.account_type == User.AccountType.PROFESSIONAL
        ):
            return False

        try:
            profile = user.agent_profile
        except AgentProfile.DoesNotExist:
            return False

        if not profile.is_active:
            return False

        action = getattr(view, "action", None)

        if action in self.READ_ACTIONS:
            return profile.role in {
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_TERRAIN,
                AgentProfile.Role.AGENT_SAISIE,
            }

        if action in self.WRITE_ACTIONS:
            return profile.role == AgentProfile.Role.AGENT_SAISIE

        return False
