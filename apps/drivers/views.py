from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response

from .models import Driver
from .permissions import DriverPermission
from .serializers import (
    DriverCreateSerializer,
    DriverDossierSearchQuerySerializer,
    DriverLicenseReadSerializer,
    DriverNIFSearchQuerySerializer,
    DriverUpdateSerializer,
)
from .services import (
    build_license_search_result,
    normalize_dossier_lookup_value,
    normalize_nif,
    normalized_dossier_expression,
    normalized_nif_expression,
)


class DriverPagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="Lister les dossiers conducteurs",
        description=(
            "Permission : compte professionnel actif avec rôle ADMIN, "
            "AGENT_TERRAIN ou AGENT_SAISIE. Pagination de 40 éléments."
        ),
        responses={
            200: DriverLicenseReadSerializer(many=True),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
        },
    ),
    retrieve=extend_schema(
        summary="Consulter un dossier conducteur",
        description=(
            "Permission : compte professionnel actif avec rôle autorisé."
        ),
        responses={
            200: DriverLicenseReadSerializer,
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
            404: OpenApiResponse(description="Dossier introuvable."),
        },
    ),
    create=extend_schema(
        summary="Créer un dossier conducteur",
        description=(
            "Permission : AGENT_SAISIE uniquement. Fournir soit `person`, "
            "soit `person_id`."
        ),
        request=DriverCreateSerializer,
        responses={
            201: DriverLicenseReadSerializer,
            400: OpenApiResponse(description="Données invalides."),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Seul un agent de saisie est autorisé."
            ),
        },
    ),
    partial_update=extend_schema(
        summary="Modifier partiellement un dossier conducteur",
        description=(
            "Permission : AGENT_SAISIE uniquement. PUT et DELETE ne sont "
            "pas disponibles."
        ),
        request=DriverUpdateSerializer,
        responses={
            200: DriverLicenseReadSerializer,
            400: OpenApiResponse(description="Données invalides."),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Seul un agent de saisie est autorisé."
            ),
            404: OpenApiResponse(description="Dossier introuvable."),
        },
    ),
)
class DriverViewSet(ModelViewSet):
    permission_classes = [DriverPermission]
    pagination_class = DriverPagination
    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    filterset_fields = (
        "dossier_number",
        "person__nif",
        "sex",
        "blood_group",
        "license_type",
    )
    search_fields = (
        "dossier_number",
        "person__nif",
        "person__first_name",
        "person__last_name",
    )

    def get_queryset(self):
        return (
            Driver.objects
            .select_related("person")
            .order_by("-id")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return DriverCreateSerializer

        if self.action == "partial_update":
            return DriverUpdateSerializer

        return DriverLicenseReadSerializer

    def _not_found_response(self):
        return api_response(
            False,
            "Aucun permis trouvé.",
            {},
            {
                "driver_license": [
                    "Aucun permis ne correspond aux informations fournies."
                ]
            },
            status.HTTP_404_NOT_FOUND,
        )

    def _license_response(self, drivers):
        drivers = list(drivers)

        message, data = build_license_search_result(
            drivers,
            DriverLicenseReadSerializer,
        )
        data["judicial_alert"] = None

        if (
            drivers
            and drivers[0].nif
            and data["unpaid_tickets"]["count"] >= 2
        ):
            from apps.alerts.services import evaluate_judicial_alert

            judicial_alert, _ = evaluate_judicial_alert(
                nif=drivers[0].nif,
                actor=self.request.user,
                unpaid_ticket_count=data["unpaid_tickets"]["count"],
            )

            if judicial_alert is not None:
                data["judicial_alert"] = {
                    "code": "JUDICIAL_ALERT",
                    "level": "CRITICAL",
                    "message": judicial_alert.description,
                }

        response = api_response(
            True,
            message,
            data,
        )
        response["Cache-Control"] = "private, no-store"
        return response

    def _search_by_dossier_response(self, request):
        query_serializer = DriverDossierSearchQuerySerializer(
            data=request.query_params
        )

        if not query_serializer.is_valid():
            return api_response(
                False,
                "Le numéro de dossier est requis.",
                {},
                {
                    "dossier_number": [
                        "Ce paramètre de recherche est obligatoire."
                    ]
                },
                status.HTTP_400_BAD_REQUEST,
            )

        dossier_number = normalize_dossier_lookup_value(
            query_serializer.validated_data["dossier_number"]
        )

        drivers = (
            self.get_queryset()
            .annotate(
                normalized_dossier_number=(
                    normalized_dossier_expression()
                )
            )
            .filter(
                normalized_dossier_number=dossier_number
            )
        )

        if not drivers.exists():
            return self._not_found_response()

        return self._license_response(drivers)

    def _search_by_nif_response(self, request):
        query_serializer = DriverNIFSearchQuerySerializer(
            data=request.query_params
        )

        if not query_serializer.is_valid():
            return api_response(
                False,
                "Le NIF est requis.",
                {},
                {
                    "nif": [
                        "Ce paramètre de recherche est obligatoire."
                    ]
                },
                status.HTTP_400_BAD_REQUEST,
            )

        nif = normalize_nif(
            query_serializer.validated_data["nif"]
        )

        drivers = (
            self.get_queryset()
            .annotate(
                normalized_person_nif=(
                    normalized_nif_expression()
                )
            )
            .filter(normalized_person_nif=nif)
        )

        if not drivers.exists():
            return self._not_found_response()

        return self._license_response(drivers)

    @extend_schema(
        summary="Rechercher un permis par numéro de dossier",
        parameters=[
            OpenApiParameter(
                name="dossier_number",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
                examples=[
                    OpenApiExample(
                        "Dossier",
                        value="DRV-000124",
                    )
                ],
            )
        ],
        responses={
            200: OpenApiResponse(
                description=(
                    "Permis trouvé avec état de validité, tickets impayés "
                    "et éventuelle alerte judiciaire."
                )
            ),
            400: OpenApiResponse(
                description="Paramètre absent ou vide."
            ),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
            404: OpenApiResponse(
                description="Aucun permis trouvé."
            ),
        },
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="search-by-dossier",
    )
    def search_by_dossier(self, request):
        return self._search_by_dossier_response(request)

    @extend_schema(
        summary="Rechercher un permis par NIF",
        description=(
            "La recherche utilise Person.nif. Les espaces et tirets sont "
            "ignorés."
        ),
        parameters=[
            OpenApiParameter(
                name="nif",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
                examples=[
                    OpenApiExample(
                        "NIF",
                        value="001-234-567-8",
                    )
                ],
            )
        ],
        responses={
            200: OpenApiResponse(description="Permis trouvé."),
            400: OpenApiResponse(
                description="Paramètre absent ou vide."
            ),
            401: OpenApiResponse(
                description="Authentification JWT requise."
            ),
            403: OpenApiResponse(
                description="Compte ou rôle non autorisé."
            ),
            404: OpenApiResponse(
                description="Aucun permis trouvé."
            ),
        },
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="search-by-nif",
    )
    def search_by_nif(self, request):
        return self._search_by_nif_response(request)

    @extend_schema(
        summary="Alias historique de recherche par dossier",
        deprecated=True,
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="search",
    )
    def search(self, request):
        return self._search_by_dossier_response(request)
