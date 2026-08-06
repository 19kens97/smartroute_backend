from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import AgentProfile, Person

from .models import AuditLog
from .services import create_audit_log


class AuditLogTests(TestCase):
    def setUp(self):
        User = get_user_model()
        person = Person.objects.create(
            nif="8600000001",
            first_name="Audit",
            last_name="Agent",
        )
        self.user = User.objects.create_user(
            person=person,
            account_type=User.AccountType.PROFESSIONAL,
            email="audit.agent@example.com",
            password="Pass1234!Secure",
        )
        AgentProfile.objects.create(
            user=self.user,
            role=AgentProfile.Role.ADMIN,
            badge_number="86-00-00-00001",
            is_active=True,
        )
        self.factory = RequestFactory()

    def test_audit_captures_request_and_role_snapshots(self):
        request = self.factory.patch(
            "/api/tickets/1/cancel/",
            HTTP_USER_AGENT="SmartRouteMobile/test",
            REMOTE_ADDR="127.0.0.1",
        )
        request.request_id = "audit-request-001"

        audit = create_audit_log(
            actor=self.user,
            action=AuditLog.Action.CANCEL,
            request=request,
            payload={
                "reason": "Doublon",
                "password": "do-not-store",
                "driver_nif_snapshot": "NIF-001",
            },
            commit_on_success=False,
        )

        self.assertEqual(
            audit.actor_email_snapshot,
            "audit.agent@example.com",
        )
        self.assertEqual(
            audit.actor_role_snapshot,
            AgentProfile.Role.ADMIN,
        )
        self.assertEqual(
            audit.request_id,
            "audit-request-001",
        )
        self.assertEqual(audit.request_method, "PATCH")
        self.assertEqual(audit.ip_address, "127.0.0.1")
        self.assertEqual(
            audit.payload["password"],
            "<redacted>",
        )
        self.assertEqual(
            audit.payload["driver_nif_snapshot"],
            "NI***01",
        )

    def test_audit_can_record_global_event(self):
        audit = create_audit_log(
            actor=self.user,
            action=AuditLog.Action.LOGIN,
            payload={"method": "professional_email"},
            commit_on_success=False,
        )
        self.assertEqual(audit.object_id, "")
        self.assertEqual(audit.model_name, "")
        self.assertTrue(audit.success)
