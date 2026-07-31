
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import AgentProfile, Person
from apps.alerts.models import Alert, AlertEvidence, AlertReceipt
from apps.core.cache import invalidate_statistics_cache
from apps.delits.models import DelitAction, DelitCase, DelitEvidence, DelitStatusHistory, DelitType
from apps.documents.models import Document
from apps.drivers.models import Driver
from apps.infractions.models import Infraction
from apps.infractions.services import seed_official_infractions
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner, VehicleOwnership
from apps.owners.services import set_current_vehicle_owner
from apps.scans.models import GeminiScan, Scan
from apps.sync.models import SyncDevice, SyncItemLog, SyncSession
from apps.tickets.models import Ticket, TicketInfraction, TicketProof, TicketVerbalization
from apps.vehicles.models import Vehicle

DEMO_PASSWORD = "SmartRoute@123"
DEMO_DOMAIN = "smartroute.test"
DEMO_PREFIX = "DEMO-SR"
DEMO_NIF_PREFIX = "900"
DEMO_UUID_NS = UUID("9b2d665b-4f32-4c8f-9ec9-65af5ea3d801")
JPEG_BYTES = b"\xff\xd8\xff\xe0SMARTROUTE DEMO JPEG\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\nSMARTROUTE DEMO PNG"
PDF_BYTES = b"%PDF-1.4\n% SmartRoute PDF\n%%EOF"


def demo_uuid(name):
    return uuid5(DEMO_UUID_NS, name)


def demo_datetime(days_ago=0, hour=9, minute=0):
    day = timezone.localdate() - timedelta(days=days_ago)
    value = timezone.datetime.combine(day, timezone.datetime.min.time()) + timedelta(hours=hour, minutes=minute)
    return timezone.make_aware(value, timezone.get_current_timezone())


def set_timestamps(instance, *, days_ago=0, hour=9, minute=0, scanned=False):
    value = demo_datetime(days_ago=days_ago, hour=hour, minute=minute)
    fields = {"created_at": value, "updated_at": value}
    if scanned:
        fields["scanned_at"] = value
    instance.__class__.objects.filter(pk=instance.pk).update(**fields)
    instance.refresh_from_db()
    return instance


def split_name(full_name):
    first, last = full_name.split(" ", 1)
    return first, last


def demo_nif(value):
    number = int(demo_uuid(f"nif-{value}").hex[:12], 16) % 1_000_000
    return Person.normalize_nif(f"900{number:06d}0")


