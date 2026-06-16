from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

class AlertPermissionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        User.objects.create_user(username="field", password="Pass1234!", role="AGENT_TERRAIN")
        User.objects.create_user(username="admin", password="Pass1234!", role="ADMIN")

    def auth(self, username):
        token = self.client.post("/api/auth/token/", {"username":username,"password":"Pass1234!"}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_field_cannot_create_critical(self):
        self.auth("field")
        r = self.client.post("/api/alerts/", {"alert_type":"WANTED_VEHICLE"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_admin_can_create_critical(self):
        self.auth("admin")
        r = self.client.post("/api/alerts/", {"alert_type":"WANTED_VEHICLE"}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_unauthenticated_cannot_create_alert(self):
        self.client.credentials()
        r = self.client.post("/api/alerts/", {"alert_type":"FIELD_ESCAPE"}, format="json")
        self.assertEqual(r.status_code, 401)
