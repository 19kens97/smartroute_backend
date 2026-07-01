import logging

from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.core.api import api_response
from .models import Infraction
from .serializers import InfractionSerializer
from .services import get_active_infraction_catalog, invalidate_infraction_catalog_cache

logger = logging.getLogger(__name__)


class InfractionViewSet(ModelViewSet):
    queryset = Infraction.objects.all().order_by("display_order", "code")
    serializer_class = InfractionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            return qs.filter(active=True)
        return qs

    def list(self, request, *args, **kwargs):
        logger.info("event=infraction_catalog_requested request_id=%s user_id=%s", getattr(request, "request_id", "-"), request.user.pk)
        return api_response(True, "Catalogue des infractions", get_active_infraction_catalog(request=request))

    def perform_create(self, serializer):
        instance = serializer.save()
        transaction.on_commit(invalidate_infraction_catalog_cache)
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        transaction.on_commit(invalidate_infraction_catalog_cache)
        return instance

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])
        transaction.on_commit(invalidate_infraction_catalog_cache)
