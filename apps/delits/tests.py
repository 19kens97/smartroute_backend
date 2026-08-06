from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.accounts.models import Person, AgentProfile
from apps.drivers.models import Driver
from .models import DelitType, DelitCase
from .services import create_potential_delit_case, infer_source_type


class DelitServiceTests(TestCase):
    def setUp(self):
        User=get_user_model()
        person=Person.objects.create(nif='9900000001',first_name='Agent',last_name='Terrain')
        self.user=User.objects.create_user(person=person,account_type=User.AccountType.PROFESSIONAL,email='delit.agent@example.com',password='Pass1234!')
        AgentProfile.objects.create(user=self.user,role=AgentProfile.Role.AGENT_TERRAIN,badge_number='99-00-00-00001',is_active=True)
        driver_person=Person.objects.create(nif='9900000002',first_name='Conducteur',last_name='Test')
        self.driver=Driver.objects.create(person=driver_person,dossier_number='DE-10001-LT',license_type='B')
        self.type, _ = DelitType.objects.get_or_create(code='HIT_AND_RUN', defaults={'label':'Fuite apres accident'})

    def test_manual_creation_is_potential(self):
        case,created=create_potential_delit_case(detected_by=self.user,delit_type=self.type,source_type=DelitCase.SourceType.MANUAL_OBSERVATION,facts='Fuite observée après un accident.',driver_id=self.driver.pk)
        self.assertTrue(created)
        self.assertEqual(case.qualification_status,DelitCase.QualificationStatus.POTENTIAL)
        self.assertEqual(case.procedure_status,DelitCase.ProcedureStatus.OPEN)

    def test_infer_source_type_from_context(self):
        self.assertEqual(infer_source_type(verbalization=1), DelitCase.SourceType.VERBALIZATION)
        self.assertEqual(infer_source_type(ticket=2), DelitCase.SourceType.TICKET)
        self.assertEqual(infer_source_type(alert=3), DelitCase.SourceType.ALERT)
        self.assertEqual(infer_source_type(scan=4), DelitCase.SourceType.PLATE_SCAN)
        self.assertEqual(infer_source_type(driver=5), DelitCase.SourceType.DRIVER_SEARCH)
        self.assertEqual(infer_source_type(vehicle=6), DelitCase.SourceType.VEHICLE_CONTROL)
        self.assertEqual(infer_source_type(), DelitCase.SourceType.MANUAL_OBSERVATION)

    def test_create_potential_delit_case_infers_source_type(self):
        case,created=create_potential_delit_case(detected_by=self.user,delit_type=self.type,facts='Fuite observée après un accident.',driver=self.driver)
        self.assertTrue(created)
        self.assertEqual(case.source_type, DelitCase.SourceType.DRIVER_SEARCH)


    def test_create_from_plate_snapshot_is_plate_scan(self):
        case,created=create_potential_delit_case(
            detected_by=self.user,
            delit_type=self.type,
            facts='Fuite observee apres un accident avec plaque relevee.',
            plate_number_snapshot='aa-12345',
        )
        self.assertTrue(created)
        self.assertEqual(case.source_type, DelitCase.SourceType.PLATE_SCAN)
        self.assertEqual(case.plate_number_snapshot, 'AA-12345')
    def test_no_delete_method_in_viewset(self):
        from .views import DelitCaseViewSet
        self.assertNotIn('delete',DelitCaseViewSet.http_method_names)



    def test_send_case_to_dcpj_demo_records_tracking(self):
        from .dcpj import send_case_to_dcpj_demo
        case,created=create_potential_delit_case(
            detected_by=self.user,
            delit_type=self.type,
            facts='Fuite observee apres un accident avec conducteur identifie.',
            driver=self.driver,
            plate_number_snapshot='AA-12345',
            location_label='Delmas 33',
        )
        response=send_case_to_dcpj_demo(case,actor=self.user)
        case.refresh_from_db()
        self.assertEqual(case.dcpj_status, DelitCase.DCPJStatus.ACKNOWLEDGED)
        self.assertTrue(case.dcpj_reference.startswith('DCPJ-DEMO-'))
        self.assertEqual(response['reference'], case.dcpj_reference)
        self.assertEqual(case.dcpj_payload_snapshot['agent']['matricule'], '99-00-00-00001')
        self.assertEqual(case.dcpj_payload_snapshot['conducteur']['numero_dossier_permis'], 'DE-10001-LT')
        self.assertEqual(case.dcpj_payload_snapshot['vehicule']['immatriculation'], 'AA-12345')