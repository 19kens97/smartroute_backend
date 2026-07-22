from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.api import api_response

from .models import VehicleOwnership
from .pagination import OwnersPagination
from .permissions import OwnersPermission
from .serializers import (
    EndVehicleOwnershipSerializer,
    OwnerSerializer,
    VehicleOwnershipSerializer,
)
from .services import (
    filter_owners,
    filter_ownerships,
    ownerships_queryset,
    owners_queryset,
)


class OwnerViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    serializer_class = OwnerSerializer
    permission_classes = [OwnersPermission]
    pagination_class = OwnersPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return filter_owners(
            owners_queryset(),
            self.request.query_params,
        )

    @action(detail=True, methods=["get"])
    def vehicles(self, request, pk=None):
        owner = self.get_object()
        queryset = ownerships_queryset().filter(owner=owner)
        queryset = filter_ownerships(queryset, request.query_params)
        page = self.paginate_queryset(queryset)
        serializer = VehicleOwnershipSerializer(
            page,
            many=True,
            context={"request": request},
        )
        return self.get_paginated_response(serializer.data)


class VehicleOwnershipViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    GenericViewSet,
):
    serializer_class = VehicleOwnershipSerializer
    permission_classes = [OwnersPermission]
    pagination_class = OwnersPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return filter_ownerships(
            ownerships_queryset(),
            self.request.query_params,
        )

    @action(detail=True, methods=["post"], url_path="end")
    def end_ownership(self, request, pk=None):
        ownership = self.get_object()
        serializer = EndVehicleOwnershipSerializer(
            data=request.data,
            context={
                "request": request,
                "ownership": ownership,
            },
        )
        serializer.is_valid(raise_exception=True)
        ownership = serializer.save()

        return api_response(
            True,
            "Propriété terminée.",
            VehicleOwnershipSerializer(
                ownership,
                context={"request": request},
            ).data,
            status_code=status.HTTP_200_OK,
        )
