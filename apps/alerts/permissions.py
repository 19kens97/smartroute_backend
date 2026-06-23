from rest_framework.permissions import BasePermission


class AlertPermission(BasePermission):
    READ_ACTIONS = {"list", "retrieve", "recent_unread", "mark_opened", "evidence"}
    WRITE_ACTIONS = {"update", "partial_update"}

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(request.user, "role", None)
        if view.action in self.READ_ACTIONS:
            return True
        if view.action == "create":
            return role in {"AGENT_SAISIE", "AGENT_TERRAIN"}
        if view.action in self.WRITE_ACTIONS:
            return role == "AGENT_SAISIE"
        if view.action == "destroy":
            return True
        return False
