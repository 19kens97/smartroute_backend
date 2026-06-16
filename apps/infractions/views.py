from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from .models import Infraction
from .serializers import InfractionSerializer

class InfractionViewSet(ModelViewSet):
    queryset = Infraction.objects.all().order_by("code")
    serializer_class = InfractionSerializer
    permission_classes = [IsAuthenticated]
