import logging

from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.api import api_response
from apps.core.cache import invalidate_statistics_cache

from .models import SyncLog

logger = logging.getLogger(__name__)


class SyncPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        client_uuid = request.data.get("client_uuid")
        SyncLog.objects.create(client_uuid=client_uuid, user=request.user, direction="PUSH", payload=request.data)
        transaction.on_commit(invalidate_statistics_cache)
        logger.info("event=sync_push_received request_id=%s user_id=%s client_uuid=%s", getattr(request, "request_id", "-"), request.user.pk, client_uuid)
        return api_response(True, "Sync push received", {"client_uuid": client_uuid})


class SyncPullView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        client_uuid = request.data.get("client_uuid")
        SyncLog.objects.create(client_uuid=client_uuid, user=request.user, direction="PULL", payload=request.data)
        transaction.on_commit(invalidate_statistics_cache)
        logger.info("event=sync_pull_ready request_id=%s user_id=%s client_uuid=%s item_count=0", getattr(request, "request_id", "-"), request.user.pk, client_uuid)
        return api_response(True, "Sync pull ready", {"items": []})


class SyncStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client_uuid = request.query_params.get("client_uuid")
        logs = SyncLog.objects.filter(client_uuid=client_uuid).order_by("-id")[:10]
        logger.info("event=sync_status_loaded request_id=%s user_id=%s client_uuid=%s count=%s", getattr(request, "request_id", "-"), request.user.pk, client_uuid, len(logs))
        return api_response(True, "Sync status", {"count": len(logs), "last_status": logs[0].status if logs else None})
