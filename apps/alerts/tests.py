import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.drivers.models import Driver
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle

from .models import Alert, AlertEvidence, AlertReceipt, private_alert_evidence_storage
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
            description="Le vÃƒÂ©hicule a quittÃƒÂ© le contrÃƒÂ´le sans autorisation.",
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def payload(self, alert_type, plate_number="HT-200"):
        return {
            "alert_type": alert_type,
            "plate_number": plate_number,
            "description": "Description opÃƒÂ©rationnelle suffisamment prÃƒÂ©cise.",
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
                "description": "Description corrigÃƒÂ©e par l'agent de saisie.",
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
                "description": "Description complÃƒÂ¨te mise ÃƒÂ  jour avec PUT.",
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
                {"description": "Tentative de modification refusÃƒÂ©e."},
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


class AlertReceiptApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(username="receipt_author", role="AGENT_TERRAIN")
        self.reader_a = User.objects.create_user(username="receipt_reader_a", role="AGENT_TERRAIN")
        self.reader_b = User.objects.create_user(username="receipt_reader_b", role="AGENT_SAISIE")
        self.alert = Alert.objects.create(
            created_by=self.author,
            alert_type=Alert.TYPE_FIELD_ESCAPE,
            description="Le conducteur a pris la fuite pendant le contrÃ´le.",
        )
        self.system_alert = Alert.objects.create(
            alert_type=Alert.TYPE_JUDICIAL,
            source=Alert.SOURCE_SYSTEM,
            description="Alerte automatique contextuelle.",
            deduplication_key="JUDICIAL:RECEIPT-TEST",
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def recent_unread(self):
        return self.client.get("/api/alerts/recent-unread/")

    def test_creator_is_opened_and_other_user_receives_new_manual_alert(self):
        self.auth(self.author)
        response = self.client.post(
            "/api/alerts/",
            {"alert_type": Alert.TYPE_REFUSED_CONTROL, "description": "Le conducteur refuse le contrÃ´le routier."},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created_alert = Alert.objects.get(pk=response.data["id"])
        self.assertEqual(created_alert.created_by, self.author)
        self.assertTrue(AlertReceipt.objects.filter(alert=created_alert, user=self.author, opened_at__isnull=False).exists())
        self.assertEqual(self.recent_unread().data["data"]["unread_count"], 0)

        self.auth(self.reader_a)
        unread = self.recent_unread()
        self.assertEqual(unread.data["data"]["unread_count"], 2)
        self.assertEqual(unread.data["data"]["results"][0]["id"], created_alert.id)

    def test_opening_is_per_user_and_idempotent(self):
        self.auth(self.reader_a)
        first = self.client.post(f"/api/alerts/{self.alert.pk}/mark-opened/")
        self.assertEqual(first.status_code, 200)
        receipt = AlertReceipt.objects.get(alert=self.alert, user=self.reader_a)
        opened_at = receipt.opened_at
        self.assertEqual(self.recent_unread().data["data"]["unread_count"], 0)

        second = self.client.post(f"/api/alerts/{self.alert.pk}/mark-opened/")
        self.assertEqual(second.status_code, 200)
        receipt.refresh_from_db()
        self.assertEqual(receipt.opened_at, opened_at)
        self.assertEqual(AlertReceipt.objects.filter(alert=self.alert, user=self.reader_a).count(), 1)

        self.auth(self.reader_b)
        self.assertEqual(self.recent_unread().data["data"]["unread_count"], 1)
        self.assertFalse(AlertReceipt.objects.filter(alert=self.alert, user=self.reader_b).exists())

    def test_recent_unread_excludes_system_and_opened_alerts_and_is_ordered(self):
        newer = Alert.objects.create(
            created_by=self.author,
            alert_type=Alert.TYPE_SUSPICIOUS_BEHAVIOR,
            description="Comportement suspect observÃ© pendant le contrÃ´le.",
        )
        self.auth(self.reader_a)
        AlertReceipt.objects.create(alert=self.alert, user=self.reader_a, opened_at=timezone.now())
        response = self.recent_unread()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["unread_count"], 1)
        self.assertEqual([item["id"] for item in response.data["data"]["results"]], [newer.id])
        self.assertNotIn(self.system_alert.id, [item["id"] for item in response.data["data"]["results"]])

    def test_unread_list_filter_uses_regular_pagination(self):
        self.auth(self.reader_a)
        response = self.client.get("/api/alerts/", {"unread": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.alert.id)

    def test_unread_and_mark_opened_require_authentication(self):
        self.assertEqual(self.recent_unread().status_code, 401)
        self.assertEqual(self.client.post(f"/api/alerts/{self.alert.pk}/mark-opened/").status_code, 401)

class JudicialAlertServiceTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.actor = User.objects.create_user(username="judicial_actor", role="AGENT_TERRAIN")
        self.today = timezone.localdate()
        self.owner = Owner.objects.create(full_name="Jean ContrÃƒÂ´le", national_id="001-234-567-8")
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


class AlertEvidenceApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.field = User.objects.create_user(username="evidence_field", password="Pass1234!", role="AGENT_TERRAIN")
        self.reader = User.objects.create_user(username="evidence_reader", password="Pass1234!", role="AGENT_SAISIE")
        self.temp_root = tempfile.mkdtemp()
        self.original_storage_location = private_alert_evidence_storage._location
        private_alert_evidence_storage._location = self.temp_root
        private_alert_evidence_storage.__dict__.pop("base_location", None)
        private_alert_evidence_storage.__dict__.pop("location", None)

    def tearDown(self):
        private_alert_evidence_storage._location = self.original_storage_location
        private_alert_evidence_storage.__dict__.pop("base_location", None)
        private_alert_evidence_storage.__dict__.pop("location", None)
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def auth(self, user=None):
        self.client.force_authenticate(user=user or self.field)

    def payload(self, **extra):
        data = {
            "alert_type": Alert.TYPE_FIELD_ESCAPE,
            "plate_number": "",
            "description": "Description opérationnelle suffisamment précise.",
        }
        data.update(extra)
        return data

    def upload(self, name="proof.m4a", content_type="audio/mp4", size=32):
        return SimpleUploadedFile(name, b"a" * size, content_type=content_type)

    def create_audio_alert(self):
        self.auth()
        return self.client.post(
            "/api/alerts/",
            self.payload(
                evidence_type=AlertEvidence.TYPE_AUDIO,
                evidence_file=self.upload(),
                evidence_duration_seconds=42,
            ),
            format="multipart",
        )

    def test_create_alert_without_evidence_still_works(self):
        self.auth()
        response = self.client.post("/api/alerts/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["evidence"], [])
        self.assertEqual(AlertEvidence.objects.count(), 0)

    def test_create_alert_with_valid_audio_evidence(self):
        response = self.create_audio_alert()
        self.assertEqual(response.status_code, 201, response.data)
        evidence = AlertEvidence.objects.get()
        self.assertEqual(evidence.evidence_type, AlertEvidence.TYPE_AUDIO)
        self.assertEqual(evidence.mime_type, "audio/mp4")
        self.assertEqual(evidence.duration_seconds, 42)
        self.assertEqual(evidence.created_by, self.field)
        self.assertTrue(evidence.file.name.startswith(f"alerts/{evidence.alert_id}/"))
        self.assertIn("/api/alerts/", response.data["evidence"][0]["url"])
        self.assertNotIn(self.temp_root, response.data["evidence"][0]["url"])

    def test_create_alert_with_valid_video_evidence(self):
        self.auth()
        response = self.client.post(
            "/api/alerts/",
            self.payload(
                evidence_type=AlertEvidence.TYPE_VIDEO,
                evidence_file=self.upload("proof.mp4", "video/mp4"),
                evidence_duration_seconds=12,
            ),
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        evidence = AlertEvidence.objects.get()
        self.assertEqual(evidence.evidence_type, AlertEvidence.TYPE_VIDEO)
        self.assertEqual(evidence.mime_type, "video/mp4")

    def test_invalid_mime_type_is_rejected(self):
        self.auth()
        response = self.client.post(
            "/api/alerts/",
            self.payload(evidence_type=AlertEvidence.TYPE_AUDIO, evidence_file=self.upload("proof.exe", "application/x-msdownload")),
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AlertEvidence.objects.count(), 0)

    @override_settings(ALERT_EVIDENCE_AUDIO_MAX_MB=0)
    def test_file_too_large_is_rejected(self):
        self.auth()
        response = self.client.post(
            "/api/alerts/",
            self.payload(evidence_type=AlertEvidence.TYPE_AUDIO, evidence_file=self.upload(size=1)),
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AlertEvidence.objects.count(), 0)

    def test_evidence_type_without_file_is_rejected(self):
        self.auth()
        response = self.client.post(
            "/api/alerts/",
            self.payload(evidence_type=AlertEvidence.TYPE_AUDIO),
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AlertEvidence.objects.count(), 0)

    def test_duration_limit_is_rejected(self):
        self.auth()
        response = self.client.post(
            "/api/alerts/",
            self.payload(
                evidence_type=AlertEvidence.TYPE_AUDIO,
                evidence_file=self.upload(),
                evidence_duration_seconds=999,
            ),
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AlertEvidence.objects.count(), 0)

    def test_created_by_is_backend_controlled(self):
        self.auth()
        response = self.client.post(
            "/api/alerts/",
            self.payload(created_by=self.reader.pk, evidence_type=AlertEvidence.TYPE_AUDIO, evidence_file=self.upload()),
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        evidence = AlertEvidence.objects.get()
        self.assertEqual(Alert.objects.get(pk=response.data["id"]).created_by, self.field)
        self.assertEqual(evidence.created_by, self.field)

    def test_authenticated_users_can_read_evidence_and_anonymous_cannot(self):
        create_response = self.create_audio_alert()
        self.assertEqual(create_response.status_code, 201, create_response.data)
        evidence = AlertEvidence.objects.get()
        self.auth(self.reader)
        response = self.client.get(f"/api/alerts/{evidence.alert_id}/evidence/{evidence.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.client.force_authenticate(user=None)
        anonymous = self.client.get(f"/api/alerts/{evidence.alert_id}/evidence/{evidence.pk}/")
        self.assertEqual(anonymous.status_code, 401)

class AlertHistoryListApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="history_user", password="Pass1234!", role="AGENT_TERRAIN")
        self.other = User.objects.create_user(username="history_other", password="Pass1234!", role="AGENT_SAISIE")
        self.client.force_authenticate(user=self.user)

    def create_alert(self, index, **overrides):
        data = {
            "created_by": self.user,
            "alert_type": Alert.TYPE_FIELD_ESCAPE,
            "plate_number": f"HT-{index:03d}",
            "description": f"Description historique numero {index} pour recherche.",
        }
        data.update(overrides)
        alert = Alert.objects.create(**data)
        created_at = timezone.now() - timedelta(minutes=index)
        Alert.objects.filter(pk=alert.pk).update(created_at=created_at, updated_at=created_at)
        alert.refresh_from_db()
        return alert

    def create_history_set(self, count=23):
        return [self.create_alert(index) for index in range(count)]

    def ids(self, response):
        return [item["id"] for item in response.data["results"]]

    def test_alert_history_is_ordered_by_created_at_then_id_desc(self):
        older = self.create_alert(1, plate_number="HT-OLD")
        same_time_a = self.create_alert(2, plate_number="HT-A")
        same_time_b = self.create_alert(3, plate_number="HT-B")
        newer = self.create_alert(4, plate_number="HT-NEW")
        base_time = timezone.now()
        Alert.objects.filter(pk=older.pk).update(created_at=base_time - timedelta(days=1))
        Alert.objects.filter(pk__in=[same_time_a.pk, same_time_b.pk]).update(created_at=base_time)
        Alert.objects.filter(pk=newer.pk).update(created_at=base_time + timedelta(days=1))

        response = self.client.get("/api/alerts/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ids(response)[:4], [newer.id, same_time_b.id, same_time_a.id, older.id])

    def test_alert_history_returns_ten_items_per_page_and_page_two(self):
        self.create_history_set(23)

        page_one = self.client.get("/api/alerts/", {"page": 1})
        page_two = self.client.get("/api/alerts/", {"page": 2})

        self.assertEqual(page_one.status_code, 200)
        self.assertEqual(page_one.data["count"], 23)
        self.assertEqual(len(page_one.data["results"]), 10)
        self.assertIsNotNone(page_one.data["next"])
        self.assertEqual(len(page_two.data["results"]), 10)
        self.assertIsNotNone(page_two.data["previous"])

    def test_alert_history_last_page_is_partial(self):
        self.create_history_set(23)

        response = self.client.get("/api/alerts/", {"page": 3})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 3)
        self.assertIsNone(response.data["next"])

    def test_alert_history_ignores_page_size_above_ten(self):
        self.create_history_set(12)

        response = self.client.get("/api/alerts/", {"page_size": 100})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 10)

    def test_alert_history_searches_plate_description_and_type(self):
        plate_match = self.create_alert(1, plate_number="ZZ-777", description="Controle standard.")
        description_match = self.create_alert(2, plate_number="AA-222", description="Reflet dangereux observe.")
        type_match = self.create_alert(3, alert_type=Alert.TYPE_REFUSED_CONTROL, plate_number="AA-333", description="Controle standard.")
        self.create_alert(4, plate_number="AA-444", description="Controle standard.")

        by_plate = self.client.get("/api/alerts/", {"search": "zz777"})
        by_description = self.client.get("/api/alerts/", {"search": "Reflet"})
        by_type = self.client.get("/api/alerts/", {"search": "Refus"})

        self.assertEqual(self.ids(by_plate), [plate_match.id])
        self.assertEqual(self.ids(by_description), [description_match.id])
        self.assertEqual(self.ids(by_type), [type_match.id])

    def test_alert_history_filters_one_and_multiple_types(self):
        escape = self.create_alert(1, alert_type=Alert.TYPE_FIELD_ESCAPE)
        refused = self.create_alert(2, alert_type=Alert.TYPE_REFUSED_CONTROL)
        self.create_alert(3, alert_type=Alert.TYPE_SUSPICIOUS_BEHAVIOR)

        single = self.client.get("/api/alerts/", {"alert_type": Alert.TYPE_FIELD_ESCAPE})
        multiple = self.client.get("/api/alerts/", {"alert_type": [Alert.TYPE_FIELD_ESCAPE, Alert.TYPE_REFUSED_CONTROL]})

        self.assertEqual(self.ids(single), [escape.id])
        self.assertEqual(set(self.ids(multiple)), {escape.id, refused.id})

    def test_alert_history_combines_search_and_filters(self):
        match = self.create_alert(1, alert_type=Alert.TYPE_REFUSED_CONTROL, description="Mot cle combine.")
        self.create_alert(2, alert_type=Alert.TYPE_FIELD_ESCAPE, description="Mot cle combine.")
        self.create_alert(3, alert_type=Alert.TYPE_REFUSED_CONTROL, description="Autre contenu.")

        response = self.client.get("/api/alerts/", {"search": "combine", "alert_type": Alert.TYPE_REFUSED_CONTROL})

        self.assertEqual(self.ids(response), [match.id])

    def test_alert_history_filters_severity_source_period_and_unread(self):
        critical_manual = self.create_alert(1, alert_type=Alert.TYPE_FIELD_ESCAPE, source=Alert.SOURCE_MANUAL)
        warning_manual = self.create_alert(2, alert_type=Alert.TYPE_SUSPICIOUS_BEHAVIOR, source=Alert.SOURCE_MANUAL)
        system_alert = self.create_alert(3, alert_type=Alert.TYPE_JUDICIAL, source=Alert.SOURCE_SYSTEM, deduplication_key="JUDICIAL:HISTORY")
        opened = self.create_alert(4, created_by=self.other, source=Alert.SOURCE_MANUAL)
        AlertReceipt.objects.create(alert=opened, user=self.user, opened_at=timezone.now())
        unread = self.create_alert(5, created_by=self.other, source=Alert.SOURCE_MANUAL)

        severity = self.client.get("/api/alerts/", {"severity": "WARNING"})
        source = self.client.get("/api/alerts/", {"source": Alert.SOURCE_SYSTEM})
        created_after = (timezone.now() - timedelta(days=1)).isoformat()
        created_before = (timezone.now() + timedelta(days=1)).isoformat()
        period = self.client.get("/api/alerts/", {"created_after": created_after, "created_before": created_before})
        unread_response = self.client.get("/api/alerts/", {"unread": "true"})

        self.assertEqual(self.ids(severity), [warning_manual.id])
        self.assertEqual(self.ids(source), [system_alert.id])
        self.assertIn(critical_manual.id, self.ids(period))
        self.assertIn(warning_manual.id, self.ids(period))
        self.assertIn(unread.id, self.ids(unread_response))
        self.assertNotIn(opened.id, self.ids(unread_response))

    def test_alert_history_invalid_filter_value_returns_400(self):
        response = self.client.get("/api/alerts/", {"alert_type": "UNKNOWN"})

        self.assertEqual(response.status_code, 400)

    def test_alert_history_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/alerts/")

        self.assertEqual(response.status_code, 401)

    def test_alert_history_uses_light_list_serializer_and_detail_stays_complete(self):
        alert = self.create_alert(1, description="Description detaillee conservee.")
        AlertEvidence.objects.create(
            alert=alert,
            evidence_type=AlertEvidence.TYPE_AUDIO,
            file=SimpleUploadedFile("proof.m4a", b"abc", content_type="audio/mp4"),
            mime_type="audio/mp4",
            created_by=self.user,
        )

        listing = self.client.get("/api/alerts/")
        detail = self.client.get(f"/api/alerts/{alert.pk}/")

        self.assertEqual(listing.status_code, 200)
        list_item = listing.data["results"][0]
        self.assertEqual(
            set(list_item.keys()),
            {"id", "alert_type", "alert_type_display", "severity", "plate_number", "source", "is_opened", "created_at"},
        )
        self.assertNotIn("description", list_item)
        self.assertNotIn("evidence", list_item)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["description"], "Description detaillee conservee.")
        self.assertIn("evidence", detail.data)

    def test_alert_history_list_has_no_obvious_n_plus_one_queries(self):
        self.create_history_set(10)

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as context:
            response = self.client.get("/api/alerts/")

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(context), 4)

@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class AlertRealtimeTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username="ws_creator", password="Pass1234!", role="AGENT_TERRAIN")
        self.reader = User.objects.create_user(username="ws_reader", password="Pass1234!", role="AGENT_SAISIE")
        self.inactive = User.objects.create_user(username="ws_inactive", password="Pass1234!", role="AGENT_SAISIE", is_active=False)

    def token_for(self, user):
        from rest_framework_simplejwt.tokens import AccessToken

        return str(AccessToken.for_user(user))

    def communicator_for(self, user=None, token="__missing__"):
        from channels.testing import WebsocketCommunicator
        from config.asgi import application

        if token == "__missing__":
            token = self.token_for(user)
        query = f"?token={token}" if token else ""
        return WebsocketCommunicator(
            application,
            f"/ws/alerts/{query}",
            headers=[(b"origin", b"http://testserver")],
        )

    def connect(self, communicator):
        from asgiref.sync import async_to_sync

        return async_to_sync(communicator.connect)()

    def disconnect(self, communicator):
        from asgiref.sync import async_to_sync

        try:
            async_to_sync(communicator.disconnect)()
        except BaseException:
            pass

    def test_websocket_accepts_authenticated_user(self):
        communicator = self.communicator_for(self.reader)
        connected, _ = self.connect(communicator)
        self.assertTrue(connected)
        self.disconnect(communicator)

    def expired_token(self):
        from datetime import timedelta
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(self.reader)
        token.set_exp(lifetime=timedelta(seconds=-1))
        return str(token)

    def test_websocket_rejects_missing_invalid_and_expired_token_with_4401(self):
        for communicator in (
            self.communicator_for(token=""),
            self.communicator_for(token="invalid-token"),
            self.communicator_for(token=self.expired_token()),
        ):
            connected, close_code = self.connect(communicator)
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

    def test_websocket_rejects_inactive_user_with_4403(self):
        communicator = self.communicator_for(self.inactive)
        connected, close_code = self.connect(communicator)
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    def test_recipient_service_excludes_creator_inactive_and_system_alerts(self):
        from .realtime import get_alert_recipient_users

        alert = Alert.objects.create(
            created_by=self.creator,
            alert_type=Alert.TYPE_FIELD_ESCAPE,
            description="Le conducteur a pris la fuite pendant le controle.",
        )
        recipients = get_alert_recipient_users(alert, self.creator)
        self.assertIn(self.reader, recipients)
        self.assertNotIn(self.creator, recipients)
        self.assertNotIn(self.inactive, recipients)

        system_alert = Alert.objects.create(
            alert_type=Alert.TYPE_JUDICIAL,
            source=Alert.SOURCE_SYSTEM,
            description="Alerte automatique contextuelle.",
            deduplication_key="JUDICIAL:WS-TEST",
        )
        self.assertEqual(get_alert_recipient_users(system_alert).count(), 0)

    def test_alert_created_event_contract_has_safe_summary(self):
        from .realtime import build_alert_created_event

        alert = Alert.objects.create(
            created_by=self.creator,
            alert_type=Alert.TYPE_REFUSED_CONTROL,
            plate_number="HT-404",
            description="Le conducteur refuse le controle routier avec une description suffisamment precise.",
        )
        event = build_alert_created_event(alert)
        self.assertEqual(event["type"], "alert.created")
        self.assertEqual(event["version"], 1)
        self.assertEqual(event["data"]["id"], alert.id)
        self.assertEqual(event["data"]["alert_type"], Alert.TYPE_REFUSED_CONTROL)
        self.assertEqual(event["data"]["plate_number"], "HT-404")
        self.assertEqual(event["data"]["source"], Alert.SOURCE_MANUAL)
        self.assertIn("description_preview", event["data"])
        self.assertNotIn("token", str(event).lower())
        self.assertNotIn("subject_nif", event["data"])

    def test_rest_alert_creation_schedules_broadcast_after_commit(self):
        from unittest.mock import patch

        self.client.force_authenticate(user=self.creator)
        with patch("apps.alerts.views.broadcast_alert_created") as broadcast:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/api/alerts/",
                    {"alert_type": Alert.TYPE_FIELD_ESCAPE, "description": "Le conducteur a pris la fuite pendant le controle."},
                    format="json",
                )
        self.assertEqual(response.status_code, 201, response.data)
        broadcast.assert_called_once()
        broadcasted_alert = broadcast.call_args.args[0]
        self.assertEqual(broadcasted_alert.pk, response.data["id"])
        self.assertEqual(broadcasted_alert.created_by, self.creator)