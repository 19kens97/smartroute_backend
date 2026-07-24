from rest_framework.permissions import BasePermission

from apps.accounts.models import AgentProfile, User


class AlertPermission(BasePermission):
    message = "Vous n'êtes pas autorisé à effectuer cette opération."

    READ_ACTIONS = frozenset(
        {
            "list",
            "retrieve",
            "recent_unread",
            "mark_opened",
            "evidence",
        }
    )
    MANAGE_ACTIONS = frozenset(
        {
            "partial_update",
            "resolve",
            "cancel",
        }
    )

    def _profile(self, user):
        if not (
            user
            and user.is_authenticated
            and user.is_active
            and user.account_type == User.AccountType.PROFESSIONAL
        ):
            return None

        try:
            profile = user.agent_profile
        except AgentProfile.DoesNotExist:
            return None

        return profile if profile.is_active else None

    def has_permission(self, request, view):
        if request.method.lower() not in getattr(view, "http_method_names", []):
            return True

        profile = self._profile(request.user)
        if profile is None:
            return False

        action = getattr(view, "action", None)

        if action in self.READ_ACTIONS:
            return profile.role in {
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_TERRAIN,
                AgentProfile.Role.AGENT_SAISIE,
            }

        if action == "create":
            return profile.role in {
                AgentProfile.Role.AGENT_TERRAIN,
                AgentProfile.Role.AGENT_SAISIE,
            }

        if action in self.MANAGE_ACTIONS:
            return profile.role in {
                AgentProfile.Role.ADMIN,
                AgentProfile.Role.AGENT_SAISIE,
            }

        return False
