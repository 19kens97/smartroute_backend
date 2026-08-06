from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

from django.db import connection, models
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.test_factories import create_agent_terrain_user
from apps.delits.models import DelitCase, DelitType
from apps.sync.handlers import (
    DEFAULT_ENTITY_CONFIG,
    EntitySyncConfig,
    EntitySyncHandler,
    SyncConfigurationError,
    SyncConflictError,
    SyncHandlerError,
    SyncUnsupportedEntityError,
    get_entity_config,
    import_string,
)
from apps.sync.models import SyncItemLog
from apps.tickets.models import Ticket


class HandlerConfigurationAdditionalTests(SimpleTestCase):
    def test_custom_exceptions_codes_and_inheritance(self):
        self.assertEqual(SyncHandlerError.code, "SYNC_HANDLER_ERROR")
        self.assertEqual(SyncConfigurationError.code, "SYNC_CONFIGURATION_ERROR")
        self.assertEqual(SyncConflictError.code, "SYNC_CONFLICT")
        self.assertEqual(SyncUnsupportedEntityError.code, "UNSUPPORTED_ENTITY")
        self.assertTrue(issubclass(SyncConfigurationError, SyncHandlerError))
        self.assertTrue(issubclass(SyncConflictError, SyncHandlerError))
        self.assertTrue(issubclass(SyncUnsupportedEntityError, SyncHandlerError))

    def test_import_string_valid_and_invalid_paths(self):
        self.assertIs(import_string("apps.tickets.models.Ticket"), Ticket)
        with self.assertRaises(ImportError):
            import_string("missing.module.Ticket")
        with self.assertRaises(AttributeError):
            import_string("apps.tickets.models.MissingTicket")
        with self.assertRaises(ValueError):
            import_string("InvalidPathWithoutDot")

    @patch("apps.sync.handlers.import_module")
    def test_import_string_splits_on_last_dot(self, mocked_import_module):
        module = SimpleNamespace(Target=object)
        mocked_import_module.return_value = module
        self.assertIs(import_string("pkg.sub.module.Target"), object)
        mocked_import_module.assert_called_once_with("pkg.sub.module")

    def test_entity_sync_config_defaults_and_immutability(self):
        config = EntitySyncConfig(model="apps.tickets.models.Ticket", serializer="apps.tickets.serializers.TicketSerializer")
        self.assertIsNone(config.create_actor_field)
        self.assertIsNone(config.owner_field)
        self.assertEqual(config.updated_at_field, "updated_at")
        self.assertIsNone(config.version_field)
        self.assertTrue(config.pull_enabled)
        self.assertTrue(config.push_enabled)
        with self.assertRaises(FrozenInstanceError):
            config.model = "changed"

    def test_default_entity_config_contains_expected_entities_and_flags(self):
        self.assertEqual(
            set(DEFAULT_ENTITY_CONFIG),
            {
                SyncItemLog.EntityType.TICKET,
                SyncItemLog.EntityType.VERBALIZATION,
                SyncItemLog.EntityType.TICKET_PROOF,
                SyncItemLog.EntityType.DELIT_CASE,
                SyncItemLog.EntityType.DELIT_EVIDENCE,
            },
        )
        ticket = DEFAULT_ENTITY_CONFIG[SyncItemLog.EntityType.TICKET]
        self.assertEqual(ticket.model, "apps.tickets.models.Ticket")
        self.assertEqual(ticket.serializer, "apps.tickets.serializers.TicketSerializer")
        self.assertEqual(ticket.create_actor_field, "opened_by")
        self.assertEqual(ticket.owner_field, "opened_by")
        verbalization = DEFAULT_ENTITY_CONFIG[SyncItemLog.EntityType.VERBALIZATION]
        self.assertEqual(verbalization.create_actor_field, "agent")
        self.assertEqual(verbalization.owner_field, "agent")
        delit = DEFAULT_ENTITY_CONFIG[SyncItemLog.EntityType.DELIT_CASE]
        self.assertEqual(delit.create_actor_field, "detected_by")
        self.assertEqual(delit.owner_field, "detected_by")
        for entity_type in (SyncItemLog.EntityType.TICKET_PROOF, SyncItemLog.EntityType.DELIT_EVIDENCE):
            self.assertTrue(DEFAULT_ENTITY_CONFIG[entity_type].pull_enabled)
            self.assertFalse(DEFAULT_ENTITY_CONFIG[entity_type].push_enabled)

    def test_get_entity_config_default_custom_override_and_invalid_values(self):
        self.assertEqual(get_entity_config(SyncItemLog.EntityType.TICKET), DEFAULT_ENTITY_CONFIG[SyncItemLog.EntityType.TICKET])

        custom_value = {
            "model": "apps.tickets.models.Ticket",
            "serializer": "apps.tickets.serializers.TicketSerializer",
            "owner_field": "opened_by",
            "pull_enabled": False,
        }
        with override_settings(SYNC_ENTITY_CONFIG={"CUSTOM": custom_value}):
            config = get_entity_config("CUSTOM")
        self.assertEqual(config.model, custom_value["model"])
        self.assertEqual(config.owner_field, "opened_by")
        self.assertFalse(config.pull_enabled)
        self.assertTrue(config.push_enabled)

        override = {
            "model": "apps.delits.models.DelitCase",
            "serializer": "apps.delits.serializers.DelitCaseSerializer",
        }
        with override_settings(SYNC_ENTITY_CONFIG={SyncItemLog.EntityType.TICKET: override}):
            self.assertEqual(get_entity_config(SyncItemLog.EntityType.TICKET).model, override["model"])

        with override_settings(SYNC_ENTITY_CONFIG={"BAD": {"model": "x", "serializer": "y", "unknown": True}}):
            with self.assertRaises(TypeError):
                get_entity_config("BAD")
        with override_settings(SYNC_ENTITY_CONFIG={"BAD": {"model": "x"}}):
            with self.assertRaises(TypeError):
                get_entity_config("BAD")
        with override_settings(SYNC_ENTITY_CONFIG={"BAD": "not-a-dict"}):
            with self.assertRaises(TypeError):
                get_entity_config("BAD")

    def test_get_entity_config_unknown_entity_raises_supported_error(self):
        with self.assertRaises(SyncUnsupportedEntityError) as ctx:
            get_entity_config("UNKNOWN_ENTITY")
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_ENTITY")
        self.assertIn("UNKNOWN_ENTITY", str(ctx.exception))


