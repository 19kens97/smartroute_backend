import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.test_factories import create_agent_saisie_user, create_agent_terrain_user
from apps.delits.models import DelitType
from apps.sync.handlers import SyncConflictError, SyncHandlerError
from apps.sync.models import SyncDevice, SyncItemLog, SyncSession
from apps.sync.services import (
    _create_session,
    _get_existing_session,
    canonical_hash,
    get_owned_active_device,
    process_pull,
    process_push,
    register_device,
)


class SyncServiceTestCase(TestCase):
    def setUp(self):
        self.user = create_agent_terrain_user(email="sync.services.terrain@example.com")
        self.other_user = create_agent_saisie_user(email="sync.services.saisie@example.com")
        self.device_uuid = uuid.uuid4()
        self.device = SyncDevice.objects.create(
            user=self.user,
            device_uuid=self.device_uuid,
            device_name="Initial",
            platform=SyncDevice.Platform.ANDROID,
            app_version="1.0.0",
        )
        self.request = SimpleNamespace(user=self.user)

    def push_item(self, *, entity_type=SyncItemLog.EntityType.TICKET, operation=SyncItemLog.Operation.UPSERT, data=None):
        return {
            "entity_type": entity_type,
            "operation": operation,
            "client_uuid": uuid.uuid4(),
            "base_version": 1,
            "data": data or {"field": "value"},
        }

    def push_payload(self, *, request_uuid=None, items=None):
        return {
            "device_uuid": self.device_uuid,
            "request_uuid": request_uuid or uuid.uuid4(),
            "items": [] if items is None else items,
        }

    def pull_payload(self, *, request_uuid=None, cursor=None, entity_types=None, limit=100):
        payload = {
            "device_uuid": self.device_uuid,
            "request_uuid": request_uuid or uuid.uuid4(),
            "limit": limit,
        }
        if cursor is not None:
            payload["cursor"] = cursor
        if entity_types is not None:
            payload["entity_types"] = entity_types
        return payload

    def make_session(self, *, request_uuid=None, user=None, direction=SyncSession.Direction.PUSH, payload_hash="hash", status=SyncSession.Status.SUCCESS):
        return SyncSession.objects.create(
            request_uuid=request_uuid or uuid.uuid4(),
            user=user or self.user,
            device=self.device,
            direction=direction,
            status=status,
            payload_hash=payload_hash,
        )


class CanonicalHashTests(TestCase):
    def test_hash_is_deterministic_and_sorts_keys(self):
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))
        self.assertEqual(canonical_hash({"a": 1}), canonical_hash({"a": 1}))

    def test_hash_changes_when_content_changes(self):
        self.assertNotEqual(canonical_hash({"a": 1}), canonical_hash({"a": 2}))

    def test_hash_supports_unicode_nested_and_default_str_values(self):
        payload = {
            "message": "Vehicule deja controle",
            "nested": [{"id": uuid.UUID("00000000-0000-0000-0000-000000000001")}],
            "amount": Decimal("12.50"),
            "at": datetime(2026, 1, 2, 3, 4, 5),
        }
        self.assertEqual(canonical_hash(payload), canonical_hash(dict(reversed(payload.items()))))


