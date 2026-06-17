from rest_framework.permissions import BasePermission


class DriverPermission(BasePermission):
    READ_ACTIONS = {
        "list",
        "retrieve",
        "search",
        "search_by_dossier",
        "search_by_nif",
    }
    WRITE_ACTIONS = {"create", "partial_update"}
    DISABLED_ACTIONS = {"update", "destroy"}

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if view.action in self.READ_ACTIONS:
            return True
        if view.action in self.WRITE_ACTIONS:
            return request.user.role == "AGENT_SAISIE"
        if view.action in self.DISABLED_ACTIONS:
            return True
        return False
