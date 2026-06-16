from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import RecognizeView, ScanViewSet

router = DefaultRouter()
router.register("", ScanViewSet, basename="scan")
urlpatterns = router.urls + [path("recognize/", RecognizeView.as_view())]
