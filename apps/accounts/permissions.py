from rest_framework.permissions import BasePermission

from .models import AgentProfile, User


class IsProfessionalAccount(BasePermission):
    message = "Un compte professionnel actif est requis."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.account_type == User.AccountType.PROFESSIONAL
        )


class IsPersonalAccount(BasePermission):
    message = "Un compte personnel actif est requis."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.account_type == User.AccountType.PERSONAL
        )


class HasActiveAgentProfile(BasePermission):
    message = "Un profil agent actif est requis."

    def has_permission(self, request, view):
        if not IsProfessionalAccount().has_permission(request, view):
            return False
        try:
            return request.user.agent_profile.is_active
        except AgentProfile.DoesNotExist:
            return False


class AgentRolePermission(BasePermission):
    allowed_roles = frozenset()

    def has_permission(self, request, view):
        if not HasActiveAgentProfile().has_permission(request, view):
            return False
        return request.user.agent_profile.role in self.allowed_roles


class IsAdmin(AgentRolePermission):
    allowed_roles = frozenset({AgentProfile.Role.ADMIN})


class IsAgentTerrain(AgentRolePermission):
    allowed_roles = frozenset({AgentProfile.Role.AGENT_TERRAIN})


class IsAgentSaisie(AgentRolePermission):
    allowed_roles = frozenset({AgentProfile.Role.AGENT_SAISIE})


class IsAdminOrAgentTerrain(AgentRolePermission):
    allowed_roles = frozenset(
        {AgentProfile.Role.ADMIN, AgentProfile.Role.AGENT_TERRAIN}
    )


class IsAdminOrAgentSaisie(AgentRolePermission):
    allowed_roles = frozenset(
        {AgentProfile.Role.ADMIN, AgentProfile.Role.AGENT_SAISIE}
    )


class IsAgentTerrainOrAgentSaisie(AgentRolePermission):
    allowed_roles = frozenset(
        {AgentProfile.Role.AGENT_TERRAIN, AgentProfile.Role.AGENT_SAISIE}
    )
