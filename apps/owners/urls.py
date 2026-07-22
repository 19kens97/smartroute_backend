from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OwnerViewSet, VehicleOwnershipViewSet


router = DefaultRouter()
router.register("owners", OwnerViewSet, basename="owner")
router.register(
    "vehicle-ownerships",
    VehicleOwnershipViewSet,
    basename="vehicle-ownership",
)

app_name = "owners"

urlpatterns = [
    path("", include(router.urls)),
]
