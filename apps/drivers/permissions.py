from rest_framework.permissions import SAFE_METHODS, BasePermission


class DriverPermission(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == "AGENT_SAISIE"
