from rest_framework.permissions import BasePermission

from apps.accounts.models import AgentProfile, User


class ReportsPermission(BasePermission):
    message = "Vous n'êtes pas autorisé à consulter ces rapports."

    ALLOWED_ROLES = {
        AgentProfile.Role.ADMIN,
        AgentProfile.Role.AGENT_SAISIE,
    }

    def has_permission(self, request, view):
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

        return (
            profile.is_active
            and profile.role in self.ALLOWED_ROLES
        )
