from datetime import date
from types import SimpleNamespace

from django.test import TestCase
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.models import Person
from apps.accounts.test_factories import create_agent_saisie_user
from apps.core.models import AuditLog
from apps.owners.models import Owner, VehicleOwnership
from apps.owners.serializers import EndVehicleOwnershipSerializer, OwnerSerializer, PersonInputSerializer, VehicleOwnershipSerializer
from apps.owners.services import filter_owners, filter_ownerships, owners_queryset, ownerships_queryset, set_current_vehicle_owner
from apps.vehicles.models import Vehicle


class OwnersServiceSerializerAdditionalTests(TestCase):
    def setUp(self):
        self.user = create_agent_saisie_user(email="owners.additional@example.com")
        self.request = SimpleNamespace(user=self.user, META={"REMOTE_ADDR": "127.0.0.1"})
        self.owner_a = self.owner("0010000001", "Alice", "Owner", phone="111")
        self.owner_b = self.owner("0010000002", "Bob", "Owner", phone="222", is_active=False)
        self.vehicle = Vehicle.objects.create(plate_number="OWN-900")

    def owner(self, nif, first_name, last_name, phone="", is_active=True):
        person = Person.objects.create(nif=nif, first_name=first_name, last_name=last_name)
        return Owner.objects.create(person=person, phone=phone, is_active=is_active, created_by=self.user)

    def test_filter_owners_and_ownerships_cover_supported_params(self):
        ownership = set_current_vehicle_owner(vehicle=self.vehicle, owner=self.owner_a, start_date=date(2026, 1, 1), created_by=self.user)
        self.assertEqual(list(filter_owners(owners_queryset(), {"nif": "001-000", "name": "Alice", "phone": "111", "is_active": "true", "vehicle": str(self.vehicle.pk), "plate_number": "OWN"})), [self.owner_a])
        self.assertEqual(list(filter_owners(owners_queryset(), {"is_active": "false"})), [self.owner_b])
        self.assertEqual(list(filter_ownerships(ownerships_queryset(), {"owner": str(self.owner_a.pk), "vehicle": str(self.vehicle.pk), "is_current": "true", "ownership_type": VehicleOwnership.OwnershipType.FULL_OWNER.lower()})), [ownership])
        self.assertEqual(list(filter_ownerships(ownerships_queryset(), {"is_current": "false"})), [])

    def test_set_current_vehicle_owner_validates_required_active_and_start_order(self):
        with self.assertRaises(DjangoValidationError):
            set_current_vehicle_owner(vehicle=None, owner=self.owner_a, created_by=self.user)
        with self.assertRaises(DjangoValidationError):
            set_current_vehicle_owner(vehicle=self.vehicle, owner=None, created_by=self.user)
        with self.assertRaises(DjangoValidationError):
            set_current_vehicle_owner(vehicle=self.vehicle, owner=self.owner_b, created_by=self.user)
        set_current_vehicle_owner(vehicle=self.vehicle, owner=self.owner_a, start_date=date(2026, 2, 1), created_by=self.user)
        with self.assertRaises(DjangoValidationError):
            set_current_vehicle_owner(vehicle=self.vehicle, owner=self.owner("0010000003", "Carol", "Owner"), start_date=date(2026, 1, 1), created_by=self.user)

    def test_owner_serializer_person_data_validation_and_existing_person_rules(self):
        self.assertEqual(PersonInputSerializer().validate_nif("0010000004"), "001-000-000-4")
        with self.assertRaises(DRFValidationError):
            PersonInputSerializer().validate_nif("bad")

        serializer = OwnerSerializer(data={"person_id": self.owner_a.person_id, "person_data": {"nif": "0010000005", "first_name": "X", "last_name": "Y"}}, context={"request": self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("person", serializer.errors)

        person = Person.objects.create(nif="0010000006", first_name="New", last_name="Owner")
        serializer = OwnerSerializer(data={"person_id": person.pk, "phone": "  555  "}, context={"request": self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with self.captureOnCommitCallbacks(execute=True):
            owner = serializer.save()
        self.assertEqual(owner.created_by, self.user)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.CREATE).exists())

        update = OwnerSerializer(owner, data={"person_id": self.owner_a.person_id}, partial=True, context={"request": self.request})
        self.assertFalse(update.is_valid())
        self.assertIn("person", update.errors)

    def test_vehicle_ownership_serializer_and_end_serializer(self):
        serializer = VehicleOwnershipSerializer(data={"vehicle": self.vehicle.pk, "owner": self.owner_a.pk, "start_date": "2026-01-01", "source_document_reference": " REF 001 "}, context={"request": self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        ownership = serializer.save()
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.owner, self.owner_a)
        self.assertEqual(ownership.source_document_reference, "REF 001")

        invalid_owner = VehicleOwnershipSerializer(data={"vehicle": self.vehicle.pk, "owner": self.owner_b.pk, "start_date": "2026-02-01"}, context={"request": self.request})
        self.assertFalse(invalid_owner.is_valid())
        self.assertIn("owner", invalid_owner.errors)

        end = EndVehicleOwnershipSerializer(data={"end_date": "2026-01-15", "note": " Fin normale "}, context={"request": self.request, "ownership": ownership})
        self.assertTrue(end.is_valid(), end.errors)
        ended = end.save()
        self.assertFalse(ended.is_current)
        self.assertEqual(ended.end_date, date(2026, 1, 15))
        self.assertEqual(ended.ended_by, self.user)
        self.assertIn("Fin normale", ended.note)

        again = EndVehicleOwnershipSerializer(data={"end_date": "2026-01-16"}, context={"request": self.request, "ownership": ended})
        self.assertFalse(again.is_valid())





