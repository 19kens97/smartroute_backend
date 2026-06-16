from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import SyncLog

class SyncTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="syncuser", password="Pass1234!", role="AGENT_SAISIE")
        token = self.client.post("/api/auth/token/", {"username":"syncuser","password":"Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_sync_push(self):
        r = self.client.post("/api/sync/push/", {"client_uuid":"abc-123", "items":[]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SyncLog.objects.filter(client_uuid="abc-123", direction="PUSH").count(), 1)

    def test_sync_pull(self):
        r = self.client.post("/api/sync/pull/", {"client_uuid":"abc-123"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SyncLog.objects.filter(client_uuid="abc-123", direction="PULL").count(), 1)

    def test_sync_status_returns_last_status(self):
        SyncLog.objects.create(client_uuid="abc-123", user=self.user, direction="PUSH", payload={}, status="SUCCESS")
        r = self.client.get("/api/sync/status/?client_uuid=abc-123")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["data"]["count"], 1)
        self.assertEqual(r.data["data"]["last_status"], "SUCCESS")
