from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.core.api import api_response

from .models import Infraction
from .permissions import CanReadInfractionCatalog
from .serializers import InfractionSerializer
from .services import get_active_infraction_catalog


class InfractionViewSet(ReadOnlyModelViewSet):
    serializer_class = InfractionSerializer
    permission_classes = [
        CanReadInfractionCatalog
    ]
    pagination_class = None
    http_method_names = [
        "get",
        "head",
        "options",
    ]

    def get_queryset(self):
        return (
            Infraction.objects
            .filter(active=True)
            .order_by(
                "display_order",
                "code",
            )
        )

    def list(self, request, *args, **kwargs):
        return api_response(
            True,
            "Catalogue des infractions",
            get_active_infraction_catalog(
                request=request
            ),
        )
