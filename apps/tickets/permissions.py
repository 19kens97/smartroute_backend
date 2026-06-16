from rest_framework.permissions import SAFE_METHODS, BasePermission

class TicketPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        role = request.user.role
        if request.method in SAFE_METHODS:
            return True
        if role == "ADMIN":
            return True
        if role == "AGENT_TERRAIN":
            return obj.agent_id == request.user.id
        if role == "AGENT_SAISIE":
            return request.method == "PATCH"
        return False
