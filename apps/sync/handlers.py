from dataclasses import dataclass
from importlib import import_module

from django.conf import settings
from django.db.models import Model
from rest_framework.exceptions import ValidationError

from .models import SyncItemLog


class SyncHandlerError(Exception):
    code = "SYNC_HANDLER_ERROR"


class SyncConfigurationError(SyncHandlerError):
    code = "SYNC_CONFIGURATION_ERROR"


class SyncConflictError(SyncHandlerError):
    code = "SYNC_CONFLICT"


class SyncUnsupportedEntityError(SyncHandlerError):
    code = "UNSUPPORTED_ENTITY"


def import_string(path):
    module_path, attribute = path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, attribute)


@dataclass(frozen=True)
class EntitySyncConfig:
    model: str
    serializer: str
    create_actor_field: str | None = None
    owner_field: str | None = None
    updated_at_field: str = "updated_at"
    version_field: str | None = None
    pull_enabled: bool = True
    push_enabled: bool = True


DEFAULT_ENTITY_CONFIG = {
    SyncItemLog.EntityType.TICKET: EntitySyncConfig(
        model="apps.tickets.models.Ticket",
        serializer="apps.tickets.serializers.TicketSerializer",
        create_actor_field="opened_by",
        owner_field="opened_by",
    ),
    SyncItemLog.EntityType.VERBALIZATION: EntitySyncConfig(
        model="apps.tickets.models.TicketVerbalization",
        serializer=(
            "apps.tickets.serializers."
            "TicketVerbalizationSerializer"
        ),
        create_actor_field="agent",
        owner_field="agent",
    ),
    SyncItemLog.EntityType.DELIT_CASE: EntitySyncConfig(
        model="apps.delits.models.DelitCase",
        serializer="apps.delits.serializers.DelitCaseSerializer",
        create_actor_field="detected_by",
        owner_field="detected_by",
    ),
    # Les preuves contiennent des fichiers et doivent être envoyées via
    # leurs endpoints multipart dédiés. Elles restent disponibles en PULL.
    SyncItemLog.EntityType.TICKET_PROOF: EntitySyncConfig(
        model="apps.tickets.models.TicketProof",
        serializer="apps.tickets.serializers.TicketProofSerializer",
        owner_field="created_by",
        pull_enabled=True,
        push_enabled=False,
    ),
    SyncItemLog.EntityType.DELIT_EVIDENCE: EntitySyncConfig(
        model="apps.delits.models.DelitEvidence",
        serializer="apps.delits.serializers.DelitEvidenceSerializer",
        owner_field="created_by",
        pull_enabled=True,
        push_enabled=False,
    ),
}


def get_entity_config(entity_type):
    custom = getattr(settings, "SYNC_ENTITY_CONFIG", {})
    value = custom.get(entity_type)

    if value:
        return EntitySyncConfig(**value)

    try:
        return DEFAULT_ENTITY_CONFIG[entity_type]
    except KeyError as exc:
        raise SyncUnsupportedEntityError(
            f"Type d'entité non supporté : {entity_type}."
        ) from exc


