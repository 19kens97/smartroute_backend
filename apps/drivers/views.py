from rest_framework.decorators import action
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from apps.core.api import api_response
from .models import Driver
from .permissions import DriverPermission
from .serializers import DriverSerializer

class DriverViewSet(ModelViewSet):
    queryset = Driver.objects.all().order_by("-id")
    serializer_class = DriverSerializer
    permission_classes = [DriverPermission]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    filterset_fields = ("dossier_number", "nif", "sex", "blood_group", "license_type")
    search_fields = ("dossier_number", "nif", "full_name")

    def get_queryset(self):
        queryset = super().get_queryset()
        dossier_number = self.request.query_params.get("dossier_number")
        if dossier_number:
            queryset = queryset.filter(dossier_number=dossier_number)
        return queryset

    @action(detail=False, methods=["get"], url_path="search")
    def search_by_dossier(self, request):
        dossier_number = request.query_params.get("dossier_number")
        if not dossier_number:
            return api_response(
                False,
                "dossier_number is required",
                {},
                {"dossier_number": ["This query parameter is required."]},
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            driver = Driver.objects.get(dossier_number=dossier_number)
        except Driver.DoesNotExist:
            return api_response(
                False,
                "Driver not found",
                {},
                {"dossier_number": ["No driver found with this dossier number."]},
                status.HTTP_404_NOT_FOUND,
            )

        return api_response(True, "Driver loaded", DriverSerializer(driver).data)
