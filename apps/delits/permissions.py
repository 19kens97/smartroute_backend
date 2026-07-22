from rest_framework.permissions import BasePermission
from apps.accounts.models import AgentProfile, User


class DelitPermission(BasePermission):
    message = "Vous n'êtes pas autorisé à effectuer cette opération."

    READ_ACTIONS = {'list','retrieve','evidence_download'}

    def _profile(self, user):
        if not (user and user.is_authenticated and user.is_active and user.account_type == User.AccountType.PROFESSIONAL):
            return None
        try:
            profile = user.agent_profile
        except AgentProfile.DoesNotExist:
            return None
        return profile if profile.is_active else None

    def has_permission(self, request, view):
        profile = self._profile(request.user)
        if profile is None:
            return False
        action = getattr(view,'action',None)
        if action in self.READ_ACTIONS:
            return profile.role in {AgentProfile.Role.ADMIN,AgentProfile.Role.AGENT_TERRAIN,AgentProfile.Role.AGENT_SAISIE}
        if action == 'create':
            return profile.role == AgentProfile.Role.AGENT_TERRAIN
        if action in {'partial_update','add_action','add_evidence','submit_review'}:
            return profile.role in {AgentProfile.Role.ADMIN,AgentProfile.Role.AGENT_TERRAIN,AgentProfile.Role.AGENT_SAISIE}
        if action in {'confirm','reject','refer','close','cancel'}:
            return profile.role == AgentProfile.Role.ADMIN
        return False

    def has_object_permission(self, request, view, obj):
        profile = self._profile(request.user)
        if profile is None:
            return False
        action = getattr(view,'action',None)
        if action in self.READ_ACTIONS:
            return True
        if profile.role == AgentProfile.Role.ADMIN:
            return True
        if action in {'partial_update','add_action','add_evidence','submit_review'}:
            if profile.role == AgentProfile.Role.AGENT_TERRAIN:
                return obj.detected_by_id == request.user.id and obj.qualification_status == obj.QualificationStatus.POTENTIAL and obj.procedure_status == obj.ProcedureStatus.OPEN
            if profile.role == AgentProfile.Role.AGENT_SAISIE:
                return obj.procedure_status not in {obj.ProcedureStatus.CLOSED,obj.ProcedureStatus.CANCELLED}
        return False