class HandlerInitAdditionalTests(SimpleTestCase):
    def test_valid_handler_imports_model_and_serializer(self):
        handler = EntitySyncHandler(SyncItemLog.EntityType.TICKET)
        self.assertEqual(handler.entity_type, SyncItemLog.EntityType.TICKET)
        self.assertEqual(handler.config, DEFAULT_ENTITY_CONFIG[SyncItemLog.EntityType.TICKET])
        self.assertIs(handler.model, Ticket)
        self.assertEqual(handler.serializer_class.__name__, "TicketSerializer")

    def test_invalid_model_import_errors_become_configuration_errors(self):
        for exc in (ImportError("missing"), AttributeError("attr"), ValueError("bad")):
            with self.subTest(exc=type(exc).__name__):
                with patch("apps.sync.handlers.import_string", side_effect=exc):
                    with self.assertRaises(SyncConfigurationError) as ctx:
                        EntitySyncHandler(SyncItemLog.EntityType.TICKET)
                self.assertIn(str(SyncItemLog.EntityType.TICKET), str(ctx.exception))
                self.assertIn(str(exc), str(ctx.exception))

    def test_invalid_serializer_import_errors_become_configuration_errors(self):
        for exc in (ImportError("missing serializer"), AttributeError("attr"), ValueError("bad")):
            with self.subTest(exc=type(exc).__name__):
                with patch("apps.sync.handlers.import_string", side_effect=[Ticket, exc]):
                    with self.assertRaises(SyncConfigurationError) as ctx:
                        EntitySyncHandler(SyncItemLog.EntityType.TICKET)
                self.assertIn("missing serializer" if isinstance(exc, ImportError) else str(exc), str(ctx.exception))

    def test_imported_model_must_be_django_model_class(self):
        with patch("apps.sync.handlers.import_string", side_effect=[object(), object]):
            with self.assertRaises(SyncConfigurationError) as ctx:
                EntitySyncHandler(SyncItemLog.EntityType.TICKET)
        self.assertIn("Django", str(ctx.exception))

        class PlainClass:
            pass

        with patch("apps.sync.handlers.import_string", side_effect=[PlainClass, object]):
            with self.assertRaises(SyncConfigurationError):
                EntitySyncHandler(SyncItemLog.EntityType.TICKET)


