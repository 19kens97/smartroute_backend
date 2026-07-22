from django.db.models import (
    Case,
    IntegerField,
    Q,
    Value,
    When,
)
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet

from apps.core.services import log_action
from apps.vehicles.models import (
    normalize_plate_number,
    plate_number_lookup_variants,
)

from .models import InsurancePolicy
from .permissions import InsurancePolicyPermission
from .serializers import (
    InsurancePolicyReadSerializer,
    InsurancePolicyWriteSerializer,
)


class InsurancePolicyPagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="Lister et rechercher les polices d'assurance",
        description=(
            "Lecture réservée aux comptes professionnels actifs "
            "ADMIN, AGENT_TERRAIN ou AGENT_SAISIE."
        ),
        parameters=[
            OpenApiParameter(
                name="policy_number",
                type=str,
                required=False,
                description=(
                    "Numéro de police exact, insensible à la casse."
                ),
            ),
            OpenApiParameter(
                name="plate_number",
                type=str,
                required=False,
                description=(
                    "Plaque exacte normalisée."
                ),
            ),
        ],
        responses={
            200: InsurancePolicyReadSerializer(many=True),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
        },
    ),
    retrieve=extend_schema(
        summary="Consulter une police d'assurance",
        responses={
            200: InsurancePolicyReadSerializer,
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
            404: OpenApiResponse(
                description="Police introuvable."
            ),
        },
    ),
    create=extend_schema(
        summary="Créer une police d'assurance",
        description="Permission : AGENT_SAISIE uniquement.",
        request=InsurancePolicyWriteSerializer,
        responses={
            201: InsurancePolicyReadSerializer,
            400: OpenApiResponse(
                description="Données invalides."
            ),
            403: OpenApiResponse(
                description="Rôle non autorisé."
            ),
        },
    ),
    partial_update=extend_schema(
        summary="Modifier partiellement une police d'assurance",
        description=(
            "Permission : AGENT_SAISIE uniquement. "
            "PUT et DELETE ne sont pas disponibles."
        ),
        request=InsurancePolicyWriteSerializer,
        responses={
            200: InsurancePolicyReadSerializer,
            400: OpenApiResponse(
                description="Données invalides."
            ),
            403: OpenApiResponse(
                description="Rôle non autorisé."
            ),
            404: OpenApiResponse(
                description="Police introuvable."
            ),
        },
    ),
)
class InsurancePolicyViewSet(ModelViewSet):
    permission_classes = [InsurancePolicyPermission]
    pagination_class = InsurancePolicyPagination
    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    filterset_fields = (
        "status",
        "vehicle",
        "insurer",
    )
    search_fields = (
        "policy_number",
        "insurer",
        "vehicle__plate_number",
        "vehicle__owner__person__first_name",
        "vehicle__owner__person__last_name",
        "vehicle__owner__person__nif",
    )

    def get_queryset(self):
        today = timezone.localdate()

        queryset = (
            InsurancePolicy.objects
            .select_related(
                "vehicle",
                "vehicle__owner",
                "vehicle__owner__person",
            )
            .annotate(
                status_priority=Case(
                    When(
                        status=(
                            InsurancePolicy.Status.VALID
                        ),
                        valid_from__isnull=True,
                        valid_until__gte=today,
                        then=Value(0),
                    ),
                    When(
                        status=(
                            InsurancePolicy.Status.VALID
                        ),
                        valid_from__lte=today,
                        valid_until__gte=today,
                        then=Value(0),
                    ),
                    When(
                        valid_until__lt=today,
                        then=Value(1),
                    ),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
        )

        plate_number = self.request.query_params.get(
            "plate_number"
        )

        if plate_number:
            normalized = normalize_plate_number(
                plate_number
            )
            lookup = Q()

            for variant in plate_number_lookup_variants(
                normalized
            ):
                lookup |= Q(
                    vehicle__plate_number__iexact=variant
                )

            queryset = queryset.filter(lookup)

        policy_number = self.request.query_params.get(
            "policy_number"
        )

        if policy_number:
            normalized_policy = (
                InsurancePolicy.normalize_policy_number(
                    policy_number
                )
            )
            queryset = queryset.filter(
                policy_number__iexact=normalized_policy
            )

        return queryset.order_by(
            "status_priority",
            "-valid_until",
            "-id",
        )

    def get_serializer_class(self):
        if self.action in {
            "create",
            "partial_update",
        }:
            return InsurancePolicyWriteSerializer

        return InsurancePolicyReadSerializer

    def perform_create(self, serializer):
        policy = serializer.save()
        log_action(
            self.request.user,
            policy,
            "CREATE",
        )

    def perform_update(self, serializer):
        policy = serializer.save()
        log_action(
            self.request.user,
            policy,
            "UPDATE",
        )
