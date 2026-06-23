from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
# Import gemini handler lazily in the view below to avoid heavy imports at startup

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

def gemini_scan_plate_view(request, *args, **kwargs):
    from apps.scans.views import extract_license_plate
    return extract_license_plate(request, *args, **kwargs)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/owners/", include("apps.owners.urls")),
    path("api/vehicles/", include("apps.vehicles.urls")),
    path("api/documents/", include("apps.documents.urls")),
    path("api/drivers/", include("apps.drivers.urls")),
    path("api/insurance/", include("apps.insurance.urls")),
    path("api/scans/", include("apps.scans.urls")),
    path("api/gemini/scan-plate/", gemini_scan_plate_view),
    path("api/infractions/", include("apps.infractions.urls")),
    path("api/tickets/", include("apps.tickets.urls")),
    path("api/alerts/", include("apps.alerts.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/sync/", include("apps.sync.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
