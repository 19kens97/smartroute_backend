from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AgentProfile
from apps.accounts.test_factories import create_agent_saisie_user, create_agent_terrain_user
from apps.alerts.models import Alert
from apps.alerts.realtime import (
    build_alert_created_event,
    broadcast_alert_created,
    get_alert_recipient_users,
    professional_alert_recipients,
)
from apps.alerts.consumers import user_alert_group


class AlertRealtimeAdditionalTests(TestCase):
    def setUp(self):
        self.creator = create_agent_terrain_user(email="alert.realtime.creator@example.com")
        self.recipient = create_agent_saisie_user(email="alert.realtime.recipient@example.com")
        self.inactive = create_agent_saisie_user(email="alert.realtime.inactive@example.com")
        self.inactive.agent_profile.is_active = False
        self.inactive.agent_profile.save()
        self.alert = Alert.objects.create(
            created_by=self.creator,
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.FIELD_ESCAPE,
            severity=Alert.Severity.CRITICAL,
            status=Alert.Status.ACTIVE,
            source=Alert.Source.MANUAL,
            plate_number="HT-100",
            description="  Description tres longue pour tester le preview de creation d'alerte.  ",
        )

    def test_professional_recipients_and_creator_exclusion(self):
        ids = set(professional_alert_recipients().values_list("id", flat=True))
        self.assertIn(self.creator.id, ids)
        self.assertIn(self.recipient.id, ids)
        self.assertNotIn(self.inactive.id, ids)

        recipient_ids = set(get_alert_recipient_users(self.alert, self.creator).values_list("id", flat=True))
        self.assertNotIn(self.creator.id, recipient_ids)
        self.assertIn(self.recipient.id, recipient_ids)

    def test_build_alert_created_event_contains_expected_payload_without_full_description(self):
        event = build_alert_created_event(self.alert)
        self.assertEqual(event["type"], "alert.created")
        self.assertEqual(event["version"], 2)
        data = event["data"]
        self.assertEqual(data["id"], self.alert.pk)
        self.assertEqual(data["alert_type"], self.alert.alert_type)
        self.assertEqual(data["plate_number"], "HT100")
        self.assertEqual(data["created_by_name"], self.creator.person.full_name)
        self.assertLessEqual(len(data["description_preview"]), 180)

    @patch("apps.alerts.realtime.async_to_sync")
    @patch("apps.alerts.realtime.get_channel_layer")
    def test_broadcast_sends_payload_to_each_recipient_group(self, get_layer, async_to_sync):
        layer = Mock()
        sender = Mock()
        get_layer.return_value = layer
        async_to_sync.return_value = sender

        broadcast_alert_created(self.alert)

        sender.assert_called_once()
        args, _ = sender.call_args
        self.assertEqual(args[0], user_alert_group(self.recipient.id))
        self.assertEqual(args[1]["type"], "alert.created")
        self.assertEqual(args[1]["payload"]["data"]["id"], self.alert.id)

    @patch("apps.alerts.realtime.get_channel_layer", return_value=None)
    @patch("apps.alerts.realtime.async_to_sync")
    def test_broadcast_returns_without_channel_layer(self, async_to_sync, get_layer):
        broadcast_alert_created(self.alert)
        async_to_sync.assert_not_called()


class ExpireFieldAlertsCommandTests(TestCase):
    def test_command_outputs_expired_count(self):
        user = create_agent_terrain_user(email="alert.command.field@example.com")
        expired = Alert.objects.create(
            created_by=user,
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.SUSPICIOUS_BEHAVIOR,
            severity=Alert.Severity.WARNING,
            source=Alert.Source.MANUAL,
            description="Alerte expiree.",
        )
        Alert.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        Alert.objects.create(
            created_by=user,
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.SUSPICIOUS_BEHAVIOR,
            severity=Alert.Severity.WARNING,
            source=Alert.Source.MANUAL,
            description="Alerte encore valide.",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        out = StringIO()
        call_command("expire_field_alerts", stdout=out)
        expired.refresh_from_db()
        self.assertEqual(expired.status, Alert.Status.EXPIRED)
        self.assertIn("1 alerte(s)", out.getvalue())

