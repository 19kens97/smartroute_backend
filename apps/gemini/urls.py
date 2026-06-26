from django.urls import path
from .views import extract_license_plate, get_last_scan, search_plate

urlpatterns = [
    path('scan-plate/', extract_license_plate, name='lpr_extract'),
    path('last-scan/', get_last_scan, name='lpr_last_scan'),
    path('search-plate/', search_plate, name='lpr_search_plate'),
]
