import uuid

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person

from .models import SyncDevice, SyncSession


class SyncApiTests(APITestCase):
    password = "Pass1234!Secure"

    def professional(self, email, role, badge):
        User = get_user_model()
        person = Person.objects.create(
            nif="88" + "".join(ch for ch in badge if ch.isdigit())[-8:].zfill(8),
            first_name=role,
            last_name="Sync",
        )
        user = User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email=email,
            password=self.password,
        )
        AgentProfile.objects.create(
            user=user,
            role=role,
            badge_number=badge,
            is_active=True,
        )
        return user

    def personal(self):
        User = get_user_model()
        person = Person.objects.create(
            nif="8800000003",
            first_name="Personal",
            last_name="Sync",
        )
        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PERSONAL,
            email="",
            password=self.password,
        )

    def setUp(self):
        self.user = self.professional(
            "sync.field@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "88-00-00-00001",
        )
        self.other_user = self.professional(
            "sync.other@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "88-00-00-00004",
        )
        self.personal_user = self.personal()
        self.device_uuid = uuid.uuid4()

    def authenticate(self, user=None):
        self.client.force_authenticate(
            user=user or self.user
        )

    def register_device(self):
        self.authenticate()
        response = self.client.post(
            "/api/sync/devices/register/",
            {
                "device_uuid": str(self.device_uuid),
                "device_name": "Redmi Note",
                "platform": "ANDROID",
                "app_version": "1.0.0",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_professional_user_can_register_device(self):
        response = self.register_device()
        self.assertTrue(
            SyncDevice.objects.filter(
                user=self.user,
                device_uuid=self.device_uuid,
                is_active=True,
            ).exists()
        )
        self.assertEqual(
            response.data["data"]["platform"],
            "ANDROID",
        )

    def test_personal_user_cannot_use_sync(self):
        self.authenticate(self.personal_user)
        response = self.client.post(
            "/api/sync/devices/register/",
            {
                "device_uuid": str(uuid.uuid4()),
                "platform": "ANDROID",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_device_cannot_belong_to_two_users(self):
        self.register_device()
        self.authenticate(self.other_user)
        response = self.client.post(
            "/api/sync/devices/register/",
            {
                "device_uuid": str(self.device_uuid),
                "platform": "ANDROID",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_push_requires_registered_device(self):
        self.authenticate()
        response = self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(uuid.uuid4()),
                "request_uuid": str(uuid.uuid4()),
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_push_is_idempotent(self):
        self.register_device()
        request_uuid = uuid.uuid4()
        payload = {
            "device_uuid": str(self.device_uuid),
            "request_uuid": str(request_uuid),
            "items": [],
        }

        first = self.client.post(
            "/api/sync/push/",
            payload,
            format="json",
        )
        second = self.client.post(
            "/api/sync/push/",
            payload,
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            SyncSession.objects.filter(
                request_uuid=request_uuid
            ).count(),
            1,
        )
        self.assertEqual(
            first.data["data"]["status"],
            SyncSession.Status.SUCCESS,
        )

    def test_same_request_uuid_rejects_different_payload(self):
        self.register_device()
        request_uuid = uuid.uuid4()

        first = self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(self.device_uuid),
                "request_uuid": str(request_uuid),
                "items": [],
            },
            format="json",
        )
        second = self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(self.device_uuid),
                "request_uuid": str(request_uuid),
                "items": [
                    {
                        "entity_type": "TICKET",
                        "operation": "CREATE",
                        "client_uuid": str(uuid.uuid4()),
                        "data": {},
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)

    def test_status_is_scoped_to_current_user(self):
        self.register_device()
        request_uuid = uuid.uuid4()
        self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(self.device_uuid),
                "request_uuid": str(request_uuid),
                "items": [],
            },
            format="json",
        )

        self.authenticate(self.other_user)
        response = self.client.get(
            f"/api/sync/status/?request_uuid={request_uuid}"
        )
        self.assertEqual(response.status_code, 400)

    def test_revoke_device_blocks_future_sync(self):
        self.register_device()
        revoke = self.client.post(
            "/api/sync/devices/revoke/",
            {"device_uuid": str(self.device_uuid)},
            format="json",
        )
        self.assertEqual(revoke.status_code, 200)

        push = self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(self.device_uuid),
                "request_uuid": str(uuid.uuid4()),
                "items": [],
            },
            format="json",
        )
        self.assertEqual(push.status_code, 400)

    def test_duplicate_items_in_same_batch_are_rejected(self):
        self.register_device()
        item_uuid = uuid.uuid4()
        response = self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(self.device_uuid),
                "request_uuid": str(uuid.uuid4()),
                "items": [
                    {
                        "entity_type": "TICKET",
                        "operation": "CREATE",
                        "client_uuid": str(item_uuid),
                        "data": {},
                    },
                    {
                        "entity_type": "TICKET",
                        "operation": "CREATE",
                        "client_uuid": str(item_uuid),
                        "data": {},
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_more_than_100_items_is_rejected(self):
        self.register_device()
        items = [
            {
                "entity_type": "TICKET",
                "operation": "CREATE",
                "client_uuid": str(uuid.uuid4()),
                "data": {},
            }
            for _ in range(101)
        ]
        response = self.client.post(
            "/api/sync/push/",
            {
                "device_uuid": str(self.device_uuid),
                "request_uuid": str(uuid.uuid4()),
                "items": items,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
