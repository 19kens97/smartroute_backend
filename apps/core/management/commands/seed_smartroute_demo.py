from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.alerts.models import Alert, AlertEvidence, AlertReceipt
from apps.alerts.services import evaluate_judicial_alert
from apps.core.cache import invalidate_statistics_cache
from apps.documents.models import Document
from apps.drivers.models import Driver
from apps.infractions.models import Infraction
from apps.infractions.services import seed_official_infractions
from apps.insurance.models import InsurancePolicy
from apps.owners.models import Owner
from apps.scans.models import GeminiScan, Scan
from apps.sync.models import SyncLog
from apps.tickets.models import Ticket, TicketInfraction, TicketProof
from apps.vehicles.models import Vehicle


DEFAULT_PASSWORD = "Pass1234!"
MILO_PASSWORD = "Kens0001"


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


def update_fields(instance, data):
    for field, value in data.items():
        setattr(instance, field, value)
    instance.save()
    return instance


def create_file_once(field, filename, content, save=True):
    if not field:
        field.save(filename, ContentFile(content), save=save)


class Command(BaseCommand):
    help = "Seed a complete SmartRoute development dataset."

    @transaction.atomic
    def handle(self, *args, **options):
        seed_official_infractions()
        today = timezone.localdate()

        users = self.seed_users()
        owners = self.seed_owners()
        vehicles = self.seed_vehicles(owners, today)
        drivers = self.seed_drivers(today)
        self.seed_insurance(vehicles, today)
        infractions = self.get_demo_infractions()
        tickets = self.seed_tickets(users, drivers, vehicles, infractions)
        self.seed_ticket_proofs(users, tickets)
        self.seed_alerts(users, vehicles, drivers, today)
        self.seed_scans(users, vehicles)
        self.seed_sync_logs(users)
        self.seed_documents(users, vehicles)

        invalidate_statistics_cache()

        self.stdout.write(
            self.style.SUCCESS(
                "seed_smartroute_demo completed "
                f"(agents={len(users)}, vehicles={len(vehicles)}, drivers={len(drivers)}, tickets={len(tickets)}, "
                f"milo password: {MILO_PASSWORD})"
            )
        )

    def seed_users(self):
        User = get_user_model()
        specs = [
            {"username": "admin", "password": DEFAULT_PASSWORD, "role": User.Role.ADMIN, "first_name": "Nadia", "last_name": "Beaubrun", "email": "admin@smartroute.local", "badge_number": "DCPR-0001", "phone": "+50937001001", "precinct": "Direction centrale", "post": "Administratrice", "nif": "NIF-HT-000001", "is_staff": True, "is_superuser": True},
            {"username": "agent_terrain", "password": DEFAULT_PASSWORD, "role": User.Role.AGENT_TERRAIN, "first_name": "Jean", "last_name": "Baptiste", "email": "terrain@smartroute.local", "badge_number": "DCPR-2104", "phone": "+50937001002", "precinct": "Delmas", "post": "Agent de terrain", "nif": "NIF-HT-000002"},
            {"username": "agent_saisie", "password": DEFAULT_PASSWORD, "role": User.Role.AGENT_SAISIE, "first_name": "Claudine", "last_name": "Etienne", "email": "saisie@smartroute.local", "badge_number": "DCPR-3108", "phone": "+50937001003", "precinct": "Petion-Ville", "post": "Agent de saisie", "nif": "NIF-HT-000003", "is_staff": True},
            {"username": "milo", "password": MILO_PASSWORD, "role": User.Role.AGENT_TERRAIN, "first_name": "Milo", "last_name": "Pierre", "email": "milo@smartroute.local", "badge_number": "DCPR-7421", "phone": "+50937001111", "precinct": "Delmas", "post": "Agent de terrain", "nif": "NIF-HT-009871"},
        ]
        users = {}
        for spec in specs:
            spec = spec.copy()
            password = spec.pop("password")
            username = spec["username"]
            user, _ = User.objects.get_or_create(username=username)
            update_fields(user, spec)
            user.set_password(password)
            user.save()
            users[username] = user
        return users

    def seed_owners(self):
        specs = [
            {"full_name": "Jean Pierre", "national_id": "NIF-HT-100001", "phone": "+50937000001", "address": "Delmas 33"},
            {"full_name": "Micheline Louis", "national_id": "NIF-HT-100002", "phone": "+50937000002", "address": "Petion-Ville"},
            {"full_name": "Daniel Etienne", "national_id": "NIF-HT-100003", "phone": "+50937000003", "address": "Carrefour"},
            {"full_name": "Rachelle Francois", "national_id": "NIF-HT-100004", "phone": "+50937000004", "address": "Tabarre"},
            {"full_name": "Samuelle Joseph", "national_id": "NIF-HT-100005", "phone": "+50937000005", "address": "Croix-des-Bouquets"},
        ]
        owners = {}
        for spec in specs:
            owner, _ = Owner.objects.update_or_create(national_id=spec["national_id"], defaults=spec)
            owners[spec["national_id"]] = owner
        return owners

    def seed_vehicles(self, owners, today):
        specs = [
            {"plate_number": "AA12345", "owner": owners["NIF-HT-100001"], "brand": "Toyota", "model": "Corolla", "color": "Blanc", "year": 2018, "engine_number": "ENG-AA-12345", "registration_valid_until": today + timedelta(days=180), "is_wanted": False},
            {"plate_number": "BB54321", "owner": owners["NIF-HT-100002"], "brand": "Nissan", "model": "Sentra", "color": "Gris", "year": 2017, "engine_number": "ENG-BB-54321", "registration_valid_until": today - timedelta(days=20), "is_wanted": True},
            {"plate_number": "CC67890", "owner": owners["NIF-HT-100003"], "brand": "Hyundai", "model": "Elantra", "color": "Noir", "year": 2020, "engine_number": "ENG-CC-67890", "registration_valid_until": today + timedelta(days=60), "is_wanted": False},
            {"plate_number": "DD24680", "owner": owners["NIF-HT-100004"], "brand": "Kia", "model": "Sportage", "color": "Rouge", "year": 2021, "engine_number": "ENG-DD-24680", "registration_valid_until": today + timedelta(days=15), "is_wanted": False},
            {"plate_number": "EE13579", "owner": owners["NIF-HT-100005"], "brand": "Isuzu", "model": "NPR", "color": "Bleu", "year": 2015, "engine_number": "ENG-EE-13579", "registration_valid_until": today - timedelta(days=90), "is_wanted": False},
        ]
        vehicles = {}
        for spec in specs:
            vehicle, _ = Vehicle.objects.update_or_create(plate_number=spec["plate_number"], defaults=spec)
            vehicles[vehicle.plate_number] = vehicle
        return vehicles

    def seed_drivers(self, today):
        specs = [
            {"dossier_number": "DL-10001", "nif": "NIF-HT-100001", "full_name": "Marc Louis", "address": "Delmas 33", "birth_date": date(1988, 4, 12), "sex": "M", "blood_group": "O+", "license_type": "B", "issue_place": "Port-au-Prince", "issue_date": today - timedelta(days=700), "expires_at": today + timedelta(days=900)},
            {"dossier_number": "DL-10002", "nif": "NIF-HT-100002", "full_name": "Ruben Michel", "address": "Petion-Ville", "birth_date": date(1991, 9, 3), "sex": "M", "blood_group": "A+", "license_type": "B", "issue_place": "Port-au-Prince", "issue_date": today - timedelta(days=900), "expires_at": today + timedelta(days=400)},
            {"dossier_number": "DL-10003", "nif": "NIF-HT-100003", "full_name": "Steeve Jean", "address": "Carrefour", "birth_date": date(1985, 12, 22), "sex": "M", "blood_group": "B+", "license_type": "C", "issue_place": "Port-au-Prince", "issue_date": today - timedelta(days=1600), "expires_at": today - timedelta(days=30)},
            {"dossier_number": "DL-20001", "nif": "NIF-HT-200200", "full_name": "Elodie Charles", "address": "Tabarre", "birth_date": date(1994, 2, 18), "sex": "F", "blood_group": "AB+", "license_type": "B", "issue_place": "Port-au-Prince", "issue_date": today - timedelta(days=300), "expires_at": today + timedelta(days=1500)},
            {"dossier_number": "DL-20002", "nif": "NIF-HT-200200", "full_name": "Elodie Charles", "address": "Tabarre", "birth_date": date(1994, 2, 18), "sex": "F", "blood_group": "AB+", "license_type": "C", "issue_place": "Cap-Haitien", "issue_date": today - timedelta(days=120), "expires_at": today + timedelta(days=1600)},
        ]
        drivers = {}
        for spec in specs:
            driver, _ = Driver.objects.update_or_create(dossier_number=spec["dossier_number"], defaults=spec)
            drivers[spec["dossier_number"]] = driver
        return drivers

    def seed_insurance(self, vehicles, today):
        specs = [
            {"vehicle": vehicles["AA12345"], "insurer": "OAVCT", "policy_number": "OAVCT-AA12345-2026", "valid_until": today + timedelta(days=180), "status": InsurancePolicy.STATUS_VALID},
            {"vehicle": vehicles["BB54321"], "insurer": "OAVCT", "policy_number": "OAVCT-BB54321-2026", "valid_until": today - timedelta(days=30), "status": InsurancePolicy.STATUS_EXPIRED},
            {"vehicle": vehicles["CC67890"], "insurer": "Haiti Assurance", "policy_number": "HA-CC67890-2026", "valid_until": today + timedelta(days=90), "status": InsurancePolicy.STATUS_SUSPENDED},
            {"vehicle": vehicles["DD24680"], "insurer": "Caribe Assurance", "policy_number": "CA-DD24680-2026", "valid_until": today + timedelta(days=15), "status": InsurancePolicy.STATUS_VALID},
            {"vehicle": vehicles["EE13579"], "insurer": "OAVCT", "policy_number": "OAVCT-EE13579-2026", "valid_until": today - timedelta(days=5), "status": InsurancePolicy.STATUS_EXPIRED},
        ]
        for spec in specs:
            InsurancePolicy.objects.update_or_create(policy_number=spec["policy_number"], defaults=spec)

    def get_demo_infractions(self):
        codes = ["I006", "I010", "I019", "I020", "I034", "I036", "I059"]
        return {item.code: item for item in Infraction.objects.filter(code__in=codes, active=True)}

    def seed_tickets(self, users, drivers, vehicles, infractions):
        specs = [
            {"client_uuid": UUID("11111111-1111-4111-8111-111111111111"), "agent": users["agent_terrain"], "driver": drivers["DL-10001"], "vehicle": vehicles["AA12345"], "status": "ISSUED", "days_ago": 0, "hour": 8, "note": "Controle regulier, PV impaye valide.", "codes": ["I019", "I020"], "location_label": "Delmas 33"},
            {"client_uuid": UUID("22222222-2222-4222-8222-222222222222"), "agent": users["milo"], "driver": drivers["DL-10001"], "vehicle": vehicles["AA12345"], "status": "VALIDATED", "days_ago": 0, "hour": 10, "note": "Deuxieme PV valide pour tester les alertes judiciaires.", "codes": ["I006"], "location_label": "Route de Delmas"},
            {"client_uuid": UUID("33333333-3333-4333-8333-333333333333"), "agent": users["milo"], "driver": drivers["DL-10002"], "vehicle": vehicles["BB54321"], "status": "PENDING_SYNC", "days_ago": 1, "hour": 14, "note": "PV en attente de synchronisation.", "codes": ["I010", "I036"], "location_label": "Petion-Ville"},
            {"client_uuid": UUID("44444444-4444-4444-8444-444444444444"), "agent": users["agent_terrain"], "driver": drivers["DL-10003"], "vehicle": vehicles["CC67890"], "status": "DRAFT", "days_ago": 2, "hour": 9, "note": "Brouillon pour reprise mobile.", "codes": ["I034"], "location_label": "Carrefour"},
            {"client_uuid": UUID("55555555-5555-4555-8555-555555555555"), "agent": users["agent_saisie"], "driver": drivers["DL-20001"], "vehicle": vehicles["DD24680"], "status": "PAID", "days_ago": 3, "hour": 11, "note": "PV regle.", "codes": ["I059"], "location_label": "Tabarre"},
            {"client_uuid": UUID("66666666-6666-4666-8666-666666666666"), "agent": users["agent_terrain"], "driver": drivers["DL-20002"], "vehicle": vehicles["EE13579"], "status": "CANCELLED", "days_ago": 5, "hour": 16, "note": "PV annule apres verification administrative.", "codes": ["I036"], "location_label": "Croix-des-Bouquets"},
            {"client_uuid": UUID("77777777-7777-4777-8777-777777777777"), "agent": users["milo"], "driver": drivers["DL-10002"], "vehicle": vehicles["BB54321"], "status": "ISSUED", "days_ago": 7, "hour": 13, "note": "PV plus ancien pour statistiques 31 jours.", "codes": ["I019"], "location_label": "Bourdon"},
        ]
        tickets = {}
        for spec in specs:
            ticket, _ = Ticket.objects.update_or_create(
                client_uuid=spec["client_uuid"],
                defaults={
                    "agent": spec["agent"],
                    "driver_license": spec["driver"].dossier_number,
                    "driver_name_snapshot": spec["driver"].full_name,
                    "plate_number_snapshot": spec["vehicle"].plate_number,
                    "vehicle": spec["vehicle"],
                    "status": spec["status"],
                    "note": spec["note"],
                    "occurred_at": demo_datetime(spec["days_ago"], spec["hour"], 5),
                    "location_label": spec["location_label"],
                    "latitude": Decimal("18.539200"),
                    "longitude": Decimal("-72.336400"),
                },
            )
            set_timestamps(ticket, days_ago=spec["days_ago"], hour=spec["hour"], minute=10)
            for code in spec["codes"]:
                infraction = infractions[code]
                TicketInfraction.objects.update_or_create(ticket=ticket, infraction=infraction, defaults={"amount_snapshot": infraction.amount or 0})
            tickets[str(spec["client_uuid"])] = ticket
        return tickets

    def seed_ticket_proofs(self, users, tickets):
        specs = [
            {"ticket": tickets["11111111-1111-4111-8111-111111111111"], "evidence_type": TicketProof.EVIDENCE_PHOTO, "filename": "pv-aa12345-photo.jpg", "content": b"SMARTROUTE DEMO PHOTO", "mime_type": "image/jpeg", "caption": "Photo plaque et contexte."},
            {"ticket": tickets["22222222-2222-4222-8222-222222222222"], "evidence_type": TicketProof.EVIDENCE_AUDIO, "filename": "pv-aa12345-audio.m4a", "content": b"SMARTROUTE DEMO AUDIO", "mime_type": "audio/m4a", "caption": "Note vocale de controle.", "duration_seconds": 18},
            {"ticket": tickets["33333333-3333-4333-8333-333333333333"], "evidence_type": TicketProof.EVIDENCE_VIDEO, "filename": "pv-bb54321-video.mp4", "content": b"SMARTROUTE DEMO VIDEO", "mime_type": "video/mp4", "caption": "Video courte du controle.", "duration_seconds": 12},
        ]
        for spec in specs:
            proof = TicketProof.objects.filter(ticket=spec["ticket"], evidence_type=spec["evidence_type"]).first()
            if proof is None:
                proof = TicketProof.objects.create(ticket=spec["ticket"], evidence_type=spec["evidence_type"], mime_type=spec["mime_type"], size_bytes=len(spec["content"]), duration_seconds=spec.get("duration_seconds"), caption=spec["caption"], created_by=users["milo"])
            else:
                update_fields(proof, {"mime_type": spec["mime_type"], "size_bytes": len(spec["content"]), "duration_seconds": spec.get("duration_seconds"), "caption": spec["caption"], "created_by": users["milo"]})
            create_file_once(proof.file, spec["filename"], spec["content"])

    def seed_alerts(self, users, vehicles, drivers, today):
        specs = [
            {"deduplication_key": "DEMO:ALERT:FIELD_ESCAPE:DD24680", "created_by": users["milo"], "alert_type": Alert.TYPE_FIELD_ESCAPE, "plate_number": vehicles["DD24680"].plate_number, "description": "Le conducteur a quitte le point de controle avant la fin de la verification.", "source": Alert.SOURCE_MANUAL, "days_ago": 0},
            {"deduplication_key": "DEMO:ALERT:REFUSED_CONTROL:CC67890", "created_by": users["agent_terrain"], "alert_type": Alert.TYPE_REFUSED_CONTROL, "plate_number": vehicles["CC67890"].plate_number, "description": "Refus de presenter les documents demandes par l'agent.", "source": Alert.SOURCE_MANUAL, "days_ago": 1},
            {"deduplication_key": "DEMO:ALERT:SUSPICIOUS_BEHAVIOR:AA12345", "created_by": users["milo"], "alert_type": Alert.TYPE_SUSPICIOUS_BEHAVIOR, "plate_number": vehicles["AA12345"].plate_number, "description": "Comportement incoherent pendant le controle routier.", "source": Alert.SOURCE_MANUAL, "days_ago": 2},
            {"deduplication_key": "DEMO:ALERT:WANTED_VEHICLE:BB54321", "created_by": users["agent_saisie"], "alert_type": Alert.TYPE_WANTED_VEHICLE, "plate_number": vehicles["BB54321"].plate_number, "description": "Vehicule recherche signale par le service de renseignement.", "source": Alert.SOURCE_MANUAL, "days_ago": 3},
            {"deduplication_key": "DEMO:ALERT:STOLEN_PLATE:ZZ99999", "created_by": users["agent_saisie"], "alert_type": Alert.TYPE_STOLEN_PLATE, "plate_number": "ZZ99999", "description": "Plaque volee a surveiller lors des controles.", "source": Alert.SOURCE_MANUAL, "days_ago": 4},
        ]
        alerts = []
        for spec in specs:
            spec = spec.copy()
            days_ago = spec.pop("days_ago")
            alert, _ = Alert.objects.update_or_create(deduplication_key=spec["deduplication_key"], defaults=spec)
            set_timestamps(alert, days_ago=days_ago, hour=12)
            alerts.append(alert)

        evaluate_judicial_alert(vehicle=vehicles["AA12345"], nif=drivers["DL-10001"].nif, period_start=today, period_end=today, actor=users["milo"])
        evaluate_judicial_alert(vehicle=vehicles["BB54321"], nif=drivers["DL-10002"].nif, period_start=today, period_end=today, actor=users["milo"])
        evaluate_judicial_alert(nif=drivers["DL-20001"].nif, period_start=today, period_end=today, actor=users["agent_saisie"])

        if not AlertEvidence.objects.filter(alert=alerts[0], evidence_type=AlertEvidence.TYPE_AUDIO).exists():
            evidence = AlertEvidence.objects.create(alert=alerts[0], evidence_type=AlertEvidence.TYPE_AUDIO, mime_type="audio/m4a", size_bytes=21, duration_seconds=16, created_by=users["milo"])
            evidence.file.save("alert-field-escape.m4a", ContentFile(b"SMARTROUTE ALERT AUDIO"), save=True)

        for alert in Alert.objects.filter(deduplication_key__startswith="DEMO:ALERT:"):
            AlertReceipt.objects.update_or_create(
                alert=alert,
                user=users["agent_saisie"],
                defaults={"opened_at": timezone.now() if alert.alert_type in {Alert.TYPE_WANTED_VEHICLE, Alert.TYPE_STOLEN_PLATE} else None},
            )

    def seed_scans(self, users, vehicles):
        scan_specs = [
            {"agent": users["agent_terrain"], "plate_number": vehicles["AA12345"].plate_number, "source": "MOBILE_GEMINI", "days_ago": 0, "hour": 7},
            {"agent": users["milo"], "plate_number": vehicles["BB54321"].plate_number, "source": "MANUAL", "days_ago": 0, "hour": 9},
            {"agent": users["milo"], "plate_number": "UNKNOWN01", "source": "MOBILE_GEMINI", "days_ago": 1, "hour": 13},
            {"agent": users["agent_terrain"], "plate_number": vehicles["CC67890"].plate_number, "source": "OFFLINE_QUEUE", "days_ago": 3, "hour": 15},
        ]
        for spec in scan_specs:
            scan, _ = Scan.objects.update_or_create(agent=spec["agent"], plate_number=spec["plate_number"], source=spec["source"], defaults={"agent": spec["agent"]})
            set_timestamps(scan, days_ago=spec["days_ago"], hour=spec["hour"])

        gemini_specs = [
            {"agent": users["milo"], "plate_number": vehicles["AA12345"].plate_number, "vehicle": vehicles["AA12345"], "model_used": "gemini-2.5-flash", "raw_response": "AA12345", "plate_detected": True, "days_ago": 0, "hour": 8},
            {"agent": users["agent_terrain"], "plate_number": "", "vehicle": None, "model_used": "gemini-2.5-flash", "raw_response": "gemini_value_error", "plate_detected": False, "days_ago": 2, "hour": 10},
        ]
        for spec in gemini_specs:
            gemini, _ = GeminiScan.objects.update_or_create(
                agent=spec["agent"],
                raw_response=spec["raw_response"],
                defaults={"plate_number": spec["plate_number"], "source": "MOBILE_GEMINI", "model_used": spec["model_used"], "plate_detected": spec["plate_detected"], "vehicle": spec["vehicle"]},
            )
            set_timestamps(gemini, days_ago=spec["days_ago"], hour=spec["hour"], scanned=True)

    def seed_sync_logs(self, users):
        specs = [
            {"client_uuid": "device-delmas-001", "user": users["agent_terrain"], "direction": "PUSH", "payload": {"items": 4}, "status": "SUCCESS"},
            {"client_uuid": "device-milo-7421", "user": users["milo"], "direction": "PUSH", "payload": {"tickets": 1}, "status": "PENDING"},
            {"client_uuid": "device-saisie-3108", "user": users["agent_saisie"], "direction": "PULL", "payload": {"alerts": 2}, "status": "FAILED"},
        ]
        for spec in specs:
            SyncLog.objects.update_or_create(client_uuid=spec["client_uuid"], user=spec["user"], direction=spec["direction"], defaults={"payload": spec["payload"], "status": spec["status"]})

    def seed_documents(self, users, vehicles):
        specs = [
            {"vehicle": vehicles["AA12345"], "uploaded_by": users["agent_saisie"], "title": "Assurance valide AA12345", "filename": "assurance_aa12345.pdf"},
            {"vehicle": vehicles["BB54321"], "uploaded_by": users["agent_saisie"], "title": "Carte grise expiree BB54321", "filename": "carte_grise_bb54321.pdf"},
            {"vehicle": vehicles["CC67890"], "uploaded_by": users["admin"], "title": "Assurance suspendue CC67890", "filename": "assurance_cc67890.pdf"},
            {"vehicle": vehicles["EE13579"], "uploaded_by": users["admin"], "title": "Immatriculation expiree EE13579", "filename": "immatriculation_ee13579.pdf"},
        ]
        for spec in specs:
            document, _ = Document.objects.get_or_create(vehicle=spec["vehicle"], title=spec["title"], defaults={"uploaded_by": spec["uploaded_by"]})
            document.uploaded_by = spec["uploaded_by"]
            document.save()
            create_file_once(document.file, spec["filename"], b"SMARTROUTE DEMO DOCUMENT")
