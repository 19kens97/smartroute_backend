from django.contrib.auth import get_user_model
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.alerts.models import Alert
from apps.tickets.models import Ticket

from .models import Driver


class DriverApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.saisie = User.objects.create_user(username="saisie_driver", password="Pass1234!", role="AGENT_SAISIE")
        self.terrain = User.objects.create_user(username="terrain_driver", password="Pass1234!", role="AGENT_TERRAIN")
        self.admin = User.objects.create_user(username="admin_driver", password="Pass1234!", role="ADMIN")
        self.today = timezone.localdate()
        self.driver = Driver.objects.create(
            dossier_number="DOS-001",
            nif="0012345678",
            full_name="Jean Permis",
            address="Delmas",
            birth_date=self.today.replace(year=self.today.year - 30),
            sex="M",
            blood_group="O+",
            license_type="B",
            issue_place="Port-au-Prince",
            issue_date=self.today - timedelta(days=365),
            expires_at=self.today + timedelta(days=365),
        )

    def auth(self, username):
        token = self.client.post(
            "/api/auth/token/",
            {"username": username, "password": "Pass1234!"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def create_driver(self, dossier_number, nif="0099988877", issue_offset=-365, expiry_offset=365, **extra):
        data = {
            "dossier_number": dossier_number,
            "nif": nif,
            "full_name": extra.pop("full_name", f"Driver {dossier_number}"),
            "address": "Delmas",
            "birth_date": self.today.replace(year=self.today.year - 30),
            "sex": "M",
            "blood_group": "O+",
            "license_type": "B",
            "issue_place": "Port-au-Prince",
            "issue_date": self.today + timedelta(days=issue_offset) if issue_offset is not None else None,
            "expires_at": self.today + timedelta(days=expiry_offset) if expiry_offset is not None else None,
        }
        data.update(extra)
        return Driver.objects.create(**data)

    def force_auth(self, user):
        self.client.force_authenticate(user=user)

    def license_payload(self, response, index=0):
        return response.data["data"]["licenses"][index]

    def test_unauthenticated_user_cannot_list_drivers(self):
        response = self.client.get("/api/drivers/")

        self.assertEqual(response.status_code, 401)

    def test_all_authenticated_roles_can_list_drivers(self):
        for user in (self.admin, self.terrain, self.saisie):
            self.force_auth(user)
            response = self.client.get("/api/drivers/")

            self.assertEqual(response.status_code, 200)
            self.assertGreaterEqual(len(response.data), 1)

    def test_all_authenticated_roles_can_retrieve_driver(self):
        for user in (self.admin, self.terrain, self.saisie):
            self.force_auth(user)
            response = self.client.get(f"/api/drivers/{self.driver.id}/")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["dossier_number"], "DOS-001")

    def test_all_authenticated_roles_can_search_by_dossier_and_nif(self):
        for user in (self.admin, self.terrain, self.saisie):
            self.force_auth(user)
            dossier_response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})
            nif_response = self.client.get("/api/drivers/search-by-nif/", {"nif": "0012345678"})

            self.assertEqual(dossier_response.status_code, 200)
            self.assertEqual(nif_response.status_code, 200)

    def test_unauthenticated_user_cannot_search_by_dossier(self):
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_user_cannot_search_by_nif(self):
        response = self.client.get("/api/drivers/search-by-nif/", {"nif": "0012345678"})

        self.assertEqual(response.status_code, 401)

    def test_admin_can_search_driver_by_dossier_number(self):
        self.force_auth(self.admin)
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(self.license_payload(response)["dossier_number"], "DOS-001")

    def test_field_agent_can_search_driver_by_nif(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-nif/", {"nif": "0012345678"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_entry_agent_can_search_driver_by_dossier_number(self):
        self.force_auth(self.saisie)
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_legacy_search_alias_still_searches_by_dossier_number(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.license_payload(response)["dossier_number"], "DOS-001")

    def test_dossier_number_is_required(self):
        self.force_auth(self.terrain)

        missing = self.client.get("/api/drivers/search-by-dossier/")
        blank = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "   "})

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(blank.status_code, 400)
        self.assertIn("dossier_number", missing.data["errors"])

    def test_nif_is_required(self):
        self.force_auth(self.terrain)

        missing = self.client.get("/api/drivers/search-by-nif/")
        blank = self.client.get("/api/drivers/search-by-nif/", {"nif": "   "})

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(blank.status_code, 400)
        self.assertIn("nif", missing.data["errors"])

    def test_no_driver_for_dossier_returns_404(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "UNKNOWN"})

        self.assertEqual(response.status_code, 404)
        self.assertIn("driver_license", response.data["errors"])

    def test_no_driver_for_nif_returns_404(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-nif/", {"nif": "404404404"})

        self.assertEqual(response.status_code, 404)
        self.assertIn("driver_license", response.data["errors"])

    def test_dossier_search_is_case_insensitive(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "dos-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.license_payload(response)["dossier_number"], "DOS-001")

    def test_nif_search_ignores_spaces_and_hyphens(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-nif/", {"nif": "001-234 567-8"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.license_payload(response)["nif"], "0012345678")

    def test_one_license_found_by_nif(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-nif/", {"nif": "0012345678"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertFalse(response.data["data"]["has_conflict"])
        self.assertTrue(self.license_payload(response)["is_currently_valid"])
        self.assertEqual(self.license_payload(response)["validity_state"], "VALID")

    def test_multiple_historical_licenses_without_overlap_have_no_conflict(self):
        nif = "1112223334"
        self.create_driver("HIST-001", nif=nif, issue_offset=-2000, expiry_offset=-1000)
        self.create_driver("HIST-002", nif=nif, issue_offset=-900, expiry_offset=-100)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-nif/", {"nif": nif})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 2)
        self.assertFalse(response.data["data"]["has_conflict"])
        self.assertEqual(response.data["data"]["active_count"], 0)

    def test_overlapping_license_periods_set_conflict(self):
        nif = "2223334445"
        first = self.create_driver("OVER-001", nif=nif, issue_offset=-1000, expiry_offset=-200)
        second = self.create_driver("OVER-002", nif=nif, issue_offset=-800, expiry_offset=-100)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-nif/", {"nif": nif})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["has_conflict"])
        self.assertEqual(set(response.data["data"]["overlapping_license_ids"]), {first.id, second.id})
        self.assertEqual(response.data["data"]["alert"]["code"], "MULTIPLE_ACTIVE_LICENSES")

    def test_multiple_currently_valid_licenses_return_business_alert(self):
        nif = "3334445556"
        self.create_driver("ACTIVE-001", nif=nif, issue_offset=-100, expiry_offset=100)
        self.create_driver("ACTIVE-002", nif=nif, issue_offset=-50, expiry_offset=200)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-nif/", {"nif": nif})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["has_conflict"])
        self.assertEqual(response.data["data"]["active_count"], 2)
        self.assertEqual(response.data["data"]["alert"]["code"], "MULTIPLE_ACTIVE_LICENSES")

    def test_expired_pending_and_unknown_validity_states(self):
        expired = self.create_driver("STATE-EXP", issue_offset=-1000, expiry_offset=-1)
        pending = self.create_driver("STATE-PEND", issue_offset=10, expiry_offset=100)
        unknown_issue = self.create_driver("STATE-UNK-ISSUE", issue_offset=None, expiry_offset=100)
        unknown_expiry = self.create_driver("STATE-UNK-EXP", issue_offset=-10, expiry_offset=None)
        self.force_auth(self.terrain)

        cases = [
            (expired, "EXPIRED", False),
            (pending, "NOT_YET_VALID", False),
            (unknown_issue, "UNKNOWN", False),
            (unknown_expiry, "UNKNOWN", False),
        ]
        for driver, state, is_valid in cases:
            response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": driver.dossier_number})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.license_payload(response)["validity_state"], state)
            self.assertEqual(self.license_payload(response)["is_currently_valid"], is_valid)

    def test_response_does_not_expose_sensitive_user_fields(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        payload = str(response.data)
        self.assertNotIn("password", payload)
        self.assertNotIn("token", payload)

    def test_dossier_search_uses_two_queries_without_n_plus_one(self):
        self.force_auth(self.terrain)

        with self.assertNumQueries(2):
            response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 200)

    def create_ticket(self, driver=None, status="VALIDATED", created_days_ago=0):
        driver = driver or self.driver
        ticket = Ticket.objects.create(
            agent=self.terrain,
            driver_license=driver.dossier_number,
            plate_number_snapshot="HT-DRIVER",
            status=status,
        )
        if created_days_ago:
            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=timezone.now() - timedelta(days=created_days_ago)
            )
            ticket.refresh_from_db()
        return ticket

    def test_search_response_contains_empty_unpaid_ticket_summary(self):
        self.force_auth(self.terrain)
        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"]["unpaid_tickets"],
            {"count": 0, "has_unpaid_tickets": False, "alert": None, "items": []},
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_one_valid_unpaid_ticket_returns_warning_without_judicial_alert(self):
        ticket = self.create_ticket(status="VALIDATED")
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        summary = response.data["data"]["unpaid_tickets"]
        self.assertEqual(summary["count"], 1)
        self.assertTrue(summary["has_unpaid_tickets"])
        self.assertEqual(summary["alert"]["code"], "UNPAID_TICKETS")
        self.assertEqual(summary["items"][0]["id"], ticket.id)
        self.assertEqual(summary["items"][0]["payment_status"], "UNPAID")
        self.assertIsNone(response.data["data"]["judicial_alert"])
        self.assertFalse(Alert.objects.filter(alert_type=Alert.TYPE_JUDICIAL).exists())

    def test_two_valid_unpaid_tickets_create_one_idempotent_judicial_alert(self):
        self.create_ticket(status="ISSUED")
        self.create_ticket(status="VALIDATED")
        self.force_auth(self.terrain)

        first = self.client.get("/api/drivers/search-by-nif/", {"nif": "001-234-567-8"})
        second = self.client.get("/api/drivers/search-by-nif/", {"nif": "0012345678"})

        self.assertEqual(first.data["data"]["unpaid_tickets"]["count"], 2)
        self.assertEqual(first.data["data"]["judicial_alert"]["code"], "JUDICIAL_ALERT")
        self.assertEqual(second.status_code, 200)
        judicial = Alert.objects.filter(
            alert_type=Alert.TYPE_JUDICIAL,
            subject_nif="0012345678",
        )
        self.assertEqual(judicial.count(), 1)
        self.assertIn("MULTIPLE_VALID_UNPAID_TICKETS", judicial.get().system_reasons)

    def test_paid_cancelled_and_non_validated_tickets_are_excluded(self):
        for status in ("PAID", "CANCELLED", "DRAFT", "PENDING_SYNC"):
            self.create_ticket(status=status)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.data["data"]["unpaid_tickets"]["count"], 0)

    def test_ticket_for_another_driver_is_excluded(self):
        other = self.create_driver("OTHER-001", nif="9988776655")
        self.create_ticket(driver=other)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.data["data"]["unpaid_tickets"]["count"], 0)

    def test_ticket_outside_control_period_is_excluded(self):
        self.create_ticket(created_days_ago=1)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-dossier/", {"dossier_number": "DOS-001"})

        self.assertEqual(response.data["data"]["unpaid_tickets"]["count"], 0)

    def test_nif_search_combines_tickets_from_all_matching_dossiers(self):
        second_driver = self.create_driver("DOS-SECOND", nif="001-234-567-8")
        self.create_ticket(driver=self.driver)
        self.create_ticket(driver=second_driver)
        self.force_auth(self.terrain)

        response = self.client.get("/api/drivers/search-by-nif/", {"nif": "001 234 567 8"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["unpaid_tickets"]["count"], 2)
        returned_ids = {item["id"] for item in response.data["data"]["unpaid_tickets"]["items"]}
        self.assertEqual(returned_ids, set(Ticket.objects.values_list("id", flat=True)))
    def test_entry_agent_can_create_driver(self):
        self.auth("saisie_driver")
        response = self.client.post(
            "/api/drivers/",
            {
                "dossier_number": "DOS-002",
                "nif": "NIF-002",
                "full_name": "Marie Permis",
                "address": "Petion-Ville",
                "birth_date": "1992-05-20",
                "sex": "F",
                "blood_group": "A+",
                "license_type": "B",
                "issue_place": "Port-au-Prince",
                "issue_date": "2024-02-01",
                "expires_at": "2029-02-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Driver.objects.filter(dossier_number="DOS-002").exists())

    def test_unauthenticated_user_cannot_create_driver(self):
        response = self.client.post(
            "/api/drivers/",
            {"dossier_number": "DOS-401", "full_name": "Anonymous", "license_type": "B"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_non_entry_agent_cannot_create_driver(self):
        self.auth("terrain_driver")
        response = self.client.post(
            "/api/drivers/",
            {"dossier_number": "DOS-003", "full_name": "Blocked", "license_type": "B"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_create_driver(self):
        self.auth("admin_driver")
        response = self.client.post(
            "/api/drivers/",
            {"dossier_number": "DOS-004", "full_name": "Admin Blocked", "license_type": "B"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_entry_agent_can_patch_driver(self):
        self.force_auth(self.saisie)
        response = self.client.patch(
            f"/api/drivers/{self.driver.id}/",
            {"address": "Carrefour"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.address, "Carrefour")

    def test_admin_cannot_patch_driver(self):
        self.force_auth(self.admin)
        response = self.client.patch(
            f"/api/drivers/{self.driver.id}/",
            {"address": "Blocked Admin"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_field_agent_cannot_patch_driver(self):
        self.force_auth(self.terrain)
        response = self.client.patch(
            f"/api/drivers/{self.driver.id}/",
            {"address": "Blocked Terrain"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_cannot_patch_driver(self):
        response = self.client.patch(
            f"/api/drivers/{self.driver.id}/",
            {"address": "Blocked Anonymous"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_put_driver_is_not_available_for_entry_agent_or_admin(self):
        for user in (self.saisie, self.admin):
            self.force_auth(user)
            response = self.client.put(
                f"/api/drivers/{self.driver.id}/",
                {
                    "dossier_number": "DOS-001",
                    "nif": "0012345678",
                    "full_name": "Jean Permis",
                    "license_type": "B",
                },
                format="json",
            )

            self.assertEqual(response.status_code, 405)

    def test_delete_driver_is_not_available(self):
        self.auth("saisie_driver")
        response = self.client.delete(f"/api/drivers/{self.driver.id}/")

        self.assertEqual(response.status_code, 405)

    def test_delete_driver_is_not_available_for_admin(self):
        self.force_auth(self.admin)
        response = self.client.delete(f"/api/drivers/{self.driver.id}/")

        self.assertEqual(response.status_code, 405)
