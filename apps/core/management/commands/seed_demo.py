from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.alerts.models import Alert
from apps.documents.models import Document
from apps.drivers.models import Driver
from apps.infractions.models import Infraction
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner
from apps.scans.models import Scan
from apps.sync.models import SyncLog
from apps.tickets.models import Ticket, TicketInfraction
from apps.vehicles.models import Vehicle

class Command(BaseCommand):
    help="Seed SmartRoute demo data"

    def handle(self, *args, **kwargs):
        User = get_user_model()

        users = {}
        user_specs = [
            ("admin", "ADMIN"),
            ("agent_terrain", "AGENT_TERRAIN"),
            ("agent_saisie", "AGENT_SAISIE"),
            ("milo", "AGENT_TERRAIN"),
        ]
        for username, role in user_specs:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@smartroute.local", "role": role},
            )
            user.role = role
            if username == "milo":
                user.first_name = "Milo"
                user.last_name = "Pierre"
                user.email = "milo@smartroute.local"
                user.badge_number = "DCPR-7421"
                user.phone = "+50937001111"
                user.precinct = "Delmas"
                user.post = "Agent de terrain"
                user.nif = "NIF-HT-009871"
            elif not user.badge_number:
                user.badge_number = f"DCPR-{1000 + len(users) + 1}"
            user.set_password("Pass1234!" if username != "milo" else "Kens1997")
            user.save()
            users[username] = user

        owners_data = [
            {"full_name": "Jean Pierre", "national_id": "HT-001", "phone": "+50937000001", "address": "Delmas 33"},
            {"full_name": "Micheline Louis", "national_id": "HT-002", "phone": "+50937000002", "address": "Petion-Ville"},
            {"full_name": "Daniel Etienne", "national_id": "HT-003", "phone": "+50937000003", "address": "Carrefour"},
        ]
        owners = []
        for data in owners_data:
            owner, _ = Owner.objects.get_or_create(national_id=data["national_id"], defaults=data)
            owners.append(owner)

        vehicles_data = [
            {"plate_number": "AA12345", "owner": owners[0], "brand": "Toyota", "model": "Corolla", "color": "Blanc", "is_wanted": False},
            {"plate_number": "BB54321", "owner": owners[1], "brand": "Nissan", "model": "Sentra", "color": "Gris", "is_wanted": True},
            {"plate_number": "CC67890", "owner": owners[2], "brand": "Hyundai", "model": "Elantra", "color": "Noir", "is_wanted": False},
        ]
        vehicles = []
        for data in vehicles_data:
            plate = data.pop("plate_number")
            vehicle, _ = Vehicle.objects.get_or_create(plate_number=plate, defaults=data)
            vehicles.append(vehicle)

        today = timezone.localdate()
        insurance_data = [
            {"vehicle": vehicles[0], "insurer": "OAVCT", "policy_number": "OAVCT-AA12345", "valid_until": today + timedelta(days=180), "status": InsurancePolicy.STATUS_VALID},
            {"vehicle": vehicles[1], "insurer": "OAVCT", "policy_number": "OAVCT-BB54321", "valid_until": today - timedelta(days=30), "status": InsurancePolicy.STATUS_EXPIRED},
            {"vehicle": vehicles[2], "insurer": "Haiti Assurance", "policy_number": "HA-CC67890", "valid_until": today + timedelta(days=90), "status": InsurancePolicy.STATUS_SUSPENDED},
        ]
        for data in insurance_data:
            policy_number = data["policy_number"]
            defaults = {key: value for key, value in data.items() if key != "policy_number"}
            InsurancePolicy.objects.update_or_create(policy_number=policy_number, defaults=defaults)
        drivers_data = [
            {
                "full_name": "Marc Louis",
                "dossier_number": "DL-10001",
                "nif": "NIF-HT-10001",
                "address": "Delmas 33",
                "birth_date": "1988-04-12",
                "sex": "M",
                "blood_group": "O+",
                "license_type": "B",
                "issue_place": "Port-au-Prince",
                "issue_date": "2024-01-15",
                "expires_at": "2029-01-15",
            },
            {
                "full_name": "Ruben Michel",
                "dossier_number": "DL-10002",
                "nif": "NIF-HT-10002",
                "address": "Petion-Ville",
                "birth_date": "1991-09-03",
                "sex": "M",
                "blood_group": "A+",
                "license_type": "B",
                "issue_place": "Port-au-Prince",
                "issue_date": "2023-08-20",
                "expires_at": "2028-08-20",
            },
            {
                "full_name": "Steeve Jean",
                "dossier_number": "DL-10003",
                "nif": "NIF-HT-10003",
                "address": "Carrefour",
                "birth_date": "1985-12-22",
                "sex": "M",
                "blood_group": "B+",
                "license_type": "C",
                "issue_place": "Port-au-Prince",
                "issue_date": "2022-06-10",
                "expires_at": "2027-06-10",
            },
        ]
        drivers = []
        for data in drivers_data:
            driver, _ = Driver.objects.get_or_create(dossier_number=data["dossier_number"], defaults=data)
            for field, value in data.items():
                setattr(driver, field, value)
            driver.save()
            drivers.append(driver)

        infractions_data = [
            {"code": "I001", "label": "Exces de vitesse", "amount": 2500, "active": True},
            {"code": "I002", "label": "Ceinture absente", "amount": 1500, "active": True},
            {"code": "I003", "label": "Stationnement interdit", "amount": 1200, "active": True},
            {"code": "I004", "label": "Assurance non presentee", "amount": 3000, "active": True},
        ]
        infractions = []
        for data in infractions_data:
            infraction, _ = Infraction.objects.get_or_create(code=data["code"], defaults=data)
            infractions.append(infraction)

        tickets_data = [
            {"agent": users["agent_terrain"], "driver_license": drivers[0].dossier_number, "plate_number_snapshot": vehicles[0].plate_number, "vehicle": vehicles[0], "status": "ISSUED", "note": "Controle regulier"},
            {"agent": users["milo"], "driver_license": drivers[1].dossier_number, "plate_number_snapshot": vehicles[1].plate_number, "vehicle": vehicles[1], "status": "PENDING_SYNC", "note": "A verifier au poste"},
            {"agent": users["agent_terrain"], "driver_license": drivers[2].dossier_number, "plate_number_snapshot": vehicles[2].plate_number, "vehicle": vehicles[2], "status": "DRAFT", "note": "Controle de routine"},
        ]
        tickets = []
        for data in tickets_data:
            ticket, _ = Ticket.objects.get_or_create(
                agent=data["agent"],
                driver_license=data["driver_license"],
                plate_number_snapshot=data["plate_number_snapshot"],
                defaults=data,
            )
            tickets.append(ticket)

        TicketInfraction.objects.get_or_create(ticket=tickets[0], infraction=infractions[0], defaults={"amount_snapshot": infractions[0].amount})
        TicketInfraction.objects.get_or_create(ticket=tickets[0], infraction=infractions[1], defaults={"amount_snapshot": infractions[1].amount})
        TicketInfraction.objects.get_or_create(ticket=tickets[1], infraction=infractions[3], defaults={"amount_snapshot": infractions[3].amount})
        TicketInfraction.objects.get_or_create(ticket=tickets[2], infraction=infractions[2], defaults={"amount_snapshot": infractions[2].amount})

        alerts_data = [
            {"created_by": users["admin"], "alert_type": "WANTED_VEHICLE", "plate_number": vehicles[1].plate_number, "description": "Vehicule recherche dans un dossier judiciaire."},
            {"created_by": users["agent_terrain"], "alert_type": "REFUSED_CONTROL", "plate_number": vehicles[2].plate_number, "description": "Refus de collaborer lors du controle."},
            {"created_by": users["admin"], "alert_type": "STOLEN_PLATE", "plate_number": "ZZ99999", "description": "Plaque signalee volee."},
        ]
        for data in alerts_data:
            Alert.objects.get_or_create(
                created_by=data["created_by"],
                alert_type=data["alert_type"],
                plate_number=data["plate_number"],
                defaults={"description": data["description"]},
            )

        scans_data = [
            {"agent": users["agent_terrain"], "plate_number": vehicles[0].plate_number, "source": "MOBILE_GEMINI"},
            {"agent": users["milo"], "plate_number": vehicles[1].plate_number, "source": "MOBILE_GEMINI"},
            {"agent": users["agent_terrain"], "plate_number": vehicles[2].plate_number, "source": "MANUAL"},
        ]
        for data in scans_data:
            Scan.objects.get_or_create(agent=data["agent"], plate_number=data["plate_number"], defaults={"source": data["source"]})

        sync_logs_data = [
            {"client_uuid": "device-001", "user": users["agent_terrain"], "direction": "PUSH", "payload": {"items": 2}, "status": "SUCCESS"},
            {"client_uuid": "device-002", "user": users["milo"], "direction": "PULL", "payload": {"last_sync": "2026-05-25T10:00:00Z"}, "status": "SUCCESS"},
            {"client_uuid": "device-001", "user": users["agent_saisie"], "direction": "PUSH", "payload": {"items": 1}, "status": "SUCCESS"},
        ]
        for data in sync_logs_data:
            SyncLog.objects.get_or_create(
                client_uuid=data["client_uuid"],
                user=data["user"],
                direction=data["direction"],
                payload=data["payload"],
                defaults={"status": data["status"]},
            )

        documents_data = [
            {"vehicle": vehicles[0], "uploaded_by": users["agent_saisie"], "title": "Assurance 2026", "filename": "assurance_aa12345.pdf"},
            {"vehicle": vehicles[1], "uploaded_by": users["admin"], "title": "Carte grise BB54321", "filename": "carte_grise_bb54321.pdf"},
        ]
        for data in documents_data:
            document, created = Document.objects.get_or_create(
                vehicle=data["vehicle"],
                title=data["title"],
                defaults={"uploaded_by": data["uploaded_by"]},
            )
            if created or not document.file:
                document.uploaded_by = data["uploaded_by"]
                document.file.save(data["filename"], ContentFile(b"SMARTROUTE DEMO DOCUMENT"), save=True)

        self.stdout.write(self.style.SUCCESS("seed_demo completed (milo password: Kens1997 | others: Pass1234!)"))
