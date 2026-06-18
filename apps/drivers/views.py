from rest_framework.decorators import action
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from apps.core.api import api_response
from .models import Driver
from .permissions import DriverPermission
from .serializers import (
    DriverDossierSearchQuerySerializer,
    DriverLicenseReadSerializer,
    DriverNIFSearchQuerySerializer,
    DriverSerializer,
)
from .services import build_license_search_result, normalize_dossier_number, normalize_nif, normalized_nif_expression

LICENSE_SEARCH_FIELDS = (
    "id",
    "dossier_number",
    "nif",
    "full_name",
    "address",
    "birth_date",
    "sex",
    "blood_group",
    "license_type",
    "issue_place",
    "issue_date",
    "expires_at",
    "created_at",
    "updated_at",
)


@extend_schema_view(
    list=extend_schema(
        summary="Lister les conducteurs",
        description="Permission: tout utilisateur authentifie. PUT et DELETE ne sont pas disponibles.",
        responses={200: DriverSerializer, 401: OpenApiResponse(description="Authentification JWT requise.")},
    ),
    retrieve=extend_schema(
        summary="Consulter un conducteur",
        description="Permission: tout utilisateur authentifie.",
        responses={
            200: DriverSerializer,
            401: OpenApiResponse(description="Authentification JWT requise."),
            404: OpenApiResponse(description="Introuvable."),
        },
    ),
    create=extend_schema(
        summary="Creer un conducteur",
        description="Permission: AGENT_SAISIE uniquement.",
        responses={
            201: DriverSerializer,
            400: OpenApiResponse(description="Donnees invalides."),
            401: OpenApiResponse(description="Authentification JWT requise."),
            403: OpenApiResponse(description="Role non autorise."),
        },
    ),
    partial_update=extend_schema(
        summary="Modifier partiellement un conducteur",
        description="Permission: AGENT_SAISIE uniquement. PUT est indisponible; utilisez PATCH.",
        responses={
            200: DriverSerializer,
            400: OpenApiResponse(description="Donnees invalides."),
            401: OpenApiResponse(description="Authentification JWT requise."),
            403: OpenApiResponse(description="Role non autorise."),
            404: OpenApiResponse(description="Introuvable."),
        },
    ),
)
class DriverViewSet(ModelViewSet):
    queryset = Driver.objects.all().order_by("-id")
    serializer_class = DriverSerializer
    permission_classes = [DriverPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ("dossier_number", "nif", "sex", "blood_group", "license_type")
    search_fields = ("dossier_number", "nif", "full_name")

    def get_queryset(self):
        queryset = super().get_queryset()
        dossier_number = self.request.query_params.get("dossier_number")
        if dossier_number:
            queryset = queryset.filter(dossier_number=dossier_number)
        return queryset

    def _not_found_response(self):
        return api_response(
            False,
            "Aucun permis trouvé.",
            {},
            {"driver_license": ["Aucun permis ne correspond aux informations fournies."]},
            status.HTTP_404_NOT_FOUND,
        )

    def _license_response(self, drivers):
        message, data = build_license_search_result(drivers, DriverLicenseReadSerializer)
        response = api_response(True, message, data)
        response["Cache-Control"] = "private, no-store"
        return response

    def _search_by_dossier_response(self, request):
        serializer = DriverDossierSearchQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return api_response(
                False,
                "Le numéro de dossier est requis.",
                {},
                {"dossier_number": ["Ce paramètre de recherche est obligatoire."]},
                status.HTTP_400_BAD_REQUEST,
            )

        dossier_number = normalize_dossier_number(serializer.validated_data["dossier_number"])
        drivers = list(
            Driver.objects.only(*LICENSE_SEARCH_FIELDS)
            .filter(dossier_number__iexact=dossier_number)
            .order_by("-id")
        )
        if not drivers:
            return self._not_found_response()
        return self._license_response(drivers)

    def _search_by_nif_response(self, request):
        serializer = DriverNIFSearchQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return api_response(
                False,
                "Le NIF est requis.",
                {},
                {"nif": ["Ce paramètre de recherche est obligatoire."]},
                status.HTTP_400_BAD_REQUEST,
            )

        nif = normalize_nif(serializer.validated_data["nif"])
        drivers = list(
            Driver.objects.only(*LICENSE_SEARCH_FIELDS)
            .annotate(normalized_nif=normalized_nif_expression())
            .filter(normalized_nif=nif)
            .order_by("-issue_date", "-id")
        )
        if not drivers:
            return self._not_found_response()
        return self._license_response(drivers)

    @extend_schema(
        summary="Rechercher un permis par numero de dossier",
        description="Tous les utilisateurs authentifiés peuvent consulter ce endpoint. Alias historique: /api/drivers/search/.",
        parameters=[
            OpenApiParameter(
                name="dossier_number",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
                examples=[OpenApiExample("Dossier", value="DRV-000124")],
            )
        ],
        responses={
            200: OpenApiResponse(description="Permis trouvé. Inclut count, has_conflict, alert et licenses."),
            400: OpenApiResponse(description="Paramètre dossier_number absent ou vide."),
            401: OpenApiResponse(description="Authentification JWT requise."),
            404: OpenApiResponse(description="Aucun permis trouvé."),
        },
        examples=[
            OpenApiExample(
                "Permis trouvé",
                value={
                    "success": True,
                    "message": "Permis trouvé.",
                    "data": {
                        "count": 1,
                        "active_count": 1,
                        "has_conflict": False,
                        "alert": None,
                        "overlapping_license_ids": [],
                        "licenses": [{"dossier_number": "DRV-000124", "is_currently_valid": True, "validity_state": "ACTIVE"}],
                    },
                    "errors": {},
                },
                response_only=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="search-by-dossier",
    )
    def search_by_dossier(self, request):
        return self._search_by_dossier_response(request)

    @extend_schema(
        summary="Rechercher des permis par NIF",
        description=(
            "Tous les utilisateurs authentifiés peuvent consulter ce endpoint. "
            "Les espaces et tirets du NIF sont ignorés. Le cas MULTIPLE_ACTIVE_LICENSES est retourné en HTTP 200."
        ),
        parameters=[
            OpenApiParameter(
                name="nif",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
                examples=[OpenApiExample("NIF", value="001-234-567-8")],
            )
        ],
        responses={
            200: OpenApiResponse(description="Permis trouvés ou alerte métier MULTIPLE_ACTIVE_LICENSES."),
            400: OpenApiResponse(description="Paramètre nif absent ou vide."),
            401: OpenApiResponse(description="Authentification JWT requise."),
            404: OpenApiResponse(description="Aucun permis trouvé."),
        },
        examples=[
            OpenApiExample(
                "Plusieurs permis actifs",
                value={
                    "success": True,
                    "message": "Plusieurs permis actifs ont été détectés pour cette personne.",
                    "data": {
                        "count": 2,
                        "active_count": 2,
                        "has_conflict": True,
                        "alert": {
                            "code": "MULTIPLE_ACTIVE_LICENSES",
                            "level": "WARNING",
                            "message": "Plusieurs permis utilisables simultanément sont associés à ce NIF. Une vérification administrative est requise.",
                        },
                        "overlapping_license_ids": [12, 18],
                        "licenses": [],
                    },
                    "errors": {},
                },
                response_only=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="search-by-nif",
    )
    def search_by_nif(self, request):
        return self._search_by_nif_response(request)

    @extend_schema(
        summary="Alias historique de recherche par numero de dossier",
        description="Alias rétrocompatible de /api/drivers/search-by-dossier/.",
        deprecated=True,
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="search",
    )
    def search(self, request):
        return self._search_by_dossier_response(request)