class EntitySyncHandler:
    def __init__(self, entity_type):
        self.entity_type = entity_type
        self.config = get_entity_config(entity_type)

        try:
            self.model = import_string(self.config.model)
            self.serializer_class = import_string(
                self.config.serializer
            )
        except (ImportError, AttributeError, ValueError) as exc:
            raise SyncConfigurationError(
                f"Configuration invalide pour {entity_type}: {exc}"
            ) from exc

        if not isinstance(self.model, type) or not issubclass(
            self.model,
            Model,
        ):
            raise SyncConfigurationError(
                f"{self.config.model} n'est pas un modèle Django."
            )

    def get_instance(self, client_uuid):
        try:
            return self.model.objects.get(client_uuid=client_uuid)
        except self.model.DoesNotExist:
            return None

    def _server_version(self, instance):
        if not instance:
            return None

        if self.config.version_field:
            return getattr(
                instance,
                self.config.version_field,
                None,
            )

        updated_at = getattr(
            instance,
            self.config.updated_at_field,
            None,
        )
        return (
            int(updated_at.timestamp() * 1_000_000)
            if updated_at
            else None
        )

    def _check_conflict(self, instance, base_version):
        if instance is None or base_version is None:
            return

        server_version = self._server_version(instance)
        if server_version and base_version != server_version:
            raise SyncConflictError(
                "La donnée du serveur a été modifiée depuis "
                "la dernière version connue par l'appareil."
            )

    def push(
        self,
        *,
        operation,
        client_uuid,
        data,
        base_version,
        user,
        request,
    ):
        if not self.config.push_enabled:
            raise SyncUnsupportedEntityError(
                "Cette entité doit être envoyée par son endpoint "
                "multipart dédié."
            )

        instance = self.get_instance(client_uuid)

        if operation == SyncItemLog.Operation.CREATE:
            if instance is not None:
                return {
                    "status": SyncItemLog.Status.DUPLICATE,
                    "instance": instance,
                    "server_version": self._server_version(instance),
                }

            payload = dict(data)
            payload["client_uuid"] = str(client_uuid)
            serializer = self.serializer_class(
                data=payload,
                context={
                    "request": request,
                    "sync": True,
                },
            )
            serializer.is_valid(raise_exception=True)
            save_kwargs = {}
            if self.config.create_actor_field:
                save_kwargs[self.config.create_actor_field] = user
            instance = serializer.save(**save_kwargs)

        elif operation in {
            SyncItemLog.Operation.UPDATE,
            SyncItemLog.Operation.UPSERT,
        }:
            if instance is None:
                if operation == SyncItemLog.Operation.UPDATE:
                    raise ValidationError(
                        {
                            "client_uuid": (
                                "Aucune donnée serveur ne correspond "
                                "à cet identifiant client."
                            )
                        }
                    )

                payload = dict(data)
                payload["client_uuid"] = str(client_uuid)
                serializer = self.serializer_class(
                    data=payload,
                    context={
                        "request": request,
                        "sync": True,
                    },
                )
                serializer.is_valid(raise_exception=True)
                save_kwargs = {}
                if self.config.create_actor_field:
                    save_kwargs[self.config.create_actor_field] = user
                instance = serializer.save(**save_kwargs)
            else:
                self._check_conflict(instance, base_version)
                serializer = self.serializer_class(
                    instance,
                    data=data,
                    partial=True,
                    context={
                        "request": request,
                        "sync": True,
                    },
                )
                serializer.is_valid(raise_exception=True)
                instance = serializer.save()
        else:
            raise SyncUnsupportedEntityError(
                f"Opération non supportée : {operation}."
            )

        return {
            "status": SyncItemLog.Status.SUCCESS,
            "instance": instance,
            "server_version": self._server_version(instance),
        }

    def pull_queryset(self, *, user, cursor):
        if not self.config.pull_enabled:
            return self.model.objects.none()

        queryset = self.model.objects.all()

        if cursor:
            queryset = queryset.filter(
                **{
                    f"{self.config.updated_at_field}__gt": cursor
                }
            )

        # Par défaut, les données opérationnelles restent limitées à leur
        # auteur lorsque le modèle possède le champ configuré.
        if self.config.owner_field:
            field_names = {
                field.name
                for field in self.model._meta.get_fields()
            }
            if self.config.owner_field in field_names:
                queryset = queryset.filter(
                    **{self.config.owner_field: user}
                )

        return queryset.order_by(
            self.config.updated_at_field,
            "pk",
        )

    def serialize_for_pull(self, instance, request):
        serializer = self.serializer_class(
            instance,
            context={
                "request": request,
                "sync": True,
            },
        )
        return serializer.data

    def updated_at(self, instance):
        return getattr(
            instance,
            self.config.updated_at_field,
            None,
        )
