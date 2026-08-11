import mimetypes

from django.http import FileResponse, Http404
from apps.accounts.permissions import IsAgentTerrain
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.core.api import api_response
from apps.core.openapi import ApiEnvelopeSerializer, ScanHistoryEnvelopeSerializer
from apps.gemini.views import extract_license_plate, get_last_scan, search_plate
from .models import GeminiScan, Scan
from .serializers import ScanSerializer


class ScanViewSet(ReadOnlyModelViewSet):
    queryset = Scan.objects.select_related("agent").all().order_by("-id")
    serializer_class = ScanSerializer
    permission_classes = [IsAgentTerrain]


class ScanHistoryView(APIView):
    permission_classes = [IsAgentTerrain]

    @extend_schema(responses={200: ScanHistoryEnvelopeSerializer}, tags=["scans"])
    def get(self, request):
        manual_scans = [
            {
                "id": f"manual-{scan.pk}",
                "agent": scan.agent_id,
                "plate_number": scan.plate_number,
                "source": "MANUAL",
                "created_at": scan.created_at,
                "updated_at": scan.updated_at,
                "image_url": None,
            }
            for scan in Scan.objects.filter(agent=request.user).order_by("-created_at", "-id")
        ]
        camera_scans = [
            {
                "id": f"scan-{scan.pk}",
                "agent": scan.agent_id,
                "plate_number": scan.plate_number,
                "source": "MOBILE_GEMINI",
                "created_at": scan.scanned_at,
                "updated_at": scan.updated_at,
                "image_url": f"/api/scans/history/{scan.pk}/image/" if scan.image else None,
            }
            for scan in GeminiScan.objects.filter(agent=request.user).only(
                "id", "agent_id", "plate_number", "scanned_at", "updated_at", "image"
            ).order_by("-scanned_at", "-id")
        ]
        results = sorted(
            [*manual_scans, *camera_scans],
            key=lambda item: (item["created_at"], item["id"]),
            reverse=True,
        )
        return api_response(True, "Historique des scans", results)


class ScanHistoryImageView(APIView):
    permission_classes = [IsAgentTerrain]

    @extend_schema(parameters=[OpenApiParameter("pk", OpenApiTypes.INT, OpenApiParameter.PATH)], responses={200: OpenApiResponse(response=OpenApiTypes.BINARY, description="Image du scan")}, tags=["scans"])
    def get(self, request, pk):
        scan = GeminiScan.objects.filter(pk=pk, agent=request.user).only("image").first()
        if scan is None or not scan.image:
            raise Http404
        content_type = mimetypes.guess_type(scan.image.name)[0] or "application/octet-stream"
        response = FileResponse(scan.image.open("rb"), content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        return response


class RecognizeView(APIView):
    permission_classes = [IsAgentTerrain]

    @extend_schema(request=None, responses={200: ApiEnvelopeSerializer, 501: ApiEnvelopeSerializer}, tags=["scans"])
    def post(self, request):
        from django.conf import settings

        if not getattr(settings, "ENABLE_RECOGNIZE_ENDPOINT", False):
            return api_response(False, "Future endpoint disabled in MVP", {}, {"detail": "Not enabled"}, 501)
        return api_response(True, "Recognized", {"plate_number": "DEMO123"})
