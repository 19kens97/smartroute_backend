from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from apps.core.api import api_response
from .models import SyncLog

class SyncPushView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        client_uuid = request.data.get("client_uuid")
        SyncLog.objects.create(client_uuid=client_uuid, user=request.user, direction="PUSH", payload=request.data)
        return api_response(True, "Sync push received", {"client_uuid": client_uuid})

class SyncPullView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        client_uuid = request.data.get("client_uuid")
        SyncLog.objects.create(client_uuid=client_uuid, user=request.user, direction="PULL", payload=request.data)
        return api_response(True, "Sync pull ready", {"items": []})

class SyncStatusView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        client_uuid = request.query_params.get("client_uuid")
        logs = SyncLog.objects.filter(client_uuid=client_uuid).order_by("-id")[:10]
        return api_response(True, "Sync status", {"count": len(logs), "last_status": logs[0].status if logs else None})
