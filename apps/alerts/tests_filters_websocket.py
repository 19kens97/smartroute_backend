from types import SimpleNamespace

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase
from django.urls import path
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import AgentProfile, Person, User
from apps.alerts.consumers import AlertConsumer, user_alert_group
from apps.alerts.filters import AlertFilter
from apps.alerts.middleware import JWTAuthMiddleware
from apps.alerts.models import Alert


def create_agent(*, role=AgentProfile.Role.AGENT_TERRAIN, suffix="001"):
    person = Person.objects.create(nif=f"110-000-{int(suffix):03d}-0", first_name="Agent", last_name=suffix)
    user = User.objects.create_user(
        email=f"agent{suffix}@example.com",
        password="Passw0rd!123",
        person=person,
        account_type=User.AccountType.PROFESSIONAL,
    )
    AgentProfile.objects.create(user=user, role=role, badge_number=f"11-00-00-0{int(suffix):04d}")
    return user


@database_sync_to_async
def create_ws_user(*, suffix):
    return create_agent(suffix=suffix)


class AlertFilterTests(TestCase):
    def setUp(self):
        self.user = create_agent(suffix="001")
        self.vehicle = Alert.objects.create(
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.WANTED_VEHICLE,
            severity=Alert.Severity.CRITICAL,
            status=Alert.Status.ACTIVE,
            source=Alert.Source.MANUAL,
            plate_number="AA-12345",
            description="Vehicule recherche",
            created_by=self.user,
        )
        self.person = Alert.objects.create(
            category=Alert.Category.ADMINISTRATIVE,
            alert_type=Alert.AlertType.REFUSED_CONTROL,
            severity=Alert.Severity.WARNING,
            status=Alert.Status.RESOLVED,
            source=Alert.Source.MANUAL,
            subject_nif="123-456-789-0",
            description="Refus de controle",
            created_by=self.user,
        )

    def _ids(self, params):
        return list(AlertFilter(params, queryset=Alert.objects.order_by("id")).qs.values_list("id", flat=True))

    def test_filters_by_category_status_plate_and_search(self):
        self.assertEqual(self._ids({"category": [Alert.Category.FIELD_REPORT]}), [self.vehicle.id])
        self.assertEqual(self._ids({"status": [Alert.Status.RESOLVED]}), [self.person.id])
        self.assertEqual(self._ids({"plate_number": "aa12345"}), [self.vehicle.id])
        self.assertEqual(self._ids({"search": "recherche"}), [self.vehicle.id])
        self.assertEqual(self._ids({"search": "REFUSED"}), [self.person.id])

    def test_combined_filters_and_invalid_plate_return_exact_queryset(self):
        self.assertEqual(
            self._ids({"category": [Alert.Category.FIELD_REPORT], "severity": [Alert.Severity.CRITICAL]}),
            [self.vehicle.id],
        )
        self.assertEqual(self._ids({"plate_number": "bad"}), [])


class JWTAuthMiddlewareTests(TestCase):
    def setUp(self):
        self.user = create_agent(suffix="010")
        self.middleware = JWTAuthMiddleware(lambda scope, receive, send: None)

    def test_extracts_token_from_header_and_subprotocol_but_not_query(self):
        token = "abc.def"
        self.assertIsNone(self.middleware._get_token({"query_string": b"token=abc.def", "headers": []}))
        self.assertEqual(self.middleware._get_token({"headers": [(b"authorization", b"Bearer abc.def")]}), token)
        self.assertEqual(self.middleware._get_token({"headers": [(b"sec-websocket-protocol", b"json, bearer.abc.def")]}), token)

    async def test_authenticates_valid_jwt_and_rejects_invalid_or_missing(self):
        token = str(AccessToken.for_user(self.user))
        user, reason = await self.middleware._authenticate({"query_string": b"", "headers": [(b"sec-websocket-protocol", f"bearer.{token}".encode())]})
        self.assertEqual(user.pk, self.user.pk)
        self.assertIsNone(reason)

        missing_user, missing_reason = await self.middleware._authenticate({"query_string": b"", "headers": []})
        self.assertFalse(missing_user.is_authenticated)
        self.assertEqual(missing_reason, "missing_token")

        invalid_user, invalid_reason = await self.middleware._authenticate({"query_string": b"", "headers": [(b"sec-websocket-protocol", b"bearer.not-a-token")]})
        self.assertFalse(invalid_user.is_authenticated)
        self.assertEqual(invalid_reason, "invalid_token")


class AlertWebSocketTests(TransactionTestCase):
    async def test_authenticated_user_connects_receives_event_and_disconnects(self):
        user = await create_ws_user(suffix="011")
        app = URLRouter([path("ws/alerts/", AlertConsumer.as_asgi())])
        communicator = WebsocketCommunicator(app, "/ws/alerts/")
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        payload = {"type": "alert_created", "id": 7, "severity": "CRITICAL"}
        await get_channel_layer().group_send(user_alert_group(user.pk), {"type": "alert.created", "payload": payload})
        self.assertEqual(await communicator.receive_json_from(), payload)
        await communicator.disconnect()

    async def test_anonymous_user_is_rejected_and_large_payload_closes(self):
        app = URLRouter([path("ws/alerts/", AlertConsumer.as_asgi())])
        anonymous = WebsocketCommunicator(app, "/ws/alerts/")
        anonymous.scope["user"] = SimpleNamespace(is_authenticated=False)
        connected, _ = await anonymous.connect()
        self.assertFalse(connected)

        user = await create_ws_user(suffix="012")
        communicator = WebsocketCommunicator(app, "/ws/alerts/")
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_json_to({"payload": "x" * 5000})
        await communicator.wait()


