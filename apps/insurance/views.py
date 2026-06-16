from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from .models import InsurancePolicy
from .serializers import InsurancePolicySerializer


class InsurancePolicyViewSet(ModelViewSet):
    queryset = InsurancePolicy.objects.select_related("vehicle").all().order_by("-id")
    serializer_class = InsurancePolicySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("policy_number", "status", "vehicle")
    search_fields = ("policy_number", "insurer", "vehicle__plate_number")

    def get_queryset(self):
        queryset = super().get_queryset()
        plate_number = self.request.query_params.get("plate_number")
        if plate_number:
            queryset = queryset.filter(vehicle__plate_number=plate_number)
        return queryset

