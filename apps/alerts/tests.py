from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.drivers.models import Driver
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle

from .models import Alert
from .services import (
    REASON_INSURANCE_EXPIRED,
    REASON_MULTIPLE_LICENSES,
    REASON_REGISTRATION_EXPIRED,
    REASON_UNPAID_TICKETS,
    evaluate_judicial_alert,
)


class AlertApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.entry = User.objects.create_user(username="alert_entry", password="Pass1234!", role="AGENT_SAISIE")
        self.field = User.objects.create_user(username="alert_field", password="Pass1234!", role="AGENT_TERRAIN")
        self.admin = User.objects.create_user(username="alert_admin", password="Pass1234!", role="ADMIN")
        self.supervisor = User.objects.create_user(username="alert_supervisor", password="Pass1234!", role="SUPERVISEUR")
        self.alert = Alert.objects.create(
            created_by=self.field,
            alert_type=Alert.TYPE_FIELD_ESCAPE,
            plate_number="HT-100",
            description="Le véhicule a quitté le contrôle sans autorisation.",
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def payload(self, alert_type, plate_number="HT-200"):
        return {
            "alert_type": alert_type,
            "plate_number": plate_number,
            "description": "Description opérationnelle suffisamment précise.",
        }

    def test_all_authenticated_roles_can_list_and_retrieve(self):
        for user in (self.entry, self.field, self.admin, self.supervisor):
            self.auth(user)
            listing = self.client.get("/api/alerts/")
            detail = self.client.get(f"/api/alerts/{self.alert.pk}/")
            self.assertEqual(listing.status_code, 200)
            self.assertIn("results", listing.data)
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.data["alert_type_display"], "Fuite lors du contrôle")

    def test_anonymous_cannot_read(self):
        self.assertEqual(self.client.get("/api/alerts/").status_code, 401)
        self.assertEqual(self.client.get(f"/api/alerts/{self.alert.pk}/").status_code, 401)

    def test_entry_agent_creation_matrix(self):
        self.auth(self.entry)
        for alert_type in (Alert.TYPE_WANTED_VEHICLE, Alert.TYPE_STOLEN_PLATE):
            response = self.client.post("/api/alerts/", self.payload(alert_type), format="json")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["source"], Alert.SOURCE_MANUAL)
            self.assertEqual(response.data["created_by"], self.entry.pk)

        for alert_type in (
            Alert.TYPE_FIELD_ESCAPE,
            Alert.TYPE_REFUSED_CONTROL,
            Alert.TYPE_SUSPICIOUS_BEHAVIOR,
            Alert.TYPE_JUDICIAL,
        ):
            response = self.client.post("/api/alerts/", self.payload(alert_type), format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_field_agent_creation_matrix(self):
        self.auth(self.field)
        for alert_type in (
            Alert.TYPE_FIELD_ESCAPE,
            Alert.TYPE_REFUSED_CONTROL,
            Alert.TYPE_SUSPICIOUS_BEHAVIOR,
        ):
            response = self.client.post("/api/alerts/", self.payload(alert_type, plate_number=""), format="json")
            self.assertEqual(response.status_code, 201, response.data)

        for alert_type in (Alert.TYPE_WANTED_VEHICLE, Alert.TYPE_STOLEN_PLATE, Alert.TYPE_JUDICIAL):
            response = self.client.post("/api/alerts/", self.payload(alert_type), format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_admin_supervisor_and_anonymous_cannot_create(self):
        for user in (self.admin, self.supervisor):
            self.auth(user)
            self.assertEqual(
                self.client.post("/api/alerts/", self.payload(Alert.TYPE_WANTED_VEHICLE), format="json").status_code,
                403,
            )
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.post("/api/alerts/", self.payload(Alert.TYPE_FIELD_ESCAPE), format="json").status_code,
            401,
        )

    def test_plate_and_description_validation(self):
        self.auth(self.entry)
        missing_plate = self.client.post(
            "/api/alerts/",
            self.payload(Alert.TYPE_WANTED_VEHICLE, plate_number=""),
            format="json",
        )
        short_description = self.client.post(
            "/api/alerts/",
            {"alert_type": Alert.TYPE_STOLEN_PLATE, "plate_number": "AA-1", "description": "court"},
            format="json",
        )
        self.assertEqual(missing_plate.status_code, 400)
        self.assertIn("plate_number", missing_plate.data["errors"])
        self.assertEqual(short_description.status_code, 400)
        self.assertIn("description", short_description.data["errors"])

    def test_entry_agent_can_update_only_manual_description_and_plate(self):
        self.auth(self.entry)
        response = self.client.patch(
            f"/api/alerts/{self.alert.pk}/",
            {
                "plate_number": "  ht-999  ",
                "description": "Description corrigée par l'agent de saisie.",
                "created_by": self.entry.pk,
                "source": Alert.SOURCE_SYSTEM,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.plate_number, "HT-999")
        self.assertEqual(self.alert.created_by, self.field)
        self.assertEqual(self.alert.source, Alert.SOURCE_MANUAL)

    def test_entry_agent_can_put_without_redeclaring_immutable_type(self):
        self.auth(self.entry)
        response = self.client.put(
            f"/api/alerts/{self.alert.pk}/",
            {
                "plate_number": "HT-777",
                "description": "Description complète mise à jour avec PUT.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.alert_type, Alert.TYPE_FIELD_ESCAPE)
    def test_other_roles_cannot_update(self):
        for user in (self.field, self.admin, self.supervisor):
            self.auth(user)
            response = self.client.patch(
                f"/api/alerts/{self.alert.pk}/",
                {"description": "Tentative de modification refusée."},
                format="json",
            )
            self.assertEqual(response.status_code, 403)

    def test_alert_type_cannot_change(self):
        self.auth(self.entry)
        response = self.client.patch(
            f"/api/alerts/{self.alert.pk}/",
            {"alert_type": Alert.TYPE_STOLEN_PLATE},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.alert_type, Alert.TYPE_FIELD_ESCAPE)

    def test_system_judicial_alert_cannot_be_updated(self):
        judicial = Alert.objects.create(
            alert_type=Alert.TYPE_JUDICIAL,
            source=Alert.SOURCE_SYSTEM,
            description="Motif automatique.",
            deduplication_key="JUDICIAL:TEST",
        )
        self.auth(self.entry)
        response = self.client.patch(
            f"/api/alerts/{judicial.pk}/",
            {"description": "Modification manuelle interdite."},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_is_disabled_for_every_role(self):
        for user in (self.entry, self.field, self.admin, self.supervisor):
            self.auth(user)
            self.assertEqual(self.client.delete(f"/api/alerts/{self.alert.pk}/").status_code, 405)

    def test_plate_filter_is_normalized_and_case_insensitive(self):
        self.auth(self.field)
        response = self.client.get("/api/alerts/", {"plate_number": "  ht-100 "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)


class JudicialAlertServiceTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.actor = User.objects.create_user(username="judicial_actor", role="AGENT_TERRAIN")
        self.today = timezone.localdate()
        self.owner = Owner.objects.create(full_name="Jean Contrôle", national_id="001-234-567-8")
        self.vehicle = Vehicle.objects.create(
            plate_number="JD-100",
            owner=self.owner,
            registration_valid_until=self.today + timedelta(days=30),
        )

    def ticket(self, status="VALIDATED", vehicle=None):
        return Ticket.objects.create(
            agent=self.actor,
            driver_license="DRV-1",
            plate_number_snapshot=(vehicle or self.vehicle).plate_number,
            vehicle=vehicle or self.vehicle,
            status=status,
        )

    def license(self, suffix, issue_offset=-30, expiry_offset=30):
        return Driver.objects.create(
            dossier_number=f"DOS-{suffix}",
            nif="0012345678",
            full_name=f"Conducteur {suffix}",
            license_type="B",
            issue_date=self.today + timedelta(days=issue_offset),
            expires_at=self.today + timedelta(days=expiry_offset),
        )

    def test_expired_registration_creates_judicial_alert(self):
        self.vehicle.registration_valid_until = self.today - timedelta(days=1)
        self.vehicle.save()
        alert, created = evaluate_judicial_alert(vehicle=self.vehicle, actor=self.actor)
        self.assertTrue(created)
        self.assertIn(REASON_REGISTRATION_EXPIRED, alert.system_reasons)

    def test_expired_latest_insurance_creates_judicial_alert(self):
        InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="Assureur",
            policy_number="POL-EXPIRED",
            valid_until=self.today - timedelta(days=1),
            status=InsurancePolicy.STATUS_EXPIRED,
        )
        alert, _ = evaluate_judicial_alert(vehicle=self.vehicle)
        self.assertIn(REASON_INSURANCE_EXPIRED, alert.system_reasons)

    def test_two_valid_unpaid_tickets_create_judicial_alert(self):
        self.ticket("ISSUED")
        self.ticket("VALIDATED")
        alert, _ = evaluate_judicial_alert(vehicle=self.vehicle)
        self.assertIn(REASON_UNPAID_TICKETS, alert.system_reasons)

    def test_two_valid_licenses_for_same_nif_create_judicial_alert(self):
        self.license("1")
        self.license("2")
        alert, _ = evaluate_judicial_alert(nif="001-234-567-8")
        self.assertIn(REASON_MULTIPLE_LICENSES, alert.system_reasons)
        self.assertEqual(alert.plate_number, "")
        self.assertEqual(alert.subject_nif, "0012345678")

    def test_no_condition_creates_no_alert(self):
        alert, created = evaluate_judicial_alert(vehicle=self.vehicle)
        self.assertIsNone(alert)
        self.assertFalse(created)
        self.assertFalse(Alert.objects.exists())

    def test_second_identical_evaluation_is_idempotent(self):
        self.vehicle.registration_valid_until = self.today - timedelta(days=1)
        self.vehicle.save()
        first, first_created = evaluate_judicial_alert(vehicle=self.vehicle)
        second, second_created = evaluate_judicial_alert(vehicle=self.vehicle)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Alert.objects.count(), 1)

    def test_existing_alert_reasons_are_updated(self):
        self.vehicle.registration_valid_until = self.today - timedelta(days=1)
        self.vehicle.save()
        alert, _ = evaluate_judicial_alert(vehicle=self.vehicle)
        InsurancePolicy.objects.create(
            vehicle=self.vehicle,
            insurer="Assureur",
            policy_number="POL-UPDATE",
            valid_until=self.today - timedelta(days=1),
        )
        updated, created = evaluate_judicial_alert(vehicle=self.vehicle)
        self.assertFalse(created)
        self.assertEqual(alert.pk, updated.pk)
        self.assertEqual(
            updated.system_reasons,
            [REASON_REGISTRATION_EXPIRED, REASON_INSURANCE_EXPIRED],
        )

    def test_paid_cancelled_draft_and_pending_tickets_are_excluded(self):
        for status in ("PAID", "CANCELLED", "DRAFT", "PENDING_SYNC"):
            self.ticket(status)
            self.ticket(status)
        alert, _ = evaluate_judicial_alert(vehicle=self.vehicle)
        self.assertIsNone(alert)

    def test_expired_or_not_yet_valid_licenses_are_excluded(self):
        self.license("expired-1", issue_offset=-60, expiry_offset=-1)
        self.license("expired-2", issue_offset=-50, expiry_offset=-2)
        self.license("future-1", issue_offset=1, expiry_offset=30)
        self.license("future-2", issue_offset=2, expiry_offset=40)
        alert, _ = evaluate_judicial_alert(nif="0012345678")
        self.assertIsNone(alert)

    def test_control_period_is_respected(self):
        yesterday = self.today - timedelta(days=1)
        self.ticket("ISSUED")
        self.ticket("VALIDATED")
        alert, _ = evaluate_judicial_alert(
            vehicle=self.vehicle,
            period_start=yesterday,
            period_end=yesterday,
        )
        self.assertIsNone(alert)

    def test_invalid_period_rolls_back_without_alert(self):
        with self.assertRaises(ValueError):
            evaluate_judicial_alert(
                vehicle=self.vehicle,
                period_start=self.today,
                period_end=self.today - timedelta(days=1),
            )
        self.assertFalse(Alert.objects.exists())