class SyncDeviceServiceTests(SyncServiceTestCase):
    def test_get_owned_active_device_returns_matching_active_device(self):
        self.assertEqual(get_owned_active_device(user=self.user, device_uuid=self.device_uuid), self.device)

    def test_get_owned_active_device_rejects_missing_other_inactive_revoked_or_wrong_uuid(self):
        cases = [
            (self.user, uuid.uuid4()),
            (self.other_user, self.device_uuid),
        ]
        inactive = SyncDevice.objects.create(user=self.user, device_uuid=uuid.uuid4(), is_active=False)
        revoked = SyncDevice.objects.create(
            user=self.user,
            device_uuid=uuid.uuid4(),
            is_active=False,
            revoked_at=timezone.now(),
            revoked_by=self.user,
        )
        cases.extend([(self.user, inactive.device_uuid), (self.user, revoked.device_uuid)])

        for user, device_uuid in cases:
            with self.subTest(user=user.pk, device_uuid=device_uuid):
                with self.assertRaises(ValidationError) as ctx:
                    get_owned_active_device(user=user, device_uuid=device_uuid)
                self.assertIn("device_uuid", ctx.exception.detail)

    def test_register_device_creates_with_all_data_and_defaults(self):
        created_uuid = uuid.uuid4()
        device = register_device(
            user=self.user,
            validated_data={
                "device_uuid": created_uuid,
                "device_name": "Pixel",
                "platform": SyncDevice.Platform.IOS,
                "app_version": "2.0.0",
            },
        )
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.device_name, "Pixel")
        self.assertEqual(device.platform, SyncDevice.Platform.IOS)
        self.assertEqual(device.app_version, "2.0.0")
        self.assertTrue(device.is_active)
        self.assertIsNone(device.revoked_at)
        self.assertIsNone(device.revoked_by)
        self.assertIsNotNone(device.last_seen_at)

        default_device = register_device(user=self.user, validated_data={"device_uuid": uuid.uuid4()})
        self.assertEqual(default_device.device_name, "")
        self.assertEqual(default_device.platform, SyncDevice.Platform.ANDROID)
        self.assertEqual(default_device.app_version, "")

    def test_register_device_updates_and_reactivates_same_owner_device(self):
        self.device.revoke(actor=self.user)
        old_last_seen = self.device.last_seen_at

        device = register_device(
            user=self.user,
            validated_data={
                "device_uuid": self.device_uuid,
                "device_name": "Updated",
                "platform": SyncDevice.Platform.WEB,
                "app_version": "3.0.0",
            },
        )

        self.assertEqual(SyncDevice.objects.filter(device_uuid=self.device_uuid).count(), 1)
        self.assertEqual(device.device_name, "Updated")
        self.assertEqual(device.platform, SyncDevice.Platform.WEB)
        self.assertTrue(device.is_active)
        self.assertIsNone(device.revoked_at)
        self.assertIsNone(device.revoked_by)
        self.assertGreater(device.last_seen_at, old_last_seen)

    def test_register_device_rejects_device_owned_by_another_user(self):
        with self.assertRaises(ValidationError) as ctx:
            register_device(user=self.other_user, validated_data={"device_uuid": self.device_uuid})
        self.assertIn("device_uuid", ctx.exception.detail)


class SyncSessionServiceTests(SyncServiceTestCase):
    def test_get_existing_session_is_scoped_by_request_user_and_direction(self):
        request_uuid = uuid.uuid4()
        matching = self.make_session(request_uuid=request_uuid, direction=SyncSession.Direction.PUSH)
        self.make_session(user=self.other_user, direction=SyncSession.Direction.PUSH)
        self.make_session(direction=SyncSession.Direction.PULL)

        self.assertEqual(
            _get_existing_session(request_uuid=request_uuid, user=self.user, direction=SyncSession.Direction.PUSH),
            matching,
        )
        self.assertIsNone(
            _get_existing_session(request_uuid=uuid.uuid4(), user=self.user, direction=SyncSession.Direction.PUSH)
        )

    def test_create_session_sets_processing_fields(self):
        cursor = timezone.now()
        request_uuid = uuid.uuid4()
        payload_hash = "a" * 64
        session = _create_session(
            request_uuid=request_uuid,
            device=self.device,
            user=self.user,
            direction=SyncSession.Direction.PULL,
            item_count=3,
            cursor=cursor,
            payload_hash=payload_hash,
        )
        self.assertEqual(session.status, SyncSession.Status.PROCESSING)
        self.assertEqual(session.direction, SyncSession.Direction.PULL)
        self.assertEqual(session.device, self.device)
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.item_count, 3)
        self.assertEqual(session.cursor, cursor)
        self.assertEqual(session.payload_hash, payload_hash)

    def test_create_session_recovers_existing_session_after_integrity_error(self):
        request_uuid = uuid.uuid4()
        existing = self.make_session(request_uuid=request_uuid, direction=SyncSession.Direction.PUSH)

        with patch("apps.sync.services.SyncSession.objects.create", side_effect=IntegrityError) as mocked_create:
            session = _create_session(
            request_uuid=request_uuid,
            device=self.device,
            user=self.user,
            direction=SyncSession.Direction.PUSH,
            item_count=1,
        )
        self.assertEqual(session, existing)
        mocked_create.assert_called_once()

    def test_create_session_collision_with_other_user_or_direction_is_rejected(self):
        request_uuid = uuid.uuid4()
        self.make_session(request_uuid=request_uuid, direction=SyncSession.Direction.PULL)
        with patch("apps.sync.services.SyncSession.objects.create", side_effect=IntegrityError) as mocked_create:
            with self.assertRaises(ValidationError):
                _create_session(
                    request_uuid=request_uuid,
                    device=self.device,
                    user=self.user,
                    direction=SyncSession.Direction.PUSH,
                    item_count=1,
                )

        other_request_uuid = uuid.uuid4()
        other_device = SyncDevice.objects.create(user=self.other_user, device_uuid=uuid.uuid4())
        self.make_session(request_uuid=other_request_uuid, user=self.other_user, direction=SyncSession.Direction.PUSH)
        with patch("apps.sync.services.SyncSession.objects.create", side_effect=IntegrityError) as mocked_create_other:
            with self.assertRaises(ValidationError):
                _create_session(
                    request_uuid=other_request_uuid,
                    device=self.device,
                    user=self.user,
                    direction=SyncSession.Direction.PUSH,
                    item_count=1,
                )
        self.assertTrue(other_device.pk)
        self.assertEqual(mocked_create.call_count, 1)
        self.assertEqual(mocked_create_other.call_count, 1)

    @patch("apps.sync.services.SyncSession.objects.create", side_effect=IntegrityError)
    def test_create_session_integrity_error_without_existing_session_is_rejected(self, mocked_create):
        with self.assertRaises(ValidationError) as ctx:
            _create_session(
                request_uuid=uuid.uuid4(),
                device=self.device,
                user=self.user,
                direction=SyncSession.Direction.PUSH,
                item_count=1,
            )
        self.assertIn("request_uuid", ctx.exception.detail)
        mocked_create.assert_called_once()


