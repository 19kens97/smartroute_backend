from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from .models import Alert
from .serializers import AlertSerializer

class AlertViewSet(ModelViewSet):
    queryset = Alert.objects.select_related("created_by").all().order_by("-id")
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
