from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.accounts.models import AgentProfile, User


class OwnersPermission(BasePermission):
    message = "Vous n'êtes pas autorisé à effectuer cette opération."

    WRITE_ROLES = {
        AgentProfile.Role.ADMIN,
        AgentProfile.Role.AGENT_SAISIE,
    }
    READ_ROLES = {
        AgentProfile.Role.ADMIN,
        AgentProfile.Role.AGENT_SAISIE,
        AgentProfile.Role.AGENT_TERRAIN,
    }

    def has_permission(self, request, view):
        if request.method.lower() not in getattr(view, "http_method_names", []):
            return True

        user = getattr(request, "user", None)

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

        if request.method in SAFE_METHODS:
            return profile.role in self.READ_ROLES

        return profile.role in self.WRITE_ROLES
