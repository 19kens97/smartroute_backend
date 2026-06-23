from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.vehicles.models import normalize_plate_number
from .models import InsurancePolicy
from .serializers import InsurancePolicySerializer


class InsurancePolicyViewSet(ModelViewSet):
    queryset = InsurancePolicy.objects.select_related("vehicle", "vehicle__owner").all()
    serializer_class = InsurancePolicySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("status", "vehicle")
    search_fields = ("policy_number", "insurer", "vehicle__plate_number")

    @extend_schema(
        parameters=[
            OpenApiParameter("policy_number", str, description="Numero de police exact, insensible a la casse."),
            OpenApiParameter("plate_number", str, description="Plaque exacte normalisee."),
        ],
        responses={
            200: InsurancePolicySerializer(many=True),
            401: OpenApiResponse(description="Authentification JWT requise."),
        },
    )
    def get_queryset(self):
        today = timezone.localdate()
        queryset = super().get_queryset().annotate(
            status_priority=Case(
                When(status=InsurancePolicy.STATUS_VALID, valid_until__gte=today, then=Value(0)),
                When(valid_until__lt=today, then=Value(1)),
                When(status=InsurancePolicy.STATUS_SUSPENDED, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        plate_number = self.request.query_params.get("plate_number")
        if plate_number:
            queryset = queryset.filter(vehicle__plate_number__iexact=normalize_plate_number(plate_number))
        policy_number = self.request.query_params.get("policy_number")
        if policy_number:
            queryset = queryset.filter(policy_number__iexact=policy_number.strip())
        return queryset.order_by("status_priority", "-valid_until", "-id")
