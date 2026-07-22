from pathlib import Path

from django.http import FileResponse
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet

from .models import Document
from .permissions import DocumentPermission
from .serializers import (
    DocumentCreateSerializer,
    DocumentReadSerializer,
    DocumentUpdateSerializer,
)


class DocumentPagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="Lister les pièces jointes des véhicules",
        description=(
            "Lecture réservée aux comptes professionnels actifs disposant "
            "d'un rôle ADMIN, AGENT_TERRAIN ou AGENT_SAISIE."
        ),
        parameters=[
            OpenApiParameter(
                name="vehicle",
                type=int,
                required=False,
                description="Filtrer par identifiant du véhicule.",
            ),
            OpenApiParameter(
                name="document_type",
                type=str,
                required=False,
                description="Filtrer par type de pièce jointe.",
            ),
        ],
        responses={200: DocumentReadSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Consulter une pièce jointe",
        responses={
            200: DocumentReadSerializer,
            404: OpenApiResponse(description="Document introuvable."),
        },
    ),
    create=extend_schema(
        summary="Ajouter une pièce jointe à un véhicule",
        description="Permission : AGENT_SAISIE uniquement.",
        request=DocumentCreateSerializer,
        responses={
            201: DocumentReadSerializer,
            400: OpenApiResponse(description="Données ou fichier invalides."),
            403: OpenApiResponse(description="Rôle non autorisé."),
        },
    ),
    partial_update=extend_schema(
        summary="Modifier les métadonnées d'une pièce jointe",
        description=(
            "Permission : AGENT_SAISIE uniquement. Le fichier et le véhicule "
            "ne sont pas modifiables par PATCH."
        ),
        request=DocumentUpdateSerializer,
        responses={
            200: DocumentReadSerializer,
            400: OpenApiResponse(description="Données invalides."),
            403: OpenApiResponse(description="Rôle non autorisé."),
        },
    ),
)
class DocumentViewSet(ModelViewSet):
    permission_classes = [DocumentPermission]
    pagination_class = DocumentPagination
    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    filterset_fields = (
        "vehicle",
        "document_type",
        "uploaded_by",
    )
    search_fields = (
        "title",
        "description",
        "original_filename",
        "vehicle__plate_number",
    )

    def get_queryset(self):
        queryset = (
            Document.objects
            .select_related(
                "vehicle",
                "uploaded_by",
                "uploaded_by__person",
            )
            .order_by("-created_at", "-id")
        )

        vehicle_id = self.request.query_params.get("vehicle")
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        document_type = self.request.query_params.get("document_type")
        if document_type:
            queryset = queryset.filter(document_type=document_type)

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentCreateSerializer
        if self.action == "partial_update":
            return DocumentUpdateSerializer
        return DocumentReadSerializer

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @extend_schema(
        summary="Télécharger une pièce jointe",
        responses={
            200: OpenApiResponse(description="Flux binaire du fichier."),
            404: OpenApiResponse(
                description="Document ou fichier introuvable."
            ),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="download",
    )
    def download(self, request, pk=None):
        document = self.get_object()

        if not document.file:
            raise NotFound(
                "Aucun fichier n'est associé à ce document."
            )

        try:
            document.file.open("rb")
        except (FileNotFoundError, OSError):
            raise NotFound(
                "Le fichier associé à ce document est introuvable."
            )

        filename = (
            document.original_filename
            or Path(document.file.name).name
        )

        return FileResponse(
            document.file,
            as_attachment=True,
            filename=filename,
            content_type=(
                document.mime_type
                or "application/octet-stream"
            ),
        )
