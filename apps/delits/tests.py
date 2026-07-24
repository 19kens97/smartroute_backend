from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.accounts.models import Person, AgentProfile
from apps.drivers.models import Driver
from .models import DelitType, DelitCase
from .services import create_potential_delit_case


class DelitServiceTests(TestCase):
    def setUp(self):
        User=get_user_model()
        person=Person.objects.create(nif='DEL-AGT-1',first_name='Agent',last_name='Terrain')
        self.user=User.objects.create_user(person=person,account_type=User.AccountType.PROFESSIONAL,email='delit.agent@example.com',password='Pass1234!')
        AgentProfile.objects.create(user=self.user,role=AgentProfile.Role.AGENT_TERRAIN,badge_number='DEL-AGT-1',is_active=True)
        driver_person=Person.objects.create(nif='DEL-DRV-1',first_name='Conducteur',last_name='Test')
        self.driver=Driver.objects.create(person=driver_person,dossier_number='DEL-DRV-1',license_type='B')
        self.type=DelitType.objects.create(code='HIT_AND_RUN',label='Fuite après accident')

    def test_manual_creation_is_potential(self):
        case,created=create_potential_delit_case(detected_by=self.user,delit_type=self.type,source_type=DelitCase.SourceType.MANUAL_OBSERVATION,facts='Fuite observée après un accident.',driver_id=self.driver.pk)
        self.assertTrue(created)
        self.assertEqual(case.qualification_status,DelitCase.QualificationStatus.POTENTIAL)
        self.assertEqual(case.procedure_status,DelitCase.ProcedureStatus.OPEN)

    def test_no_delete_method_in_viewset(self):
        from .views import DelitCaseViewSet
        self.assertNotIn('delete',DelitCaseViewSet.http_method_names)