class ProcessPushServiceTests(SyncServiceTestCase):
    def fake_success_handler(self, *, status=SyncItemLog.Status.SUCCESS, pk="42", version=7):
        instance = SimpleNamespace(pk=pk)
        handler = Mock()
        handler.push.return_value = {"instance": instance, "status": status, "server_version": version}
        return handler

    def test_empty_push_creates_success_session_without_logs_handlers_or_cache(self):
        payload = self.push_payload(items=[])
        with patch("apps.sync.services.EntitySyncHandler") as handler_class, patch("apps.sync.services.invalidate_statistics_cache") as invalidate:
            session, created = process_push(user=self.user, request=self.request, validated_data=payload)

        self.device.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(session.status, SyncSession.Status.SUCCESS)
        self.assertEqual(session.item_count, 0)
        self.assertEqual(session.success_count, 0)
        self.assertEqual(session.items.count(), 0)
        handler_class.assert_not_called()
        invalidate.assert_not_called()
        self.assertIsNotNone(self.device.last_seen_at)

    def test_successful_item_creates_log_counts_success_and_invalidates_cache_on_commit(self):
        item = self.push_item(data={"amount": 10})
        handler = self.fake_success_handler(pk="99", version=12)
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler), patch("apps.sync.services.invalidate_statistics_cache") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                session, created = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=[item]))

        log = session.items.get()
        self.assertTrue(created)
        self.assertEqual(session.status, SyncSession.Status.SUCCESS)
        self.assertEqual(session.success_count, 1)
        self.assertEqual(log.status, SyncItemLog.Status.SUCCESS)
        self.assertEqual(log.payload_hash, canonical_hash(item["data"]))
        self.assertEqual(log.server_id, "99")
        self.assertEqual(log.server_version, 12)
        invalidate.assert_called_once()

    def test_duplicate_item_counts_as_success_without_cache_invalidation(self):
        item = self.push_item()
        handler = self.fake_success_handler(status=SyncItemLog.Status.DUPLICATE)
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler), patch("apps.sync.services.invalidate_statistics_cache") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                session, created = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=[item]))

        self.assertTrue(created)
        self.assertEqual(session.status, SyncSession.Status.SUCCESS)
        self.assertEqual(session.success_count, 1)
        self.assertEqual(session.items.get().status, SyncItemLog.Status.DUPLICATE)
        invalidate.assert_not_called()

    def test_multiple_successes_use_handlers_for_multiple_entity_types(self):
        items = [
            self.push_item(entity_type=SyncItemLog.EntityType.TICKET),
            self.push_item(entity_type=SyncItemLog.EntityType.DELIT_CASE),
        ]
        handler = self.fake_success_handler()
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler) as handler_class:
            session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=items))

        self.assertEqual(session.status, SyncSession.Status.SUCCESS)
        self.assertEqual(session.success_count, 2)
        self.assertEqual(session.items.count(), 2)
        self.assertEqual([call.args[0] for call in handler_class.call_args_list], [SyncItemLog.EntityType.TICKET, SyncItemLog.EntityType.DELIT_CASE])
        self.assertEqual(handler.push.call_count, 2)

    def test_conflict_only_marks_failed_session_and_conflict_log(self):
        item = self.push_item()
        handler = Mock()
        handler.push.side_effect = SyncConflictError("Version obsolette")
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
            session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=[item]))

        log = session.items.get()
        self.assertEqual(session.status, SyncSession.Status.FAILED)
        self.assertEqual(session.conflict_count, 1)
        self.assertEqual(session.success_count, 0)
        self.assertEqual(log.status, SyncItemLog.Status.CONFLICT)
        self.assertEqual(log.error_code, "SYNC_CONFLICT")
        self.assertIn("Version obsolette", log.error_message)

    def test_success_plus_conflict_is_partial_success(self):
        items = [self.push_item(), self.push_item()]
        handler = Mock()
        handler.push.side_effect = [
            {"instance": SimpleNamespace(pk=1), "status": SyncItemLog.Status.SUCCESS, "server_version": 1},
            SyncConflictError("Conflit"),
        ]
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
            session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=items))
        self.assertEqual(session.status, SyncSession.Status.PARTIAL_SUCCESS)
        self.assertEqual(session.success_count, 1)
        self.assertEqual(session.conflict_count, 1)

    def test_validation_handler_value_and_type_errors_are_logged_as_failures_with_codes_and_truncation(self):
        cases = [
            (ValidationError({"field": "bad"}), "VALIDATION_ERROR"),
            (SyncHandlerError("handler failed"), "SYNC_HANDLER_ERROR"),
            (ValueError("v" * 600), "VALIDATION_ERROR"),
            (TypeError("wrong type"), "VALIDATION_ERROR"),
        ]
        for exc, expected_code in cases:
            with self.subTest(exc=type(exc).__name__):
                handler = Mock()
                handler.push.side_effect = exc
                with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
                    session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=[self.push_item()]))
                log = session.items.get()
                self.assertEqual(session.status, SyncSession.Status.FAILED)
                self.assertEqual(session.failure_count, 1)
                self.assertEqual(log.status, SyncItemLog.Status.FAILED)
                self.assertEqual(log.error_code, expected_code)
                self.assertLessEqual(len(log.error_message), 500)

    def test_unexpected_error_is_logged_and_does_not_escape_loop(self):
        handler = Mock()
        handler.push.side_effect = RuntimeError("boom")
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler), patch("apps.sync.services.logger.exception") as logged:
            session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=[self.push_item()]))
        log = session.items.get()
        self.assertEqual(session.status, SyncSession.Status.FAILED)
        self.assertEqual(session.failure_count, 1)
        self.assertEqual(log.error_code, "INTERNAL_ERROR")
        self.assertIn("erreur interne", log.error_message)
        logged.assert_called_once()

    def test_final_status_matrix_for_success_failure_and_conflict_counts(self):
        scenarios = [
            ([SyncItemLog.Status.SUCCESS], SyncSession.Status.SUCCESS, (1, 0, 0)),
            ([ValueError("bad")], SyncSession.Status.FAILED, (0, 1, 0)),
            ([SyncConflictError("conflict")], SyncSession.Status.FAILED, (0, 0, 1)),
            ([SyncItemLog.Status.SUCCESS, ValueError("bad")], SyncSession.Status.PARTIAL_SUCCESS, (1, 1, 0)),
            ([SyncItemLog.Status.SUCCESS, SyncConflictError("conflict")], SyncSession.Status.PARTIAL_SUCCESS, (1, 0, 1)),
            ([ValueError("bad"), SyncConflictError("conflict")], SyncSession.Status.FAILED, (0, 1, 1)),
            ([SyncItemLog.Status.SUCCESS, SyncItemLog.Status.SUCCESS, ValueError("bad"), SyncConflictError("conflict")], SyncSession.Status.PARTIAL_SUCCESS, (2, 1, 1)),
        ]
        for effects, expected_status, counts in scenarios:
            with self.subTest(expected_status=expected_status, effects=[str(e) for e in effects]):
                handler = Mock()
                side_effect = []
                items = []
                for effect in effects:
                    items.append(self.push_item())
                    if effect == SyncItemLog.Status.SUCCESS:
                        side_effect.append({"instance": SimpleNamespace(pk=uuid.uuid4()), "status": effect, "server_version": 1})
                    else:
                        side_effect.append(effect)
                handler.push.side_effect = side_effect
                with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
                    session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=items))
                self.assertEqual(session.status, expected_status)
                self.assertEqual((session.success_count, session.failure_count, session.conflict_count), counts)

    def test_one_transaction_per_item_allows_other_items_after_failure(self):
        items = [self.push_item(), self.push_item(), self.push_item()]
        handler = Mock()
        handler.push.side_effect = [
            {"instance": SimpleNamespace(pk=1), "status": SyncItemLog.Status.SUCCESS, "server_version": 1},
            ValueError("bad item"),
            {"instance": SimpleNamespace(pk=3), "status": SyncItemLog.Status.SUCCESS, "server_version": 3},
        ]
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
            session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=items))
        self.assertEqual(session.status, SyncSession.Status.PARTIAL_SUCCESS)
        self.assertEqual(session.success_count, 2)
        self.assertEqual(session.failure_count, 1)
        self.assertEqual(handler.push.call_count, 3)

    def test_item_transaction_rolls_back_handler_changes_for_failed_item(self):
        DelitType.objects.create(code="BEFORE", label="Before")
        items = [self.push_item(), self.push_item()]
        effects = []

        def first_push(**kwargs):
            DelitType.objects.create(code="ROLLBACK", label="Rollback")
            raise ValueError("rollback")

        effects.extend([
            first_push,
            {"instance": SimpleNamespace(pk=2), "status": SyncItemLog.Status.SUCCESS, "server_version": 2},
        ])

        def call_side_effect(**kwargs):
            effect = effects.pop(0)
            if callable(effect):
                return effect(**kwargs)
            return effect

        handler = Mock()
        handler.push.side_effect = call_side_effect
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
            session, _ = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=items))
        self.assertFalse(DelitType.objects.filter(code="ROLLBACK").exists())
        self.assertEqual(session.status, SyncSession.Status.PARTIAL_SUCCESS)

    def test_existing_push_session_idempotence_and_hash_mismatch(self):
        payload = self.push_payload(items=[])
        payload_hash = canonical_hash(payload)
        existing = self.make_session(request_uuid=payload["request_uuid"], payload_hash=payload_hash)
        with patch("apps.sync.services.EntitySyncHandler") as handler_class:
            session, created = process_push(user=self.user, request=self.request, validated_data=payload)
        self.assertEqual(session, existing)
        self.assertFalse(created)
        handler_class.assert_not_called()
        self.assertEqual(existing.items.count(), 0)

        bad_payload = self.push_payload(request_uuid=payload["request_uuid"], items=[self.push_item()])
        with self.assertRaises(ValidationError):
            process_push(user=self.user, request=self.request, validated_data=bad_payload)

    def test_existing_push_session_without_payload_hash_is_reused(self):
        payload = self.push_payload(items=[self.push_item()])
        existing = self.make_session(request_uuid=payload["request_uuid"], payload_hash="")
        with patch("apps.sync.services.EntitySyncHandler") as handler_class:
            session, created = process_push(user=self.user, request=self.request, validated_data=payload)
        self.assertEqual(session, existing)
        self.assertFalse(created)
        handler_class.assert_not_called()

    @patch("apps.sync.services._create_session")
    def test_create_session_returning_finalized_session_short_circuits_push(self, create_session):
        finalized = self.make_session(status=SyncSession.Status.SUCCESS)
        create_session.return_value = finalized
        with patch("apps.sync.services.EntitySyncHandler") as handler_class:
            session, created = process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=[self.push_item()]))
        self.assertEqual(session, finalized)
        self.assertFalse(created)
        handler_class.assert_not_called()

    def test_no_cache_invalidation_for_duplicates_failures_conflicts_or_empty_batch(self):
        effects = [[], [SyncItemLog.Status.DUPLICATE], [ValueError("bad")], [SyncConflictError("conflict")]]
        for scenario in effects:
            with self.subTest(scenario=[str(item) for item in scenario]):
                handler = Mock()
                items = []
                side_effect = []
                for effect in scenario:
                    items.append(self.push_item())
                    if effect == SyncItemLog.Status.DUPLICATE:
                        side_effect.append({"instance": SimpleNamespace(pk=1), "status": effect, "server_version": 1})
                    else:
                        side_effect.append(effect)
                handler.push.side_effect = side_effect
                with patch("apps.sync.services.EntitySyncHandler", return_value=handler), patch("apps.sync.services.invalidate_statistics_cache") as invalidate:
                    with self.captureOnCommitCallbacks(execute=True):
                        process_push(user=self.user, request=self.request, validated_data=self.push_payload(items=items))
                invalidate.assert_not_called()


