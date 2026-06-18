from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import RecognizeView, ScanViewSet, extract_license_plate, search_plate

router = DefaultRouter()
router.register("", ScanViewSet, basename="scan")
urlpatterns = [
	path("recognize/", RecognizeView.as_view()),
	path("scan-plate/", extract_license_plate),
	path("search/", search_plate),
] + router.urls
