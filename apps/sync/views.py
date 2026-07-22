import logging

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api import api_response

from .models import SyncDevice, SyncSession
from .permissions import SyncPermission
from .serializers import (
    SyncDeviceRegisterSerializer,
    SyncDeviceRevokeSerializer,
    SyncDeviceSerializer,
    SyncPullRequestSerializer,
    SyncPushRequestSerializer,
    SyncSessionSerializer,
    SyncStatusQuerySerializer,
)
from .services import (
    get_owned_active_device,
    process_pull,
    process_push,
    register_device,
)


logger = logging.getLogger(__name__)


class SyncBaseView(APIView):
    permission_classes = [SyncPermission]

    def enforce_request_size(self, request):
        maximum = getattr(
            settings,
            "SYNC_MAX_JSON_BYTES",
            2 * 1024 * 1024,
        )
        content_length = request.META.get("CONTENT_LENGTH")

        if content_length:
            try:
                size = int(content_length)
            except (TypeError, ValueError):
                size = 0

            if size > maximum:
                raise ValidationError(
                    {
                        "payload": (
                            f"La requête dépasse la limite de "
                            f"{maximum} octets."
                        )
                    }
                )


class SyncDeviceRegisterView(SyncBaseView):
    def post(self, request):
        serializer = SyncDeviceRegisterSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        device = register_device(
            user=request.user,
            validated_data=serializer.validated_data,
        )

        logger.info(
            "event=sync_device_registered "
            "request_id=%s user_id=%s device_uuid=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            device.device_uuid,
        )

        return api_response(
            True,
            "Appareil enregistré.",
            SyncDeviceSerializer(device).data,
        )


class SyncDeviceRevokeView(SyncBaseView):
    def post(self, request):
        serializer = SyncDeviceRevokeSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        device = get_owned_active_device(
            user=request.user,
            device_uuid=serializer.validated_data[
                "device_uuid"
            ],
        )
        device.revoke(actor=request.user)

        logger.info(
            "event=sync_device_revoked "
            "request_id=%s user_id=%s device_uuid=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            device.device_uuid,
        )

        return api_response(
            True,
            "Appareil révoqué.",
            SyncDeviceSerializer(device).data,
        )


class SyncPushView(SyncBaseView):
    def post(self, request):
        self.enforce_request_size(request)

        serializer = SyncPushRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        session, created = process_push(
            user=request.user,
            request=request,
            validated_data=serializer.validated_data,
        )
        session.refresh_from_db()

        logger.info(
            "event=sync_push_completed "
            "request_id=%s user_id=%s request_uuid=%s "
            "status=%s created=%s item_count=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            session.request_uuid,
            session.status,
            created,
            session.item_count,
        )

        return api_response(
            True,
            (
                "Synchronisation traitée."
                if created
                else "Résultat idempotent retourné."
            ),
            SyncSessionSerializer(session).data,
        )


class SyncPullView(SyncBaseView):
    def post(self, request):
        self.enforce_request_size(request)

        serializer = SyncPullRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        session, items, created = process_pull(
            user=request.user,
            request=request,
            validated_data=serializer.validated_data,
        )

        logger.info(
            "event=sync_pull_completed "
            "request_id=%s user_id=%s request_uuid=%s "
            "item_count=%s created=%s",
            getattr(request, "request_id", "-"),
            request.user.pk,
            session.request_uuid,
            len(items),
            created,
        )

        return api_response(
            True,
            (
                "Données de synchronisation prêtes."
                if created
                else "Résultat idempotent recalculé."
            ),
            {
                "request_uuid": str(session.request_uuid),
                "status": session.status,
                "cursor": session.cursor,
                "next_cursor": session.next_cursor,
                "has_more": len(items)
                == serializer.validated_data["limit"],
                "items": items,
            },
        )


class SyncStatusView(SyncBaseView):
    def get(self, request):
        serializer = SyncStatusQuerySerializer(
            data=request.query_params
        )
        serializer.is_valid(raise_exception=True)

        try:
            session = (
                SyncSession.objects
                .select_related("device")
                .prefetch_related("items")
                .get(
                    request_uuid=serializer.validated_data[
                        "request_uuid"
                    ],
                    user=request.user,
                )
            )
        except SyncSession.DoesNotExist as exc:
            raise ValidationError(
                {
                    "request_uuid": (
                        "Aucune synchronisation ne correspond "
                        "à cet identifiant pour cet utilisateur."
                    )
                }
            ) from exc

        return api_response(
            True,
            "État de synchronisation.",
            SyncSessionSerializer(session).data,
        )


class SyncDevicesView(SyncBaseView):
    def get(self, request):
        devices = SyncDevice.objects.filter(
            user=request.user
        ).order_by("-last_seen_at", "-id")

        return api_response(
            True,
            "Appareils de synchronisation.",
            SyncDeviceSerializer(
                devices,
                many=True,
            ).data,
        )
