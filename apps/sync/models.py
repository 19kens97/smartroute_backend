import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class SyncDevice(TimeStampedModel):
    class Platform(models.TextChoices):
        ANDROID = "ANDROID", "Android"
        IOS = "IOS", "iOS"
        WEB = "WEB", "Web"
        OTHER = "OTHER", "Autre"

    device_uuid = models.UUIDField(unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sync_devices",
    )
    device_name = models.CharField(max_length=120, blank=True, default="")
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.ANDROID,
    )
    app_version = models.CharField(max_length=40, blank=True, default="")
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="revoked_sync_devices",
    )

    class Meta:
        ordering = ("-last_seen_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "device_uuid"),
                name="unique_sync_device_per_user",
            )
        ]

    def clean(self):
        super().clean()
        self.device_name = (self.device_name or "").strip()
        self.app_version = (self.app_version or "").strip()

        if self.revoked_at and self.is_active:
            raise ValidationError(
                {"is_active": "Un appareil révoqué ne peut pas rester actif."}
            )

    def revoke(self, *, actor):
        self.is_active = False
        self.revoked_at = timezone.now()
        self.revoked_by = actor
        self.save(
            update_fields=(
                "is_active",
                "revoked_at",
                "revoked_by",
                "updated_at",
            )
        )

    def __str__(self):
        return f"{self.user_id} - {self.device_uuid}"


class SyncSession(TimeStampedModel):
    class Direction(models.TextChoices):
        PUSH = "PUSH", "Envoi"
        PULL = "PULL", "Réception"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        PROCESSING = "PROCESSING", "En traitement"
        SUCCESS = "SUCCESS", "Réussi"
        PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partiellement réussi"
        FAILED = "FAILED", "Échec"

    request_uuid = models.UUIDField(unique=True, db_index=True)
    device = models.ForeignKey(
        SyncDevice,
        on_delete=models.PROTECT,
        related_name="sync_sessions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sync_sessions",
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    cursor = models.DateTimeField(null=True, blank=True)
    next_cursor = models.DateTimeField(null=True, blank=True)
    item_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    payload_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("user", "device", "direction", "status"),
                name="sync_session_lookup_idx",
            )
        ]

    def clean(self):
        super().clean()
        if self.device_id and self.user_id and self.device.user_id != self.user_id:
            raise ValidationError(
                {"device": "Cet appareil n'appartient pas à cet utilisateur."}
            )

    def finish(
        self,
        *,
        status,
        success_count=0,
        failure_count=0,
        conflict_count=0,
        next_cursor=None,
        error_code="",
        error_message="",
    ):
        self.status = status
        self.success_count = success_count
        self.failure_count = failure_count
        self.conflict_count = conflict_count
        self.next_cursor = next_cursor
        self.error_code = error_code
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(
            update_fields=(
                "status",
                "success_count",
                "failure_count",
                "conflict_count",
                "next_cursor",
                "error_code",
                "error_message",
                "completed_at",
                "updated_at",
            )
        )

    def __str__(self):
        return f"{self.direction} - {self.request_uuid}"


class SyncItemLog(TimeStampedModel):
    class EntityType(models.TextChoices):
        TICKET = "TICKET", "Procès-verbal"
        VERBALIZATION = "VERBALIZATION", "Verbalisation"
        TICKET_PROOF = "TICKET_PROOF", "Preuve de verbalisation"
        DELIT_CASE = "DELIT_CASE", "Dossier de délit"
        DELIT_EVIDENCE = "DELIT_EVIDENCE", "Preuve de délit"

    class Operation(models.TextChoices):
        CREATE = "CREATE", "Création"
        UPDATE = "UPDATE", "Mise à jour"
        UPSERT = "UPSERT", "Création ou mise à jour"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SUCCESS = "SUCCESS", "Réussi"
        FAILED = "FAILED", "Échec"
        CONFLICT = "CONFLICT", "Conflit"
        DUPLICATE = "DUPLICATE", "Doublon"

    session = models.ForeignKey(
        SyncSession,
        on_delete=models.CASCADE,
        related_name="items",
    )
    entity_type = models.CharField(max_length=30, choices=EntityType.choices)
    operation = models.CharField(max_length=10, choices=Operation.choices)
    client_uuid = models.UUIDField(db_index=True)
    server_id = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    base_version = models.PositiveIntegerField(null=True, blank=True)
    server_version = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    payload_hash = models.CharField(max_length=64, blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("session", "entity_type", "client_uuid", "operation"),
                name="unique_item_per_sync_session",
            )
        ]
        indexes = [
            models.Index(
                fields=("entity_type", "client_uuid", "status"),
                name="sync_item_entity_uuid_idx",
            )
        ]

    def mark(
        self,
        *,
        status,
        server_id="",
        server_version=None,
        error_code="",
        error_message="",
    ):
        self.status = status
        self.server_id = str(server_id or "")
        self.server_version = server_version
        self.error_code = error_code
        self.error_message = error_message
        self.processed_at = timezone.now()
        self.save(
            update_fields=(
                "status",
                "server_id",
                "server_version",
                "error_code",
                "error_message",
                "processed_at",
                "updated_at",
            )
        )

    def __str__(self):
        return f"{self.entity_type} - {self.client_uuid}"
