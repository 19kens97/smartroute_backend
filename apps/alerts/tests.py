from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AgentProfile, Person
from apps.accounts.test_factories import create_agent_saisie_user
from apps.drivers.models import Driver
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner
from apps.vehicles.models import Vehicle

from .models import Alert, FIELD_ALERT_LIFETIME_HOURS
from .services import (
    REASON_DRIVER_LICENSE_EXPIRING,
    REASON_INSURANCE_EXPIRING,
    REASON_REGISTRATION_EXPIRING,
    evaluate_document_expiry_warnings,
    expire_field_alerts,
)


class AlertTestMixin:
    password = "Pass1234!Secure"

    def professional(self, email, role, badge):
        User = get_user_model()
        person = Person.objects.create(
            nif=badge,
            first_name=role,
            last_name="Alerts",
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
            nif="ALT-PERSONAL-001",
            first_name="Personal",
            last_name="Alerts",
        )
        return User.objects.create_user(
            person=person,
            account_type=User.AccountType.PERSONAL,
            email="",
            password=self.password,
        )


class AlertCategoryApiTests(AlertTestMixin, APITestCase):
    def setUp(self):
        self.entry = self.professional(
            "alerts.entry@example.com",
            AgentProfile.Role.AGENT_SAISIE,
            "ALT-SAI-001",
        )
        self.field = self.professional(
            "alerts.field@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "ALT-TER-001",
        )
        self.admin = self.professional(
            "alerts.admin@example.com",
            AgentProfile.Role.ADMIN,
            "ALT-ADM-001",
        )
        self.personal_user = self.personal()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_field_agent_creates_six_hour_field_report(self):
        self.auth(self.field)

        before = timezone.now()
        response = self.client.post(
            "/api/alerts/",
            {
                "alert_type": Alert.AlertType.REFUSED_CONTROL,
                "description": (
                    "Le conducteur refuse de se soumettre "
                    "au contrôle routier."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        alert = Alert.objects.get(pk=response.data["id"])

        self.assertEqual(
            alert.category,
            Alert.Category.FIELD_REPORT,
        )
        self.assertEqual(
            alert.created_by,
            self.field,
        )
        self.assertIsNotNone(alert.expires_at)
        self.assertGreaterEqual(
            alert.expires_at,
            before + timedelta(
                hours=FIELD_ALERT_LIFETIME_HOURS,
                minutes=-1,
            ),
        )

    def test_entry_agent_creates_administrative_alert(self):
        self.auth(self.entry)

        response = self.client.post(
            "/api/alerts/",
            {
                "alert_type": Alert.AlertType.STOLEN_PLATE,
                "plate_number": "HT-12345",
                "description": (
                    "Plaque déclarée volée selon le dossier reçu."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        alert = Alert.objects.get(pk=response.data["id"])

        self.assertEqual(
            alert.category,
            Alert.Category.ADMINISTRATIVE,
        )
        self.assertIsNone(alert.expires_at)

    def test_admin_cannot_create_but_can_patch_manual_alert(self):
        alert = Alert.objects.create(
            created_by=self.entry,
            category=Alert.Category.ADMINISTRATIVE,
            alert_type=Alert.AlertType.WANTED_VEHICLE,
            severity=Alert.Severity.CRITICAL,
            status=Alert.Status.ACTIVE,
            source=Alert.Source.MANUAL,
            plate_number="HT-99999",
            description="Véhicule signalé recherché.",
        )

        self.auth(self.admin)

        denied = self.client.post(
            "/api/alerts/",
            {
                "alert_type": Alert.AlertType.STOLEN_PLATE,
                "plate_number": "AA-001",
                "description": "Tentative de création par administrateur.",
            },
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        updated = self.client.patch(
            f"/api/alerts/{alert.pk}/",
            {
                "description": (
                    "Véhicule signalé recherché, information confirmée."
                )
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)

    def test_entry_and_admin_can_cancel_manual_alert(self):
        alert = Alert.objects.create(
            created_by=self.field,
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.FIELD_ESCAPE,
            severity=Alert.Severity.CRITICAL,
            source=Alert.Source.MANUAL,
            description="Le véhicule a quitté le contrôle sans autorisation.",
        )

        self.auth(self.entry)
        response = self.client.post(
            f"/api/alerts/{alert.pk}/cancel/",
            {"note": "Signalement annulé après vérification."},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(
            alert.status,
            Alert.Status.CANCELLED,
        )
        self.assertEqual(
            alert.resolved_by,
            self.entry,
        )

    def test_automatic_alert_cannot_be_modified_or_cancelled(self):
        alert = Alert.objects.create(
            category=Alert.Category.AUTOMATIC,
            alert_type=Alert.AlertType.DOCUMENT_EXPIRY_WARNING,
            severity=Alert.Severity.WARNING,
            source=Alert.Source.SYSTEM,
            description="Document proche de l'expiration.",
            deduplication_key="AUTO:TEST",
        )

        self.auth(self.admin)

        patch_response = self.client.patch(
            f"/api/alerts/{alert.pk}/",
            {"description": "Modification interdite."},
            format="json",
        )
        cancel_response = self.client.post(
            f"/api/alerts/{alert.pk}/cancel/",
            {"note": "Tentative de clôture."},
            format="json",
        )

        self.assertEqual(patch_response.status_code, 400)
        self.assertEqual(cancel_response.status_code, 400)

    def test_personal_account_cannot_read(self):
        self.auth(self.personal_user)

        self.assertEqual(
            self.client.get("/api/alerts/").status_code,
            403,
        )

    def test_put_and_delete_are_disabled(self):
        alert = Alert.objects.create(
            created_by=self.field,
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.FIELD_ESCAPE,
            severity=Alert.Severity.CRITICAL,
            source=Alert.Source.MANUAL,
            description="Le véhicule a quitté le contrôle.",
        )

        self.auth(self.entry)

        self.assertEqual(
            self.client.put(
                f"/api/alerts/{alert.pk}/",
                {},
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/alerts/{alert.pk}/"
            ).status_code,
            405,
        )


class FieldAlertExpiryTests(AlertTestMixin, TestCase):
    def setUp(self):
        self.field = self.professional(
            "field.expiry@example.com",
            AgentProfile.Role.AGENT_TERRAIN,
            "ALT-EXP-001",
        )

    def test_expired_field_alert_moves_to_expired(self):
        alert = Alert.objects.create(
            created_by=self.field,
            category=Alert.Category.FIELD_REPORT,
            alert_type=Alert.AlertType.SUSPICIOUS_BEHAVIOR,
            severity=Alert.Severity.WARNING,
            source=Alert.Source.MANUAL,
            description="Comportement inhabituel observé sur le terrain.",
        )

        Alert.objects.filter(pk=alert.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        count = expire_field_alerts()

        alert.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(
            alert.status,
            Alert.Status.EXPIRED,
        )
        self.assertIsNotNone(alert.resolved_at)


class ExpiryWarningServiceTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

        self.creator = create_agent_saisie_user(
            email="expiry.creator@example.com",
            badge_number="ALT-CRT-001",
        )
        owner_person = Person.objects.create(
            nif="0012345678",
            first_name="Jean",
            last_name="Test",
        )
        self.owner = Owner.objects.create(
            person=owner_person,
            created_by=self.creator,
        )
        self.vehicle = Vehicle.objects.create(
            plate_number="HT-100",
            owner=self.owner,
            registration_valid_until=(
                self.today + timedelta(days=20)
            ),
        )
        self.person = Person.objects.create(
            nif="9988776655",
            first_name="Marie",
            last_name="Permis",
        )
        self.driver = Driver.objects.create(
            person=self.person,
            dossier_number="AB-30001-CD",
            license_type="B",
            issue_date=self.today - timedelta(days=300),
            expires_at=self.today + timedelta(days=15),
        )
        self.policy = InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="OAVCT",
            policy_number="POL-WARNING",
            valid_from=self.today - timedelta(days=300),
            valid_until=self.today + timedelta(days=25),
            status=InsurancePolicy.Status.VALID,
        )

    def test_creates_three_automatic_warnings(self):
        warnings = evaluate_document_expiry_warnings(
            driver=self.driver,
            vehicle=self.vehicle,
            today=self.today,
        )

        self.assertEqual(len(warnings), 3)

        for alert in warnings:
            self.assertEqual(
                alert.category,
                Alert.Category.AUTOMATIC,
            )
            self.assertEqual(
                alert.severity,
                Alert.Severity.WARNING,
            )
            self.assertEqual(
                alert.source,
                Alert.Source.SYSTEM,
            )
            self.assertIsNone(alert.expires_at)
            self.assertIsNotNone(
                alert.document_expires_on
            )

        reasons = {
            reason
            for alert in warnings
            for reason in alert.system_reasons
        }
        self.assertIn(
            REASON_DRIVER_LICENSE_EXPIRING,
            reasons,
        )
        self.assertIn(
            REASON_REGISTRATION_EXPIRING,
            reasons,
        )
        self.assertIn(
            REASON_INSURANCE_EXPIRING,
            reasons,
        )

    def test_warning_creation_is_idempotent(self):
        evaluate_document_expiry_warnings(
            driver=self.driver,
            vehicle=self.vehicle,
            today=self.today,
        )
        evaluate_document_expiry_warnings(
            driver=self.driver,
            vehicle=self.vehicle,
            today=self.today,
        )

        self.assertEqual(
            Alert.objects.filter(
                alert_type=(
                    Alert.AlertType.DOCUMENT_EXPIRY_WARNING
                )
            ).count(),
            3,
        )

    def test_owner_nif_uses_owner_person_nif(self):
        from apps.alerts.services import _owner_nif

        self.assertEqual(_owner_nif(self.vehicle), "0012345678")


