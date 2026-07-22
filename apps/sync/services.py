import hashlib
import json
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.cache import invalidate_statistics_cache

from .handlers import (
    EntitySyncHandler,
    SyncConfigurationError,
    SyncConflictError,
    SyncHandlerError,
)
from .models import SyncDevice, SyncItemLog, SyncSession


logger = logging.getLogger(__name__)


def canonical_hash(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_owned_active_device(*, user, device_uuid):
    try:
        return SyncDevice.objects.get(
            user=user,
            device_uuid=device_uuid,
            is_active=True,
            revoked_at__isnull=True,
        )
    except SyncDevice.DoesNotExist as exc:
        raise ValidationError(
            {
                "device_uuid": (
                    "Appareil inconnu, inactif ou révoqué. "
                    "Enregistrez-le avant la synchronisation."
                )
            }
        ) from exc


def register_device(*, user, validated_data):
    device_uuid = validated_data["device_uuid"]

    existing_other_user = SyncDevice.objects.filter(
        device_uuid=device_uuid
    ).exclude(user=user).exists()

    if existing_other_user:
        raise ValidationError(
            {
                "device_uuid": (
                    "Cet appareil est déjà associé à un autre compte."
                )
            }
        )

    device, _ = SyncDevice.objects.update_or_create(
        user=user,
        device_uuid=device_uuid,
        defaults={
            "device_name": validated_data.get("device_name", ""),
            "platform": validated_data.get(
                "platform",
                SyncDevice.Platform.ANDROID,
            ),
            "app_version": validated_data.get("app_version", ""),
            "last_seen_at": timezone.now(),
            "is_active": True,
            "revoked_at": None,
            "revoked_by": None,
        },
    )
    return device


def _get_existing_session(*, request_uuid, user, direction):
    session = (
        SyncSession.objects
        .filter(
            request_uuid=request_uuid,
            user=user,
            direction=direction,
        )
        .prefetch_related("items")
        .first()
    )
    return session


def _create_session(
    *,
    request_uuid,
    device,
    user,
    direction,
    item_count,
    cursor=None,
    payload_hash="",
):
    try:
        return SyncSession.objects.create(
            request_uuid=request_uuid,
            device=device,
            user=user,
            direction=direction,
            status=SyncSession.Status.PROCESSING,
            item_count=item_count,
            cursor=cursor,
            payload_hash=payload_hash,
        )
    except IntegrityError:
        session = SyncSession.objects.filter(
            request_uuid=request_uuid
        ).first()

        if (
            session
            and session.user_id == user.id
            and session.direction == direction
        ):
            return session

        raise ValidationError(
            {
                "request_uuid": (
                    "Cet identifiant de requête est déjà utilisé "
                    "pour une autre synchronisation."
                )
            }
        )


def process_push(*, user, request, validated_data):
    request_uuid = validated_data["request_uuid"]
    items = validated_data["items"]
    device = get_owned_active_device(
        user=user,
        device_uuid=validated_data["device_uuid"],
    )
    device.last_seen_at = timezone.now()
    device.save(update_fields=("last_seen_at", "updated_at"))

    payload_hash = canonical_hash(validated_data)
    existing = _get_existing_session(
        request_uuid=request_uuid,
        user=user,
        direction=SyncSession.Direction.PUSH,
    )

    if existing:
        if existing.payload_hash and existing.payload_hash != payload_hash:
            raise ValidationError(
                {
                    "request_uuid": (
                        "La même requête UUID a déjà été utilisée "
                        "avec un contenu différent."
                    )
                }
            )
        return existing, False

    session = _create_session(
        request_uuid=request_uuid,
        device=device,
        user=user,
        direction=SyncSession.Direction.PUSH,
        item_count=len(items),
        payload_hash=payload_hash,
    )

    if session.status != SyncSession.Status.PROCESSING:
        return session, False

    success_count = 0
    failure_count = 0
    conflict_count = 0
    changed_business_data = False

    for item in items:
        item_hash = canonical_hash(item["data"])
        item_log = SyncItemLog.objects.create(
            session=session,
            entity_type=item["entity_type"],
            operation=item["operation"],
            client_uuid=item["client_uuid"],
            base_version=item.get("base_version"),
            payload_hash=item_hash,
        )

        try:
            handler = EntitySyncHandler(item["entity_type"])

            # Une transaction par élément évite qu'une erreur bloque tout le lot.
            with transaction.atomic():
                result = handler.push(
                    operation=item["operation"],
                    client_uuid=item["client_uuid"],
                    data=item["data"],
                    base_version=item.get("base_version"),
                    user=user,
                    request=request,
                )

                instance = result["instance"]
                item_log.mark(
                    status=result["status"],
                    server_id=instance.pk,
                    server_version=result.get("server_version"),
                )

            if result["status"] == SyncItemLog.Status.DUPLICATE:
                success_count += 1
            else:
                success_count += 1
                changed_business_data = True

        except SyncConflictError as exc:
            conflict_count += 1
            item_log.mark(
                status=SyncItemLog.Status.CONFLICT,
                error_code=exc.code,
                error_message=str(exc),
            )

        except (
            ValidationError,
            SyncHandlerError,
            ValueError,
            TypeError,
        ) as exc:
            failure_count += 1
            detail = getattr(exc, "detail", None)
            message = (
                json.dumps(detail, default=str, ensure_ascii=False)
                if detail is not None
                else str(exc)
            )
            item_log.mark(
                status=SyncItemLog.Status.FAILED,
                error_code=getattr(
                    exc,
                    "code",
                    "VALIDATION_ERROR",
                ),
                error_message=message[:500],
            )

        except Exception:
            failure_count += 1
            logger.exception(
                "event=sync_item_unexpected_error "
                "request_uuid=%s entity_type=%s client_uuid=%s",
                request_uuid,
                item["entity_type"],
                item["client_uuid"],
            )
            item_log.mark(
                status=SyncItemLog.Status.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=(
                    "Une erreur interne est survenue pendant "
                    "le traitement de cet élément."
                ),
            )

    if failure_count == 0 and conflict_count == 0:
        final_status = SyncSession.Status.SUCCESS
    elif success_count > 0:
        final_status = SyncSession.Status.PARTIAL_SUCCESS
    else:
        final_status = SyncSession.Status.FAILED

    session.finish(
        status=final_status,
        success_count=success_count,
        failure_count=failure_count,
        conflict_count=conflict_count,
    )

    if changed_business_data:
        transaction.on_commit(invalidate_statistics_cache)

    return session, True


def process_pull(*, user, request, validated_data):
    request_uuid = validated_data["request_uuid"]
    cursor = validated_data.get("cursor")
    entity_types = validated_data.get("entity_types") or [
        SyncItemLog.EntityType.TICKET,
        SyncItemLog.EntityType.VERBALIZATION,
        SyncItemLog.EntityType.DELIT_CASE,
    ]
    limit = validated_data["limit"]

    device = get_owned_active_device(
        user=user,
        device_uuid=validated_data["device_uuid"],
    )
    device.last_seen_at = timezone.now()
    device.save(update_fields=("last_seen_at", "updated_at"))

    payload_hash = canonical_hash(validated_data)
    existing = _get_existing_session(
        request_uuid=request_uuid,
        user=user,
        direction=SyncSession.Direction.PULL,
    )

    if existing:
        if existing.payload_hash and existing.payload_hash != payload_hash:
            raise ValidationError(
                {
                    "request_uuid": (
                        "La même requête UUID a déjà été utilisée "
                        "avec un contenu différent."
                    )
                }
            )
        session = existing
        was_created = False
    else:
        session = _create_session(
            request_uuid=request_uuid,
            device=device,
            user=user,
            direction=SyncSession.Direction.PULL,
            item_count=0,
            cursor=cursor,
            payload_hash=payload_hash,
        )
        was_created = True

    output = []
    newest_cursor = cursor

    for entity_type in entity_types:
        handler = EntitySyncHandler(entity_type)
        remaining = limit - len(output)
        if remaining <= 0:
            break

        queryset = handler.pull_queryset(
            user=user,
            cursor=cursor,
        )[:remaining]

        for instance in queryset:
            updated_at = handler.updated_at(instance)
            output.append(
                {
                    "entity_type": entity_type,
                    "operation": SyncItemLog.Operation.UPSERT,
                    "server_id": str(instance.pk),
                    "client_uuid": str(
                        getattr(instance, "client_uuid", "")
                    ),
                    "updated_at": updated_at,
                    "data": handler.serialize_for_pull(
                        instance,
                        request,
                    ),
                }
            )
            if updated_at and (
                newest_cursor is None
                or updated_at > newest_cursor
            ):
                newest_cursor = updated_at

    session.item_count = len(output)
    session.save(update_fields=("item_count", "updated_at"))
    session.finish(
        status=SyncSession.Status.SUCCESS,
        success_count=len(output),
        next_cursor=newest_cursor or timezone.now(),
    )
    return session, output, was_created
