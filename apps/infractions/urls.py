from rest_framework.routers import DefaultRouter
from .views import InfractionViewSet

router = DefaultRouter()
router.register("", InfractionViewSet, basename="infraction")
urlpatterns = router.urls
