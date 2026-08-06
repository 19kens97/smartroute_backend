from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import AgentProfile, Person, User
from apps.sync.handlers import (
    EntitySyncHandler,
    SyncConfigurationError,
    SyncConflictError,
    SyncUnsupportedEntityError,
    get_entity_config,
)
from apps.sync.models import SyncItemLog


class SyncHandlerConfigurationTests(SimpleTestCase):
    def test_unknown_entity_type_raises_supported_error(self):
        with self.assertRaises(SyncUnsupportedEntityError):
            get_entity_config("UNKNOWN")

    @override_settings(SYNC_ENTITY_CONFIG={"BROKEN": {"model": "missing.Model", "serializer": "missing.Serializer"}})
    def test_invalid_import_configuration_raises_configuration_error(self):
        with self.assertRaises(SyncConfigurationError):
            EntitySyncHandler("BROKEN")

    def test_push_disabled_entity_rejects_multipart_only_types(self):
        handler = EntitySyncHandler(SyncItemLog.EntityType.TICKET_PROOF)
        with self.assertRaises(SyncUnsupportedEntityError):
            handler.push(operation=SyncItemLog.Operation.CREATE, client_uuid="00000000-0000-0000-0000-000000000001", data={}, base_version=None, user=None, request=None)


class SyncHandlerConflictTests(TestCase):
    def test_check_conflict_ignores_missing_base_version_and_detects_stale_version(self):
        person = Person.objects.create(nif="130-000-001-0", first_name="Sync", last_name="Agent")
        user = User.objects.create_user(email="sync@example.com", password="Passw0rd!123", person=person)
        AgentProfile.objects.create(user=user, role=AgentProfile.Role.AGENT_TERRAIN, badge_number="13-00-00-00001")
        handler = EntitySyncHandler(SyncItemLog.EntityType.TICKET)
        ticket = handler.model.objects.create(opened_by=user, driver_name_snapshot="Driver", driver_dossier_snapshot="AB-12345-CD")

        handler._check_conflict(ticket, None)
        server_version = handler._server_version(ticket)
        handler._check_conflict(ticket, server_version)
        with self.assertRaises(SyncConflictError):
            handler._check_conflict(ticket, server_version - 1)

    def test_pull_queryset_is_ordered_and_limited_to_owner_field(self):
        first = Person.objects.create(nif="130-000-002-0", first_name="First", last_name="Agent")
        second = Person.objects.create(nif="130-000-003-0", first_name="Second", last_name="Agent")
        user = User.objects.create_user(email="sync1@example.com", password="Passw0rd!123", person=first)
        other = User.objects.create_user(email="sync2@example.com", password="Passw0rd!123", person=second)
        handler = EntitySyncHandler(SyncItemLog.EntityType.TICKET)
        mine = handler.model.objects.create(opened_by=user, driver_name_snapshot="Mine", driver_dossier_snapshot="AB-12345-CD")
        handler.model.objects.create(opened_by=other, driver_name_snapshot="Other", driver_dossier_snapshot="EF-12345-GH")

        self.assertEqual(list(handler.pull_queryset(user=user, cursor=None)), [mine])