class FakeSerializer:
    last_instance = None

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.data = {"serialized": True}
        self.saved_with = None
        FakeSerializer.last_instance = self

    def is_valid(self, *, raise_exception=False):
        if self.kwargs.get("data", {}).get("invalid"):
            raise ValidationError({"invalid": "bad"})
        return True

    def save(self, **kwargs):
        self.saved_with = kwargs
        if self.kwargs.get("data", {}).get("explode"):
            raise RuntimeError("save failed")
        return SimpleNamespace(pk="saved", client_uuid=self.kwargs.get("data", {}).get("client_uuid"), version=1, updated_at=timezone.now(), modified_at=timezone.now())


class FakeModel(models.Model):
    client_uuid = models.UUIDField(unique=True)
    owner_marker = models.IntegerField(null=True, blank=True)
    version = models.IntegerField(null=True, blank=True)
    modified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "sync"


@override_settings(
    SYNC_ENTITY_CONFIG={
        "FAKE": {
            "model": "apps.sync.tests_handlers_additional.FakeModel",
            "serializer": "apps.sync.tests_handlers_additional.FakeSerializer",
            "create_actor_field": "owner",
            "version_field": "version",
            "updated_at_field": "modified_at",
        },
        "FAKE_NO_ACTOR": {
            "model": "apps.sync.tests_handlers_additional.FakeModel",
            "serializer": "apps.sync.tests_handlers_additional.FakeSerializer",
            "updated_at_field": "modified_at",
        },
        "FAKE_NO_OWNER_FIELD": {
            "model": "apps.sync.tests_handlers_additional.FakeModel",
            "serializer": "apps.sync.tests_handlers_additional.FakeSerializer",
            "owner_field": "missing_owner",
            "updated_at_field": "modified_at",
        },
        "FAKE_PULL_DISABLED": {
            "model": "apps.sync.tests_handlers_additional.FakeModel",
            "serializer": "apps.sync.tests_handlers_additional.FakeSerializer",
            "pull_enabled": False,
        },
        "FAKE_PUSH_DISABLED": {
            "model": "apps.sync.tests_handlers_additional.FakeModel",
            "serializer": "apps.sync.tests_handlers_additional.FakeSerializer",
            "push_enabled": False,
        },
    }
)
class EntitySyncHandlerAdditionalTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(FakeModel)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

    def setUp(self):
        self.user = create_agent_terrain_user(email="sync.handler.owner@example.com")
        self.other_user = create_agent_terrain_user(email="sync.handler.other@example.com")
        self.request = SimpleNamespace(user=self.user, build_absolute_uri=lambda path: f"http://testserver{path}")

    def create_fake(self, *, client_uuid=None, owner=None, version=1, modified_at=None):
        return FakeModel.objects.create(
            client_uuid=client_uuid or uuid.uuid4(),
            owner_marker=getattr(owner, "pk", owner),
            version=version,
            modified_at=modified_at if modified_at is not None else timezone.now(),
        )

    def test_get_instance_existing_missing_wrong_uuid_and_multiple_objects(self):
        handler = EntitySyncHandler("FAKE")
        first = self.create_fake(owner=self.user)
        second = self.create_fake(owner=self.user)
        self.assertEqual(handler.get_instance(first.client_uuid), first)
        self.assertEqual(handler.get_instance(second.client_uuid), second)
        self.assertIsNone(handler.get_instance(uuid.uuid4()))

    def test_server_version_uses_version_field_updated_at_custom_field_and_none_values(self):
        handler = EntitySyncHandler("FAKE")
        self.assertIsNone(handler._server_version(None))
        instance = SimpleNamespace(version=12, modified_at=timezone.now())
        self.assertEqual(handler._server_version(instance), 12)
        self.assertIsNone(handler._server_version(SimpleNamespace(modified_at=timezone.now())))

        no_version_handler = EntitySyncHandler("FAKE_NO_ACTOR")
        known = timezone.now()
        self.assertEqual(no_version_handler._server_version(SimpleNamespace(modified_at=known)), int(known.timestamp() * 1_000_000))
        self.assertIsNone(no_version_handler._server_version(SimpleNamespace()))
        self.assertIsNone(no_version_handler._server_version(SimpleNamespace(modified_at=None)))

    def test_check_conflict_ignores_missing_inputs_identical_version_none_and_zero_server_version(self):
        handler = EntitySyncHandler("FAKE")
        handler._check_conflict(None, 1)
        handler._check_conflict(SimpleNamespace(version=2), None)
        handler._check_conflict(SimpleNamespace(version=2), 2)
        handler._check_conflict(SimpleNamespace(version=None), 1)
        handler._check_conflict(SimpleNamespace(version=0), 1)
        with self.assertRaises(SyncConflictError) as ctx:
            handler._check_conflict(SimpleNamespace(version=3), 2)
        self.assertIn("serveur", str(ctx.exception))

    def test_push_disabled_entity_rejects_before_get_instance_or_serializer(self):
        handler = EntitySyncHandler("FAKE_PUSH_DISABLED")
        with patch.object(handler, "get_instance") as get_instance:
            with self.assertRaises(SyncUnsupportedEntityError) as ctx:
                handler.push(
                    operation=SyncItemLog.Operation.CREATE,
                    client_uuid=uuid.uuid4(),
                    data={},
                    base_version=None,
                    user=self.user,
                    request=self.request,
                )
        self.assertIn("multipart", str(ctx.exception))
        get_instance.assert_not_called()

    def test_create_push_creates_with_payload_copy_context_actor_and_success_result(self):
        handler = EntitySyncHandler("FAKE")
        client_uuid = uuid.uuid4()
        data = {"value": "initial"}
        result = handler.push(
            operation=SyncItemLog.Operation.CREATE,
            client_uuid=client_uuid,
            data=data,
            base_version=None,
            user=self.user,
            request=self.request,
        )
        serializer = FakeSerializer.last_instance
        self.assertEqual(data, {"value": "initial"})
        self.assertEqual(serializer.kwargs["data"]["client_uuid"], str(client_uuid))
        self.assertEqual(serializer.kwargs["context"], {"request": self.request, "sync": True})
        self.assertEqual(serializer.saved_with, {"owner": self.user})
        self.assertEqual(result["status"], SyncItemLog.Status.SUCCESS)
        self.assertEqual(result["instance"].pk, "saved")
        self.assertIsNotNone(result["server_version"])

    def test_create_push_without_actor_field_saves_without_kwargs(self):
        handler = EntitySyncHandler("FAKE_NO_ACTOR")
        result = handler.push(
            operation=SyncItemLog.Operation.CREATE,
            client_uuid=uuid.uuid4(),
            data={"value": "created"},
            base_version=None,
            user=self.user,
            request=self.request,
        )
        self.assertEqual(FakeSerializer.last_instance.saved_with, {})
        self.assertEqual(result["status"], SyncItemLog.Status.SUCCESS)

    def test_create_existing_returns_duplicate_without_serializer_validation(self):
        instance = self.create_fake(owner=self.user, version=9)
        handler = EntitySyncHandler("FAKE")
        with patch("apps.sync.tests_handlers_additional.FakeSerializer.is_valid") as is_valid:
            result = handler.push(
                operation=SyncItemLog.Operation.CREATE,
                client_uuid=instance.client_uuid,
                data={"ignored": True},
                base_version=None,
                user=self.user,
                request=self.request,
            )
        is_valid.assert_not_called()
        self.assertEqual(result["status"], SyncItemLog.Status.DUPLICATE)
        self.assertEqual(result["instance"], instance)
        self.assertEqual(result["server_version"], 9)

    def test_create_push_propagates_validation_and_save_errors(self):
        handler = EntitySyncHandler("FAKE")
        with self.assertRaises(ValidationError):
            handler.push(
                operation=SyncItemLog.Operation.CREATE,
                client_uuid=uuid.uuid4(),
                data={"invalid": True},
                base_version=None,
                user=self.user,
                request=self.request,
            )
        with self.assertRaises(RuntimeError):
            handler.push(
                operation=SyncItemLog.Operation.CREATE,
                client_uuid=uuid.uuid4(),
                data={"explode": True},
                base_version=None,
                user=self.user,
                request=self.request,
            )

    def test_update_missing_instance_raises_validation_error(self):
        handler = EntitySyncHandler("FAKE")
        with self.assertRaises(ValidationError) as ctx:
            handler.push(
                operation=SyncItemLog.Operation.UPDATE,
                client_uuid=uuid.uuid4(),
                data={"value": "missing"},
                base_version=None,
                user=self.user,
                request=self.request,
            )
        self.assertIn("client_uuid", ctx.exception.detail)

    def test_update_existing_uses_partial_serializer_and_detects_conflict(self):
        instance = self.create_fake(owner=self.user, version=5)
        handler = EntitySyncHandler("FAKE")
        result = handler.push(
            operation=SyncItemLog.Operation.UPDATE,
            client_uuid=instance.client_uuid,
            data={"value": "updated"},
            base_version=5,
            user=self.user,
            request=self.request,
        )
        serializer = FakeSerializer.last_instance
        self.assertEqual(serializer.args[0], instance)
        self.assertEqual(serializer.kwargs["data"], {"value": "updated"})
        self.assertTrue(serializer.kwargs["partial"])
        self.assertEqual(serializer.kwargs["context"], {"request": self.request, "sync": True})
        self.assertEqual(result["status"], SyncItemLog.Status.SUCCESS)

        with self.assertRaises(SyncConflictError):
            handler.push(
                operation=SyncItemLog.Operation.UPDATE,
                client_uuid=instance.client_uuid,
                data={"value": "stale"},
                base_version=4,
                user=self.user,
                request=self.request,
            )

    def test_update_without_base_version_and_invalid_serializer_behavior(self):
        instance = self.create_fake(owner=self.user, version=5)
        handler = EntitySyncHandler("FAKE")
        result = handler.push(
            operation=SyncItemLog.Operation.UPDATE,
            client_uuid=instance.client_uuid,
            data={"value": "no conflict check"},
            base_version=None,
            user=self.user,
            request=self.request,
        )
        self.assertEqual(result["status"], SyncItemLog.Status.SUCCESS)
        with self.assertRaises(ValidationError):
            handler.push(
                operation=SyncItemLog.Operation.UPDATE,
                client_uuid=instance.client_uuid,
                data={"invalid": True},
                base_version=None,
                user=self.user,
                request=self.request,
            )

    def test_upsert_creates_missing_updates_existing_and_detects_conflict(self):
        handler = EntitySyncHandler("FAKE")
        missing_uuid = uuid.uuid4()
        created = handler.push(
            operation=SyncItemLog.Operation.UPSERT,
            client_uuid=missing_uuid,
            data={"value": "new"},
            base_version=None,
            user=self.user,
            request=self.request,
        )
        self.assertEqual(created["status"], SyncItemLog.Status.SUCCESS)
        self.assertEqual(FakeSerializer.last_instance.kwargs["data"]["client_uuid"], str(missing_uuid))

        instance = self.create_fake(owner=self.user, version=8)
        updated = handler.push(
            operation=SyncItemLog.Operation.UPSERT,
            client_uuid=instance.client_uuid,
            data={"value": "existing"},
            base_version=8,
            user=self.user,
            request=self.request,
        )
        self.assertEqual(updated["status"], SyncItemLog.Status.SUCCESS)
        self.assertTrue(FakeSerializer.last_instance.kwargs["partial"])
        with self.assertRaises(SyncConflictError):
            handler.push(
                operation=SyncItemLog.Operation.UPSERT,
                client_uuid=instance.client_uuid,
                data={"value": "stale"},
                base_version=7,
                user=self.user,
                request=self.request,
            )
        with self.assertRaises(ValidationError):
            handler.push(
                operation=SyncItemLog.Operation.UPSERT,
                client_uuid=uuid.uuid4(),
                data={"invalid": True},
                base_version=None,
                user=self.user,
                request=self.request,
            )

    def test_unknown_operation_is_rejected_with_operation_in_message(self):
        handler = EntitySyncHandler("FAKE")
        with self.assertRaises(SyncUnsupportedEntityError) as ctx:
            handler.push(
                operation="DELETE",
                client_uuid=uuid.uuid4(),
                data={},
                base_version=None,
                user=self.user,
                request=self.request,
            )
        self.assertIn("DELETE", str(ctx.exception))

    def test_pull_queryset_disabled_cursor_order_and_missing_owner_field_branch(self):
        now = timezone.now()
        older = self.create_fake(owner=self.user, modified_at=now - timezone.timedelta(minutes=5))
        mine = self.create_fake(owner=self.user, modified_at=now)
        other = self.create_fake(owner=self.other_user, modified_at=now + timezone.timedelta(minutes=1))
        no_owner = self.create_fake(owner=None, modified_at=now + timezone.timedelta(minutes=2))

        disabled = EntitySyncHandler("FAKE_PULL_DISABLED")
        self.assertEqual(list(disabled.pull_queryset(user=self.user, cursor=None)), [])

        handler = EntitySyncHandler("FAKE")
        self.assertEqual(list(handler.pull_queryset(user=self.user, cursor=None)), [older, mine, other, no_owner])
        self.assertEqual(list(handler.pull_queryset(user=self.user, cursor=older.modified_at)), [mine, other, no_owner])

        no_owner_filter = EntitySyncHandler("FAKE_NO_OWNER_FIELD")
        self.assertEqual(list(no_owner_filter.pull_queryset(user=self.user, cursor=None)), [older, mine, other, no_owner])

        no_owner_config = EntitySyncHandler("FAKE_NO_ACTOR")
        self.assertEqual(list(no_owner_config.pull_queryset(user=self.user, cursor=None)), [older, mine, other, no_owner])

    def test_pull_queryset_with_custom_updated_at_lookup_and_order(self):
        handler = EntitySyncHandler("FAKE")
        first = self.create_fake(owner=self.user, modified_at=timezone.now())
        second = self.create_fake(owner=self.user, modified_at=first.modified_at)
        queryset = handler.pull_queryset(user=self.user, cursor=first.modified_at - timezone.timedelta(seconds=1))
        self.assertEqual(list(queryset), [first, second])

    def test_serialize_for_pull_returns_serializer_data_and_propagates_errors(self):
        handler = EntitySyncHandler("FAKE")
        instance = self.create_fake(owner=self.user)
        self.assertEqual(handler.serialize_for_pull(instance, self.request), {"serialized": True})
        serializer = FakeSerializer.last_instance
        self.assertEqual(serializer.args[0], instance)
        self.assertEqual(serializer.kwargs["context"], {"request": self.request, "sync": True})

        with patch("apps.sync.tests_handlers_additional.FakeSerializer.__init__", side_effect=RuntimeError("serializer init")):
            with self.assertRaises(RuntimeError):
                handler.serialize_for_pull(instance, self.request)

    def test_updated_at_uses_configured_field_and_returns_none_for_missing_or_null(self):
        handler = EntitySyncHandler("FAKE")
        known = timezone.now()
        self.assertEqual(handler.updated_at(SimpleNamespace(modified_at=known)), known)
        self.assertIsNone(handler.updated_at(SimpleNamespace()))
        self.assertIsNone(handler.updated_at(SimpleNamespace(modified_at=None)))


