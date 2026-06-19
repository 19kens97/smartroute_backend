from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    roles = set()

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in self.roles
        )


class IsAdminRole(HasRole):
    roles = {"ADMIN"}


class IsFieldAgentRole(HasRole):
    roles = {"AGENT_TERRAIN"}


class IsEntryAgentRole(HasRole):
    roles = {"AGENT_SAISIE"}


class IsAdminOrFieldAgentRole(HasRole):
    roles = {"ADMIN", "AGENT_TERRAIN"}


class IsAdminOrEntryAgentRole(HasRole):
    roles = {"ADMIN", "AGENT_SAISIE"}
