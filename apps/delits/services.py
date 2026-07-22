import hashlib
import secrets
from django.db import transaction
from django.utils import timezone
from .models import DelitCase, DelitStatusHistory


def generate_case_number():
    year = timezone.localdate().year
    for _ in range(20):
        value = f"DEL-{year}-{secrets.token_hex(4).upper()}"
        if not DelitCase.objects.filter(case_number=value).exists():
            return value
    raise RuntimeError("Impossible de générer un numéro de dossier unique.")


def build_deduplication_key(*, delit_type_id, scan_id=None, verbalization_id=None, alert_id=None, driver_id=None, vehicle_id=None, client_uuid=None):
    if client_uuid:
        return f"CLIENT:{client_uuid}"
    raw = '|'.join(str(v or '') for v in [delit_type_id,scan_id,verbalization_id,alert_id,driver_id,vehicle_id])
    if not any([scan_id,verbalization_id,alert_id]):
        return ''
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def create_potential_delit_case(*, detected_by, delit_type, source_type, facts, client_uuid=None, **context):
    key = build_deduplication_key(
        delit_type_id=delit_type.pk,
        scan_id=getattr(context.get('scan'),'pk',None),
        verbalization_id=getattr(context.get('verbalization'),'pk',None),
        alert_id=getattr(context.get('alert'),'pk',None),
        driver_id=getattr(context.get('driver'),'pk',None),
        vehicle_id=getattr(context.get('vehicle'),'pk',None),
        client_uuid=client_uuid,
    )
    if key:
        existing = DelitCase.objects.filter(deduplication_key=key).first()
        if existing:
            return existing, False
    with transaction.atomic():
        case = DelitCase.objects.create(
            detected_by=detected_by,
            delit_type=delit_type,
            source_type=source_type,
            facts=facts,
            client_uuid=client_uuid or secrets.token_hex(16),
            deduplication_key=key,
            **context,
        )
        DelitStatusHistory.objects.create(
            case=case,
            new_qualification_status=case.qualification_status,
            new_procedure_status=case.procedure_status,
            changed_by=detected_by,
            reason='Création manuelle du dossier potentiel.',
        )
        return case, True


def transition_case(case, *, actor, qualification_status=None, procedure_status=None, reason='', **fields):
    previous_q = case.qualification_status
    previous_p = case.procedure_status
    if qualification_status is not None:
        case.qualification_status = qualification_status
    if procedure_status is not None:
        case.procedure_status = procedure_status
    for name,value in fields.items():
        setattr(case,name,value)
    case.save()
    DelitStatusHistory.objects.create(
        case=case,
        previous_qualification_status=previous_q,
        new_qualification_status=case.qualification_status,
        previous_procedure_status=previous_p,
        new_procedure_status=case.procedure_status,
        changed_by=actor,
        reason=reason,
    )
    return case
