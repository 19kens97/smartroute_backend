from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from apps.core.services import log_action
from .models import Owner
from .serializers import OwnerSerializer

class OwnerViewSet(ModelViewSet):
    queryset = Owner.objects.all().order_by("-id")
    serializer_class = OwnerSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(self.request.user, obj, "CREATE")

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(self.request.user, obj, "UPDATE")
