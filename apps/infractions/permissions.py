from rest_framework.permissions import BasePermission

from apps.accounts.models import AgentProfile, User


class CanReadInfractionCatalog(BasePermission):
    message = "Vous n'êtes pas autorisé à consulter ce catalogue."

    def has_permission(self, request, view):
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

        return (
            profile.is_active
            and profile.role
            in {
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_TERRAIN,
                AgentProfile.Role.AGENT_SAISIE,
            }
        )