class FakeQuerySet(list):
    def __getitem__(self, item):
        result = super().__getitem__(item)
        return FakeQuerySet(result) if isinstance(item, slice) else result


class ProcessPullServiceTests(SyncServiceTestCase):
    def fake_handler(self, instances):
        handler = Mock()
        handler.pull_queryset.return_value = FakeQuerySet(instances)
        handler.updated_at.side_effect = lambda instance: instance.updated_at
        handler.serialize_for_pull.side_effect = lambda instance, request: {"name": instance.name}
        return handler

    def instance(self, pk, *, client_uuid=None, updated_at=None, name=None):
        return SimpleNamespace(
            pk=pk,
            client_uuid=client_uuid if client_uuid is not None else uuid.uuid4(),
            updated_at=updated_at,
            name=name or f"item-{pk}",
        )

    def test_pull_defaults_to_ticket_verbalization_and_delit_case_and_updates_device(self):
        payload = self.pull_payload(entity_types=None)
        handler = self.fake_handler([])
        before = self.device.last_seen_at
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler) as handler_class:
            session, output, created = process_pull(user=self.user, request=self.request, validated_data=payload)
        self.device.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(output, [])
        self.assertEqual(session.status, SyncSession.Status.SUCCESS)
        self.assertEqual(session.item_count, 0)
        self.assertEqual(session.success_count, 0)
        self.assertIsNotNone(session.next_cursor)
        self.assertGreater(self.device.last_seen_at, before)
        self.assertEqual(
            [call.args[0] for call in handler_class.call_args_list],
            [SyncItemLog.EntityType.TICKET, SyncItemLog.EntityType.VERBALIZATION, SyncItemLog.EntityType.DELIT_CASE],
        )

    def test_pull_uses_explicit_entity_types_and_formats_output_with_empty_client_uuid(self):
        now = timezone.now()
        explicit_type = SyncItemLog.EntityType.DELIT_CASE
        instances = [self.instance(5, client_uuid="", updated_at=now, name="delit")]
        handler = self.fake_handler(instances)
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler) as handler_class:
            session, output, created = process_pull(
                user=self.user,
                request=self.request,
                validated_data=self.pull_payload(entity_types=[explicit_type]),
            )
        self.assertTrue(created)
        self.assertEqual(handler_class.call_args.args[0], explicit_type)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["entity_type"], explicit_type)
        self.assertEqual(output[0]["operation"], SyncItemLog.Operation.UPSERT)
        self.assertEqual(output[0]["server_id"], "5")
        self.assertEqual(output[0]["client_uuid"], "")
        self.assertEqual(output[0]["updated_at"], now)
        self.assertEqual(output[0]["data"], {"name": "delit"})
        self.assertEqual(session.item_count, 1)
        self.assertEqual(session.success_count, 1)
        self.assertEqual(session.next_cursor, now)

    def test_pull_global_limit_stops_following_handlers_when_first_type_fills_limit(self):
        instances = [self.instance(1), self.instance(2)]
        first_handler = self.fake_handler(instances)
        second_handler = self.fake_handler([self.instance(3)])
        with patch("apps.sync.services.EntitySyncHandler", side_effect=[first_handler, second_handler]) as handler_class:
            session, output, _ = process_pull(
                user=self.user,
                request=self.request,
                validated_data=self.pull_payload(
                    entity_types=[SyncItemLog.EntityType.TICKET, SyncItemLog.EntityType.DELIT_CASE],
                    limit=2,
                ),
            )
        self.assertEqual(len(output), 2)
        self.assertEqual(session.item_count, 2)
        self.assertEqual(handler_class.call_count, 2)
        second_handler.pull_queryset.assert_not_called()

    def test_pull_limit_is_shared_across_entity_types(self):
        handlers = [
            self.fake_handler([self.instance(1), self.instance(2)]),
            self.fake_handler([self.instance(3), self.instance(4)]),
        ]
        with patch("apps.sync.services.EntitySyncHandler", side_effect=handlers):
            session, output, _ = process_pull(
                user=self.user,
                request=self.request,
                validated_data=self.pull_payload(
                    entity_types=[SyncItemLog.EntityType.TICKET, SyncItemLog.EntityType.DELIT_CASE],
                    limit=3,
                ),
            )
        self.assertEqual(len(output), 3)
        self.assertEqual(session.item_count, 3)
        self.assertEqual(len(handlers[1].pull_queryset.return_value[:1]), 1)

    def test_pull_cursor_advances_only_to_strictly_newer_non_null_updated_at(self):
        cursor = timezone.now()
        older = cursor - timedelta(minutes=1)
        newer = cursor + timedelta(minutes=1)
        newest = cursor + timedelta(minutes=5)
        instances = [
            self.instance(1, updated_at=older),
            self.instance(2, updated_at=cursor),
            self.instance(3, updated_at=None),
            self.instance(4, updated_at=newest),
            self.instance(5, updated_at=newer),
        ]
        handler = self.fake_handler(instances)
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
            session, output, _ = process_pull(
                user=self.user,
                request=self.request,
                validated_data=self.pull_payload(cursor=cursor, entity_types=[SyncItemLog.EntityType.TICKET]),
            )
        self.assertEqual(len(output), 5)
        self.assertEqual(session.next_cursor, newest)

    def test_existing_pull_session_is_reused_but_handlers_are_reprocessed(self):
        payload = self.pull_payload(entity_types=[SyncItemLog.EntityType.TICKET])
        payload_hash = canonical_hash(payload)
        existing = self.make_session(
            request_uuid=payload["request_uuid"],
            direction=SyncSession.Direction.PULL,
            payload_hash=payload_hash,
            status=SyncSession.Status.SUCCESS,
        )
        handler = self.fake_handler([self.instance(7)])
        with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
            session, output, created = process_pull(user=self.user, request=self.request, validated_data=payload)
        self.assertEqual(session, existing)
        self.assertFalse(created)
        self.assertEqual(len(output), 1)
        handler.pull_queryset.assert_called_once()

    def test_existing_pull_session_rejects_different_payload_and_reuses_missing_hash(self):
        payload = self.pull_payload(entity_types=[SyncItemLog.EntityType.TICKET])
        self.make_session(
            request_uuid=payload["request_uuid"],
            direction=SyncSession.Direction.PULL,
            payload_hash="different",
        )
        with self.assertRaises(ValidationError):
            process_pull(user=self.user, request=self.request, validated_data=payload)

        payload_without_hash = self.pull_payload(entity_types=[SyncItemLog.EntityType.TICKET])
        existing = self.make_session(
            request_uuid=payload_without_hash["request_uuid"],
            direction=SyncSession.Direction.PULL,
            payload_hash="",
            status=SyncSession.Status.SUCCESS,
        )
        with patch("apps.sync.services.EntitySyncHandler", return_value=self.fake_handler([])):
            session, output, created = process_pull(user=self.user, request=self.request, validated_data=payload_without_hash)
        self.assertEqual(session, existing)
        self.assertFalse(created)
        self.assertEqual(output, [])

    def test_pull_handler_errors_propagate(self):
        payload = self.pull_payload(entity_types=[SyncItemLog.EntityType.TICKET])
        error_cases = [
            RuntimeError("init"),
            None,
            None,
        ]
        with self.subTest(stage="init"):
            with patch("apps.sync.services.EntitySyncHandler", side_effect=error_cases[0]):
                with self.assertRaises(RuntimeError):
                    process_pull(user=self.user, request=self.request, validated_data=payload)

        with self.subTest(stage="queryset"):
            handler = Mock()
            handler.pull_queryset.side_effect = RuntimeError("query")
            with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
                with self.assertRaises(RuntimeError):
                    process_pull(user=self.user, request=self.request, validated_data=self.pull_payload(entity_types=[SyncItemLog.EntityType.TICKET]))

        with self.subTest(stage="serialize"):
            handler = self.fake_handler([self.instance(1)])
            handler.serialize_for_pull.side_effect = RuntimeError("serialize")
            with patch("apps.sync.services.EntitySyncHandler", return_value=handler):
                with self.assertRaises(RuntimeError):
                    process_pull(user=self.user, request=self.request, validated_data=self.pull_payload(entity_types=[SyncItemLog.EntityType.TICKET]))



