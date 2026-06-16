from rest_framework.routers import DefaultRouter

from .views import InsurancePolicyViewSet

router = DefaultRouter()
router.register("", InsurancePolicyViewSet, basename="insurance")
urlpatterns = router.urls