class Command(BaseCommand):
    help = "Reset and seed a complete SmartRoute dataset for local/dev only."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing SmartRoute data before seeding.")
        parser.add_argument("--no-reset", action="store_true", help="Seed/update data without deleting existing rows.")

    def guard_environment(self):
        module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        env = (os.environ.get("ENVIRONMENT", "") or getattr(settings, "ENVIRONMENT", "")).lower()
        running_tests = "test" in sys.argv
        if module == "config.settings.prod" or env == "production":
            raise CommandError("This command can only run in DEBUG/dev environment.")
        if not settings.DEBUG and not running_tests:
            raise CommandError("This command can only run in DEBUG/dev environment.")

    @transaction.atomic
    def handle(self, *args, **options):
        self.guard_environment()
        reset = options.get("reset") or not options.get("no_reset")
        if reset:
            self.reset_demo_data()
        seed_official_infractions()
        today = timezone.localdate()
        users = self.seed_users()
        owners = self.seed_owners(users)
        drivers = self.seed_drivers(users, owners, today)
        personal_users = self.seed_personal_users(drivers, owners)
        vehicles = self.seed_vehicles(users, owners, today)
        policies = self.seed_insurance(vehicles, today)
        documents = self.seed_documents(users, vehicles)
        infractions = list(Infraction.objects.filter(active=True).order_by("display_order", "code")[:10])
        if len(infractions) < 3:
            raise CommandError("Not enough active infractions to seed tickets.")
        tickets = self.seed_tickets(users, drivers, vehicles, infractions)
        proofs = self.seed_ticket_proofs(users, tickets)
        alerts = self.seed_alerts(users, vehicles, drivers, today)
        scans = self.seed_scans(users, vehicles)
        delits = self.seed_delits(users, drivers, vehicles, tickets, alerts, scans, infractions)
        sync_sessions = self.seed_sync_logs(users)
        invalidate_statistics_cache()

        counts = {
            "Persons": Person.objects.filter(nif__startswith=DEMO_NIF_PREFIX).count(),
            "Users professionnels": len(users),
            "Users personnels": len(personal_users),
            "AgentProfiles": AgentProfile.objects.filter(user__email__endswith=f"@{DEMO_DOMAIN}").count(),
            "Drivers": len(drivers),
            "Owners": len(owners),
            "Vehicles": len(vehicles),
            "VehicleOwnerships": VehicleOwnership.objects.filter(source_document_reference__startswith="DEMO-DATASET").count(),
            "InsurancePolicies": len(policies),
            "Documents": len(documents),
            "Alerts": len(alerts),
            "Scans": len(scans),
            "Tickets": len(tickets),
            "Verbalizations": TicketVerbalization.objects.filter(ticket__in=tickets).count(),
            "TicketInfractions": TicketInfraction.objects.filter(verbalization__ticket__in=tickets).count(),
            "TicketProofs": len(proofs),
            "Payments": 0,
            "Delits": len(delits),
            "SyncSessions": len(sync_sessions),
        }
        self.print_summary(counts, users)

    def table_exists(self, model):
        return model._meta.db_table in connection.introspection.table_names()

    def reset_demo_data(self):
        demo_users = get_user_model().objects.filter(email__endswith=f"@{DEMO_DOMAIN}") | get_user_model().objects.filter(person__nif__startswith=DEMO_NIF_PREFIX)
        demo_persons = Person.objects.filter(nif__startswith=DEMO_NIF_PREFIX)
        demo_vehicles = Vehicle.objects.filter(plate_number__startswith="SR")
        demo_tickets = Ticket.objects.filter(client_uuid__in=[demo_uuid(f"ticket-{i:02d}") for i in range(1, 21)])
        demo_alerts = Alert.objects.filter(deduplication_key__startswith="DEMO-DATASET:")
        demo_scans = Scan.objects.filter(plate_number__startswith="SR") | Scan.objects.filter(plate_number__startswith="UNKNOWN")
        demo_gemini = GeminiScan.objects.filter(raw_response__startswith="DEMO-DATASET:")
        if self.table_exists(DelitCase):
            demo_delits = DelitCase.objects.filter(deduplication_key__startswith="DEMO-DATASET:")
            if self.table_exists(DelitEvidence):
                DelitEvidence.objects.filter(case__in=demo_delits).delete()
            if self.table_exists(DelitAction):
                DelitAction.objects.filter(case__in=demo_delits).delete()
            if self.table_exists(DelitStatusHistory):
                DelitStatusHistory.objects.filter(case__in=demo_delits).delete()
            demo_delits.delete()
            if self.table_exists(DelitType):
                DelitType.objects.filter(code__startswith="DEMO_").delete()
        SyncItemLog.objects.filter(session__user__in=demo_users).delete()
        SyncSession.objects.filter(user__in=demo_users).delete()
        SyncDevice.objects.filter(user__in=demo_users).delete()
        AlertEvidence.objects.filter(alert__in=demo_alerts).delete()
        AlertReceipt.objects.filter(alert__in=demo_alerts).delete()
        demo_alerts.delete()
        demo_gemini.delete()
        demo_scans.delete()
        TicketProof.objects.filter(verbalization__ticket__in=demo_tickets).delete()
        TicketInfraction.objects.filter(verbalization__ticket__in=demo_tickets).delete()
        TicketVerbalization.objects.filter(ticket__in=demo_tickets).delete()
        demo_tickets.delete()
        Document.objects.filter(vehicle__in=demo_vehicles).delete()
        InsurancePolicy.objects.filter(vehicle__in=demo_vehicles).delete()
        VehicleOwnership.objects.filter(vehicle__in=demo_vehicles).delete()
        demo_vehicles.delete()
        Driver.objects.filter(person__in=demo_persons).delete()
        Owner.objects.filter(person__in=demo_persons).delete()
        AgentProfile.objects.filter(user__in=demo_users).delete()
        demo_users.delete()
        demo_persons.delete()
    def person(self, key, full_name, nif_suffix=None, birth_date=None):
        first_name, last_name = split_name(full_name)
        nif = demo_nif(nif_suffix or key) if nif_suffix is not None else None
        person, _ = Person.objects.update_or_create(
            nif=nif,
            defaults={"first_name": first_name, "last_name": last_name, "birth_date": birth_date},
        )
        return person

    def seed_users(self):
        User = get_user_model()
        specs = []
        for i in range(1, 6):
            specs.append((f"admin{i}", AgentProfile.Role.ADMIN, f"Admin Demo {i}", f"10-10-10-{i:05d}", "Direction centrale", i != 5))
        for i in range(1, 6):
            specs.append((f"saisie{i}", AgentProfile.Role.AGENT_SAISIE, f"Saisie Demo {i}", f"20-20-20-{i:05d}", "Bureau saisie", i != 5))
        for i in range(1, 6):
            specs.append((f"terrain{i}", AgentProfile.Role.AGENT_TERRAIN, f"Terrain Demo {i}", f"30-30-30-{i:05d}", "Unite terrain", i != 5))
        users = {}
        for username, role, full_name, badge, post, active in specs:
            person = self.person(username, full_name, username.upper())
            user = User.objects.filter(username=username).first() or User(username=username)
            user.person = person
            user.account_type = User.AccountType.PROFESSIONAL
            user.email = f"{username}@{DEMO_DOMAIN}"
            user.is_active = active
            user.is_staff = role == AgentProfile.Role.ADMIN
            user.is_superuser = False
            user.set_password(DEMO_PASSWORD)
            user.save()
            AgentProfile.objects.update_or_create(
                user=user,
                defaults={"role": role, "badge_number": badge, "post": post, "precinct": "Ouest", "is_active": active},
            )
            users[username] = user
        return users

    def seed_owners(self, users):
        creator = users["saisie1"]
        names = [
            "Marie Prophete", "Jacques Civil", "Nadia Transport", "Samuel Commerce", "Wideline Augustin",
            "Carline Joseph", "Patrick Louis", "Roseline Jean", "Micheline Pierre", "Entreprise Soleil",
            "Jean Baptiste", "Therese Noel", "Wilson Pierre", "Caribbean Logistics", "Ruth Saintil",
        ]
        addresses = ["Delmas 33", "Petion-Ville", "Tabarre", "Carrefour", "Delmas 75", "Croix-des-Bouquets", "Cap-Haitien", "Gonaives", "Leogane", "Port-au-Prince", "Jacmel", "Hinche", "Saint-Marc", "Aeroport", "Kenscoff"]
        owners = {}
        for index, full_name in enumerate(names, start=1):
            key = f"owner{index}"
            person = self.person(key, full_name, key.upper())
            owner, _ = Owner.objects.update_or_create(
                person=person,
                defaults={"phone": f"3701{index:04d}", "address": addresses[index - 1], "is_active": index not in {6, 15}, "created_by": creator},
            )
            owners[key] = owner
        return owners
    def seed_drivers(self, users, owners, today):
        creator = users["saisie2"]
        names = [
            "Marc Conducteur", "Ruben Michel", "Elodie Charles", "Sonia Valcin", "Wideline Augustin",
            "Patrick Louis", "Roseline Jean", "Andre Sansnif", "Milo Personnel", "Clara Route",
            "Jean Baptiste", "Therese Noel", "Wilson Pierre", "Ruth Saintil", "Lucien Taxi",
        ]
        license_types = ["B", "C", "B", "A", "D", "B", "C", "B", "TP", "PL", "B", "C", "D", "A", "TP"]
        drivers = {}
        for index, full_name in enumerate(names, start=1):
            key = f"driver{index}"
            if index in {5, 6, 7, 11, 12, 13, 14} and f"owner{index}" in owners:
                person = owners[f"owner{index}"].person
            else:
                person = self.person(key, full_name, key.upper(), date(1980 + (index % 20), ((index - 1) % 12) + 1, min(index + 1, 28)))
            expires_at = today + timedelta(days=120 + index * 30)
            if index in {2, 10, 15}:
                expires_at = today - timedelta(days=index * 7)
            if index == 4:
                expires_at = None
            driver, _ = Driver.objects.update_or_create(
                dossier_number=f"DL-{10000 + index:05d}-AA",
                defaults={
                    "person": person,
                    "address": f"Adresse DL-{10000 + index:05d}-AA",
                    "sex": Driver.Sex.FEMALE if index in {3, 4, 5, 7, 10, 12, 14} else Driver.Sex.MALE,
                    "blood_group": ["O+", "A+", "AB+", "", "O-", "B+", "A-", "", "O+", "B-", "A+", "O-", "AB-", "B+", ""][index - 1],
                    "license_type": license_types[index - 1],
                    "issue_place": "Port-au-Prince",
                    "issue_date": today - timedelta(days=900 + index),
                    "expires_at": expires_at,
                },
            )
            drivers[key] = driver
        return drivers
    def seed_personal_users(self, drivers, owners):
        User = get_user_model()
        names = [
            "Junior Citoyen", "Celine Sansvehicule", "Myrlande Etienne", "Kervens Paul", "Sabrina Joseph",
            "Daniel Alexis", "Fabienne Louis", "Stanley Noel", "Guerline Petit", "Roberto Charles",
            "Nancy Auguste", "Herve Simon", "Islande Pierre", "Patrick Mentor", "Stephanie Jean",
        ]
        users = {}
        for index, full_name in enumerate(names, start=1):
            username = f"personal{index:02d}"
            person = self.person(username, full_name, f"PERSONAL{index:02d}")
            user = User.objects.filter(username=username).first() or User(username=username)
            user.person = person
            user.account_type = User.AccountType.PERSONAL
            user.email = ""
            user.is_active = True
            user.set_password(DEMO_PASSWORD)
            user.save()
            users[username] = user
        return users
    def seed_vehicles(self, users, owners, today):
        specs = [
            ("SR10001", "Toyota", "Corolla", owners["owner1"], False, today + timedelta(days=180)),
            ("SR10002", "Nissan", "Sentra Taxi", owners["owner2"], False, today - timedelta(days=10)),
            ("SR10003", "Honda", "Moto 150", owners["owner3"], False, today + timedelta(days=90)),
            ("SR10004", "Isuzu", "NPR Camion", owners["owner3"], True, today - timedelta(days=45)),
            ("SR10005", "Toyota", "Hiace Bus", owners["owner4"], False, today + timedelta(days=20)),
            ("SR10006", "Ford", "Ranger Pickup", owners["owner5"], False, today + timedelta(days=365)),
            ("SR10007", "Hyundai", "County", owners["owner7"], False, today + timedelta(days=15)),
            ("SR10008", "Kia", "Sportage", owners["owner8"], False, None),
            ("SR10009", "Suzuki", "AX100", owners["owner9"], False, today + timedelta(days=400)),
            ("SR10010", "Mitsubishi", "Canter", owners["owner10"], False, today - timedelta(days=120)),
            ("SR10011", "Toyota", "Land Cruiser Admin", owners["owner10"], False, today + timedelta(days=800)),
            ("SR10012", "Chevrolet", "Aveo", owners["owner1"], False, today + timedelta(days=60)),
            ("SR10013", "Yamaha", "Moto Police", owners["owner10"], True, today + timedelta(days=30)),
            ("SR10014", "Mercedes", "Sprinter", owners["owner4"], False, today + timedelta(days=250)),
            ("SR10015", "Mazda", "BT-50", owners["owner5"], False, today - timedelta(days=1)),
        ]
        vehicles = {}
        for index, (plate, brand, model, owner, wanted, reg_until) in enumerate(specs, start=1):
            vehicle, _ = Vehicle.objects.update_or_create(
                plate_number=plate,
                defaults={"brand": brand, "model": model, "color": ["Blanc", "Gris", "Noir", "Bleu", "Rouge"][index % 5], "year": 2014 + (index % 10), "engine_number": f"ENG-{plate}", "registration_valid_until": reg_until, "is_wanted": wanted, "owner": owner},
            )
            if index in {4, 6, 10}:
                old_owner = owners["owner9"] if owner != owners["owner9"] else owners["owner1"]
                set_current_vehicle_owner(vehicle=vehicle, owner=old_owner, start_date=today - timedelta(days=700), source_document_reference="DEMO-DATASET-HIST", note="Ancien proprietaire.", created_by=users["saisie1"])
                set_current_vehicle_owner(vehicle=vehicle, owner=owner, start_date=today - timedelta(days=200), source_document_reference="DEMO-DATASET-CURRENT", note="Transfert.", created_by=users["saisie1"])
            else:
                set_current_vehicle_owner(vehicle=vehicle, owner=owner, start_date=today - timedelta(days=365), source_document_reference="DEMO-DATASET-CURRENT", note="Propriete courante.", created_by=users["saisie1"])
            vehicle.refresh_from_db()
            vehicles[plate] = vehicle
        return vehicles

    def seed_insurance(self, vehicles, today):
        specs = []
        for i, vehicle in enumerate(vehicles.values(), start=1):
            if i in {8, 14}:
                continue
            status = InsurancePolicy.Status.VALID
            until = today + timedelta(days=180 + i)
            if i in {2, 4, 10, 15}:
                status = InsurancePolicy.Status.EXPIRED
                until = today - timedelta(days=i)
            elif i == 5:
                status = InsurancePolicy.Status.SUSPENDED
            specs.append((vehicle, status, until))
        policies = []
        for vehicle, status, until in specs:
            policy, _ = InsurancePolicy.objects.update_or_create(
                policy_number=f"DEMO-POL-{vehicle.plate_number}",
                defaults={"vehicle": vehicle, "insurer": "OAVCT Demo", "valid_from": until - timedelta(days=365), "valid_until": until, "status": status},
            )
            policies.append(policy)
            if vehicle.plate_number in {"SR10001", "SR10002"}:
                old, _ = InsurancePolicy.objects.update_or_create(
                    policy_number=f"DEMO-POL-{vehicle.plate_number}-OLD",
                    defaults={"vehicle": vehicle, "insurer": "OAVCT Demo", "valid_from": today - timedelta(days=730), "valid_until": today - timedelta(days=366), "status": InsurancePolicy.Status.EXPIRED},
                )
                policies.append(old)
        return policies

    def seed_documents(self, users, vehicles):
        doc_cycle = [
            (Document.DocumentType.INSURANCE_COPY, "Assurance", "application/pdf", PDF_BYTES, "pdf"),
            (Document.DocumentType.REGISTRATION_COPY, "Carte grise", "application/pdf", PDF_BYTES, "pdf"),
            (Document.DocumentType.VEHICLE_PHOTO, "Photo vehicule", "image/jpeg", JPEG_BYTES, "jpg"),
            (Document.DocumentType.INSPECTION_COPY, "Inspection", "application/pdf", PDF_BYTES, "pdf"),
            (Document.DocumentType.SUPPORTING_DOCUMENT, "Document support", "application/pdf", PDF_BYTES, "pdf"),
        ]
        docs = []
        for index, (plate, vehicle) in enumerate(vehicles.items(), start=1):
            doc_type, label, mime, content, ext = doc_cycle[(index - 1) % len(doc_cycle)]
            title = f"{label} {plate}"
            document = Document.objects.filter(vehicle=vehicle, title=title).first()
            filename = f"{label.lower().replace(' ', '-')}-{plate.lower()}.{ext}"
            if document is None:
                document = Document(vehicle=vehicle, document_type=doc_type, title=title, uploaded_by=users["saisie1"], mime_type=mime, size_bytes=len(content))
                document.file.save(filename, ContentFile(content), save=True)
            else:
                document.uploaded_by = users["saisie1"]
                document.document_type = doc_type
                document.mime_type = mime
                document.size_bytes = len(content)
                document.save()
            docs.append(document)
        return docs
    def seed_tickets(self, users, drivers, vehicles, infractions):
        tickets = []
        terrain = [users["terrain1"], users["terrain2"], users["terrain3"], users["terrain4"]]
        driver_list = list(drivers.values())
        vehicle_list = list(vehicles.values())
        for i in range(1, 21):
            status = Ticket.Status.OPEN if i % 5 not in {0, 4} else (Ticket.Status.CLOSED if i % 5 == 0 else Ticket.Status.CANCELLED)
            driver = driver_list[(i - 1) % len(driver_list)]
            agent = terrain[(i - 1) % len(terrain)]
            ticket, _ = Ticket.objects.update_or_create(
                client_uuid=demo_uuid(f"ticket-{i:02d}"),
                defaults={"opened_by": agent, "driver": driver, "status": Ticket.Status.OPEN, "note": f"PV {i:02d}"},
            )
            set_timestamps(ticket, days_ago=i % 14, hour=8 + (i % 9), minute=10)
            verbalization_count = 2 if i in {3, 7, 12, 18} else 1
            for seq in range(1, verbalization_count + 1):
                vehicle = vehicle_list[(i + seq - 2) % len(vehicle_list)]
                verbalization, _ = TicketVerbalization.objects.update_or_create(
                    ticket=ticket,
                    sequence_number=seq,
                    defaults={"agent": agent, "vehicle": vehicle, "plate_number_snapshot": vehicle.plate_number, "occurred_at": demo_datetime(i % 14, 8 + (i % 9), 5 + seq), "location_label": f"Controle zone {seq}", "latitude": Decimal("18.539200"), "longitude": Decimal("-72.336400"), "note": f"Verbalisation {i:02d}-{seq}"},
                )
                for infraction in infractions[: 2 if i % 4 == 0 else 1]:
                    TicketInfraction.objects.update_or_create(verbalization=verbalization, infraction=infraction, defaults={})
            if status == Ticket.Status.CLOSED:
                ticket.status = Ticket.Status.CLOSED
                ticket.closed_by = agent
                ticket.closure_reason = "Reglement"
                ticket.save()
            elif status == Ticket.Status.CANCELLED:
                ticket.status = Ticket.Status.CANCELLED
                ticket.cancelled_by = agent
                ticket.cancellation_reason = "Annulation"
                ticket.save()
            tickets.append(ticket)
        return tickets

    def seed_ticket_proofs(self, users, tickets):
        proofs = []
        for index, ticket in enumerate(tickets[:15], start=1):
            verbalization = ticket.verbalizations.order_by("sequence_number").first()
            proof = verbalization.proofs.first()
            if proof is None:
                proof = TicketProof.objects.create(
                    verbalization=verbalization,
                    evidence_type=TicketProof.EvidenceType.PHOTO if index % 3 else TicketProof.EvidenceType.AUDIO,
                    mime_type="image/jpeg" if index % 3 else "audio/mp4",
                    size_bytes=len(JPEG_BYTES),
                    caption=f"Preuve demo {index:02d}",
                    created_by=users["terrain1"],
                )
                proof.file.save(f"proof-{ticket.ticket_number}-{index:02d}.jpg", ContentFile(JPEG_BYTES), save=True)
            proofs.append(proof)
        return proofs
    def seed_alerts(self, users, vehicles, drivers, today):
        specs = [
            ("STOLEN_MOTO", "saisie1", Alert.Category.ADMINISTRATIVE, Alert.AlertType.STOLEN_PLATE, Alert.Severity.CRITICAL, Alert.Status.ACTIVE, vehicles["SR10013"], "Plaque volee signalee sur moto administrative."),
            ("STOLEN_TAXI", "saisie2", Alert.Category.ADMINISTRATIVE, Alert.AlertType.STOLEN_PLATE, Alert.Severity.CRITICAL, Alert.Status.ACTIVE, vehicles["SR10002"], "Suspicion de plaque volee sur vehicule taxi."),
            ("WANTED_TRUCK", "saisie3", Alert.Category.ADMINISTRATIVE, Alert.AlertType.WANTED_VEHICLE, Alert.Severity.CRITICAL, Alert.Status.ACTIVE, vehicles["SR10004"], "Vehicule recherche par l'administration."),
            ("WANTED_BUS", "saisie4", Alert.Category.ADMINISTRATIVE, Alert.AlertType.WANTED_VEHICLE, Alert.Severity.WARNING, Alert.Status.ACTIVE, vehicles["SR10014"], "Verification administrative demandee sur bus."),
            ("FIELD_REFUSED_TAXI", "terrain1", Alert.Category.FIELD_REPORT, Alert.AlertType.REFUSED_CONTROL, Alert.Severity.WARNING, Alert.Status.ACTIVE, vehicles["SR10002"], "Refus de controle terrain."),
            ("FIELD_REFUSED_MOTO", "terrain2", Alert.Category.FIELD_REPORT, Alert.AlertType.REFUSED_CONTROL, Alert.Severity.WARNING, Alert.Status.ACTIVE, vehicles["SR10009"], "Conducteur reparti avant verification complete."),
            ("FIELD_ESCAPE_BUS", "terrain2", Alert.Category.FIELD_REPORT, Alert.AlertType.FIELD_ESCAPE, Alert.Severity.CRITICAL, Alert.Status.ACTIVE, vehicles["SR10007"], "Fuite observee lors d'un controle routier."),
            ("FIELD_ESCAPE_PICKUP", "terrain3", Alert.Category.FIELD_REPORT, Alert.AlertType.FIELD_ESCAPE, Alert.Severity.CRITICAL, Alert.Status.ACTIVE, vehicles["SR10006"], "Depart brusque apres injonction d'arret."),
            ("SUSPICIOUS_BUS", "terrain3", Alert.Category.FIELD_REPORT, Alert.AlertType.SUSPICIOUS_BEHAVIOR, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10005"], "Comportement suspect signale pres du terminal."),
            ("SUSPICIOUS_PICKUP", "terrain4", Alert.Category.FIELD_REPORT, Alert.AlertType.SUSPICIOUS_BEHAVIOR, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10006"], "Signalement informatif apres controle visuel."),
            ("SUSPICIOUS_SPORTAGE", "terrain5", Alert.Category.FIELD_REPORT, Alert.AlertType.SUSPICIOUS_BEHAVIOR, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10008"], "Stationnement inhabituel observe pendant la patrouille."),
            ("DOCUMENT_WARNING_PICKUP", "saisie3", Alert.Category.ADMINISTRATIVE, Alert.AlertType.DOCUMENT_EXPIRY_WARNING, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10015"], "Document proche de l'expiration."),
            ("DOCUMENT_WARNING_COUNTY", "saisie4", Alert.Category.ADMINISTRATIVE, Alert.AlertType.DOCUMENT_EXPIRY_WARNING, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10007"], "Carte grise a verifier prochainement."),
            ("DOCUMENT_WARNING_AVEO", "saisie5", Alert.Category.ADMINISTRATIVE, Alert.AlertType.DOCUMENT_EXPIRY_WARNING, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10012"], "Assurance a renouveler prochainement."),
            ("JUDICIAL_ADMIN", "admin2", Alert.Category.ADMINISTRATIVE, Alert.AlertType.JUDICIAL, Alert.Severity.WARNING, Alert.Status.ACTIVE, vehicles["SR10011"], "Alerte judiciaire administrative a verifier."),
            ("JUDICIAL_OWNER", "admin3", Alert.Category.ADMINISTRATIVE, Alert.AlertType.JUDICIAL, Alert.Severity.CRITICAL, Alert.Status.ACTIVE, vehicles["SR10010"], "Dossier judiciaire prioritaire lie au vehicule."),
            ("INFO_CONTROL", "terrain1", Alert.Category.FIELD_REPORT, Alert.AlertType.SUSPICIOUS_BEHAVIOR, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10001"], "Controle informatif ajoute au dossier de suivi."),
            ("INFO_PATROL", "terrain4", Alert.Category.FIELD_REPORT, Alert.AlertType.SUSPICIOUS_BEHAVIOR, Alert.Severity.INFO, Alert.Status.ACTIVE, vehicles["SR10003"], "Observation terrain sans action immediate."),
            ("RESOLVED_WANTED", "saisie1", Alert.Category.ADMINISTRATIVE, Alert.AlertType.WANTED_VEHICLE, Alert.Severity.WARNING, Alert.Status.RESOLVED, vehicles["SR10010"], "Alerte resolue."),
            ("CANCELLED_REFUSED", "terrain2", Alert.Category.FIELD_REPORT, Alert.AlertType.REFUSED_CONTROL, Alert.Severity.INFO, Alert.Status.CANCELLED, vehicles["SR10003"], "Signalement annule apres verification terrain."),
        ]
        alerts = []
        for key, creator_key, category, alert_type, severity, status, vehicle, description in specs:
            defaults = {"created_by": users[creator_key], "category": category, "alert_type": alert_type, "severity": severity, "status": status, "source": Alert.Source.MANUAL, "vehicle": vehicle, "plate_number": vehicle.plate_number, "description": description}
            if status == Alert.Status.RESOLVED:
                defaults.update({"resolved_by": users["admin1"], "resolution_note": "Verification administrative terminee."})
            elif status == Alert.Status.CANCELLED:
                defaults.update({"resolved_by": users["admin1"], "resolution_note": "Signalement classe sans suite apres recoupement."})
            alert, _ = Alert.objects.update_or_create(deduplication_key=f"DEMO-DATASET:ALERT:{key}", defaults=defaults)
            alerts.append(alert)
        evidence_alert = alerts[0]
        if not evidence_alert.evidence.exists():
            evidence = AlertEvidence.objects.create(alert=evidence_alert, evidence_type=AlertEvidence.EvidenceType.AUDIO, mime_type="audio/mp4", size_bytes=24, duration_seconds=12, created_by=users["terrain1"])
            evidence.file.save("alert-demo.m4a", ContentFile(b"DEMO AUDIO EVIDENCE"), save=True)
        receipt_users = [users["saisie1"], users["saisie2"], users["saisie3"], users["terrain1"], users["terrain2"], users["terrain3"], users["admin1"]]
        for alert in alerts:
            for user in receipt_users:
                AlertReceipt.objects.update_or_create(alert=alert, user=user, defaults={"opened_at": timezone.now() if alert.severity == Alert.Severity.CRITICAL else None})
        return alerts

    def seed_scans(self, users, vehicles):
        scans = []
        distribution = [(users["terrain1"], 15), (users["terrain2"], 8), (users["terrain3"], 5), (users["terrain4"], 2)]
        plates = list(vehicles.keys()) + ["UNKNOWN01", "UNKNOWN02", "UNKNOWN03"]
        index = 0
        for agent, count in distribution:
            for _ in range(count):
                plate = plates[index % len(plates)]
                scan, _ = Scan.objects.update_or_create(agent=agent, plate_number=plate, source="MANUAL" if index % 3 else "MOBILE_GEMINI", defaults={"agent": agent})
                set_timestamps(scan, days_ago=index % 12, hour=7 + (index % 10))
                scans.append(scan)
                if index < 12:
                    vehicle = vehicles.get(plate)
                    gemini, _ = GeminiScan.objects.update_or_create(
                        agent=agent,
                        raw_response=f"DEMO-DATASET:{plate}:{index}",
                        defaults={"plate_number": plate if vehicle else "", "source": "MOBILE_GEMINI", "image": ContentFile(JPEG_BYTES, name=f"scan-{index}.jpg"), "model_used": "gemini-2.5-flash", "plate_detected": bool(vehicle), "vehicle": vehicle},
                    )
                    set_timestamps(gemini, days_ago=index % 12, hour=7 + (index % 10), scanned=True)
                index += 1
        return scans

    def seed_delits(self, users, drivers, vehicles, tickets, alerts, scans, infractions):
        if not all(self.table_exists(model) for model in (DelitType, DelitCase, DelitAction, DelitEvidence)):
            self.stdout.write("Delits skipped: delits tables are not migrated in this database.")
            return []
        type_specs = [
            ("DANGEROUS_DRIVING", "Conduite dangereuse", "Manoeuvre dangereuse constatee pendant un controle.", "Code routier", 10),
            ("HIT_AND_RUN", "Fuite apres accident", "Depart du conducteur apres un accident ou dommage constate.", "Code routier", 20),
            ("DOCUMENT_FRAUD", "Fraude documentaire", "Document falsifie, incoherent ou presente comme authentique.", "Code penal :", 30),
            ("REFUSED_ORDER", "Refus d'obtemperer", "Refus d'executer une injonction reguliere d'un agent.", "Code routier", 40),
            ("RECKLESS_ENDANGERMENT", "Mise en danger", "Comportement exposant les usagers a un risque grave.", "Code penal :", 50),
            ("ROAD_INFRASTRUCTURE_DAMAGE", "Atteinte a la voie publique", "Degradation ou obstruction d'une infrastructure routiere.", "Code penal :", 60),
            ("PLATE_TAMPERING", "Manipulation de plaque", "Usage, transfert ou alteration suspecte de plaque.", "Code routier", 70),
            ("PERMIT_MISUSE", "Usage abusif de permis", "Pret, usage ou presentation irreguliere d'un permis.", "Code routier", 80),
            ("PUBLIC_TRANSPORT_ENDANGERMENT", "Transport public dangereux", "Mise en danger de passagers dans un transport public.", "Code routier", 90),
            ("IMPAIRED_DRIVING", "Conduite en etat d'ebriete", "Conduite sous influence constatee ou suspectee.", "Code routier", 100),
            ("SIGNALING_DAMAGE", "Atteinte a la signalisation", "Panneau enleve, degrade ou altere.", "Code penal :", 110),
            ("INSPECTION_FRAUD", "Fraude inspection", "Fiche d'inspection deterioree, absente ou manipulee.", "Code routier", 120),
            ("REPEAT_DANGEROUS_OFFENSE", "Recidive de conduite dangereuse", "Accumulation d'infractions graves sur un meme controle.", "Code routier", 130),
            ("VEHICLE_IDENTITY_FRAUD", "Fraude identite vehicule", "Incoherence plaque, carte ou description du vehicule.", "Code penal :", 140),
            ("AUTHORITY_OBSTRUCTION", "Obstacle a l'autorite", "Comportement entravant l'action reguliere d'un agent.", "Code penal :", 150),
        ]
        delit_types = {}
        for code, label, description, legal_basis, display_order in type_specs:
            item, _ = DelitType.objects.update_or_create(
                code=code,
                defaults={"label": label, "description": description, "legal_basis": legal_basis, "active": True, "display_order": display_order},
            )
            delit_types[code] = item

        cases = []
        type_values = list(delit_types.values())
        vehicle_values = list(vehicles.values())
        driver_values = list(drivers.values())
        status_pairs = [
            (DelitCase.QualificationStatus.POTENTIAL, DelitCase.ProcedureStatus.OPEN),
            (DelitCase.QualificationStatus.UNDER_REVIEW, DelitCase.ProcedureStatus.ACTION_TAKEN),
            (DelitCase.QualificationStatus.CONFIRMED, DelitCase.ProcedureStatus.CLOSED),
        ]
        for index in range(1, 16):
            q_status, p_status = status_pairs[(index - 1) % len(status_pairs)]
            vehicle = vehicle_values[(index - 1) % len(vehicle_values)]
            driver = driver_values[(index - 1) % len(driver_values)]
            ticket = tickets[(index - 1) % len(tickets)]
            alert = alerts[(index - 1) % len(alerts)]
            delit_type = type_values[(index - 1) % len(type_values)]
            infraction = infractions[(index - 1) % len(infractions)]
            defaults = {
                "delit_type": delit_type,
                "source_type": DelitCase.SourceType.TICKET,
                "ticket": ticket,
                "verbalization": ticket.verbalizations.first(),
                "alert": alert,
                "infraction": infraction,
                "driver": driver,
                "vehicle": vehicle,
                "plate_number_snapshot": vehicle.plate_number,
                "facts": f"Faits demo suffisamment detailles pour dossier delit {index:02d}.",
                "detected_by": users[f"terrain{((index - 1) % 5) + 1}"],
                "location_label": f"Zone controle delit {index:02d}",
                "latitude": Decimal("18.539200"),
                "longitude": Decimal("-72.336400"),
                "qualification_status": q_status,
                "procedure_status": p_status,
            }
            if q_status == DelitCase.QualificationStatus.CONFIRMED:
                defaults.update({"reviewed_by": users["admin1"], "reviewed_at": timezone.now(), "review_note": "Qualification confirmee.", "closed_by": users["admin1"], "closed_at": timezone.now(), "closure_reason": "Dossier cloture."})
            case, _ = DelitCase.objects.update_or_create(deduplication_key=f"DEMO-DATASET:DELIT:{index:02d}", defaults=defaults)
            DelitAction.objects.update_or_create(case=case, action_type=DelitAction.ActionType.IDENTITY_CHECK, defaults={"performed_by": defaults["detected_by"], "description": "Controle effectue dans le cadre du dossier."})
            if not case.evidence.exists():
                DelitEvidence.objects.create(case=case, scan=scans[(index - 1) % len(scans)], evidence_type=DelitEvidence.EvidenceType.PHOTO, mime_type="image/jpeg", size_bytes=len(JPEG_BYTES), created_by=defaults["detected_by"])
            cases.append(case)
        return cases
    def seed_sync_logs(self, users):
        sessions = []
        usernames = ["terrain1", "terrain2", "terrain3", "terrain4", "saisie1", "saisie2", "saisie3", "saisie4", "admin1", "admin2", "terrain1", "terrain2", "saisie1", "saisie2", "admin3"]
        for index, username in enumerate(usernames, start=1):
            user = users[username]
            device, _ = SyncDevice.objects.update_or_create(
                device_uuid=demo_uuid(f"device-{username}-{index:02d}"),
                user=user,
                defaults={"device_name": f"Demo device {username} {index:02d}", "platform": SyncDevice.Platform.ANDROID, "app_version": "1.0-demo"},
            )
            session, _ = SyncSession.objects.update_or_create(
                request_uuid=demo_uuid(f"sync-{username}-{index:02d}"),
                defaults={"device": device, "user": user, "direction": SyncSession.Direction.PUSH if index % 2 else SyncSession.Direction.PULL, "status": [SyncSession.Status.SUCCESS, SyncSession.Status.PENDING, SyncSession.Status.FAILED][(index - 1) % 3], "item_count": 5 * index, "success_count": max(0, 5 * index - (index % 4))},
            )
            sessions.append(session)
        return sessions
    def print_summary(self, counts, users):
        self.stdout.write(self.style.SUCCESS("Dataset SmartRoute reinitialise avec succes."))
        self.stdout.write("\nCrees :")
        for key, value in counts.items():
            self.stdout.write(f"- {key}: {value}")
        self.stdout.write("\nComptes de test :")
        for username in ["admin1", "admin2", "saisie1", "saisie2", "terrain1", "terrain2", "terrain3"]:
            self.stdout.write(f"- {users[username].email} / {DEMO_PASSWORD} / {users[username].agent_profile.role}")
        self.stdout.write("\nMot de passe uniquement local/dev, jamais production.")