class EntitySyncHandlerRealModelTests(TestCase):
    def setUp(self):
        self.user = create_agent_terrain_user(email="sync.handler.real@example.com")
        self.other_user = create_agent_terrain_user(email="sync.handler.real.other@example.com")
        self.request = SimpleNamespace(user=self.user, build_absolute_uri=lambda path: f"http://testserver{path}")

    def test_real_ticket_get_instance_version_pull_queryset_and_serializer(self):
        handler = EntitySyncHandler(SyncItemLog.EntityType.TICKET)
        mine = Ticket.objects.create(
            opened_by=self.user,
            driver_name_snapshot="Mine",
            driver_dossier_snapshot="AA-12345-BB",
        )
        Ticket.objects.create(
            opened_by=self.other_user,
            driver_name_snapshot="Other",
            driver_dossier_snapshot="CC-12345-DD",
        )
        self.assertEqual(handler.get_instance(mine.client_uuid), mine)
        self.assertIsNone(handler.get_instance(uuid.uuid4()))
        self.assertEqual(handler._server_version(mine), int(mine.updated_at.timestamp() * 1_000_000))
        self.assertEqual(list(handler.pull_queryset(user=self.user, cursor=None)), [mine])
        self.assertIn("client_uuid", handler.serialize_for_pull(mine, self.request))
        self.assertEqual(handler.updated_at(mine), mine.updated_at)

    def test_real_delit_case_owner_pull_queryset(self):
        delit_type = DelitType.objects.create(code="SYNC-HANDLER", label="Sync handler")
        mine = DelitCase.objects.create(
            delit_type=delit_type,
            detected_by=self.user,
            source_type=DelitCase.SourceType.PLATE_SCAN,
            plate_number_snapshot="ZZ-12345",
            facts="Faits suffisamment longs pour le dossier sync.",
        )
        DelitCase.objects.create(
            delit_type=delit_type,
            detected_by=self.other_user,
            source_type=DelitCase.SourceType.PLATE_SCAN,
            plate_number_snapshot="YY-12345",
            facts="Autres faits suffisamment longs pour sync.",
        )
        handler = EntitySyncHandler(SyncItemLog.EntityType.DELIT_CASE)
        self.assertEqual(list(handler.pull_queryset(user=self.user, cursor=None)), [mine])





