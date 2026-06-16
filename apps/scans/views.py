from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from apps.core.api import api_response
from .models import Scan
from .serializers import ScanSerializer

class ScanViewSet(ReadOnlyModelViewSet):
    queryset = Scan.objects.select_related("agent").all().order_by("-id")
    serializer_class = ScanSerializer
    permission_classes = [IsAuthenticated]

class RecognizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not getattr(settings, "ENABLE_RECOGNIZE_ENDPOINT", False):
            return api_response(False, "Future endpoint disabled in MVP", {}, {"detail": "Not enabled"}, 501)
        return api_response(True, "Recognized", {"plate_number": "DEMO123"})
