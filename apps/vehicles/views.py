from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from apps.core.services import log_action
from .models import Vehicle
from .serializers import VehicleSerializer

class VehicleViewSet(ModelViewSet):
    queryset = Vehicle.objects.select_related("owner").all().order_by("-id")
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("plate_number", "is_wanted")
    search_fields = ("plate_number", "brand", "model")

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(self.request.user, obj, "CREATE")

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(self.request.user, obj, "UPDATE")
