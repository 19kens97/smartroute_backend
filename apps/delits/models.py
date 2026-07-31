import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from apps.core.models import TimeStampedModel


@deconstructible
class PrivateDelitEvidenceStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_DELIT_EVIDENCE_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_delit_evidence_storage = PrivateDelitEvidenceStorage()


def delit_evidence_upload_path(instance, filename):
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f"delits/{instance.case.case_number}/{uuid.uuid4().hex}.{extension}"


class DelitType(TimeStampedModel):
    code = models.CharField(max_length=60, unique=True, db_index=True)
    label = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    legal_basis = models.CharField(max_length=255, blank=True, default="")
    active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ('display_order', 'code')

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        self.label = (self.label or '').strip()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.label}"


class DelitCase(TimeStampedModel):
    class SourceType(models.TextChoices):
        MANUAL_OBSERVATION = 'MANUAL_OBSERVATION', 'Observation directe'
        PLATE_SCAN = 'PLATE_SCAN', 'Scan ou recherche de plaque'
        DRIVER_SEARCH = 'DRIVER_SEARCH', 'Recherche conducteur'
        LICENSE_SEARCH = 'LICENSE_SEARCH', 'Recherche permis'
        VEHICLE_CONTROL = 'VEHICLE_CONTROL', 'Contrôle véhicule'
        TICKET = 'TICKET', 'Procès-verbal'
        VERBALIZATION = 'VERBALIZATION', 'Verbalisation'
        ALERT = 'ALERT', 'Alerte'

    class QualificationStatus(models.TextChoices):
        POTENTIAL = 'POTENTIAL', 'Potentiel'
        UNDER_REVIEW = 'UNDER_REVIEW', 'En révision'
        CONFIRMED = 'CONFIRMED', 'Confirmé'
        REJECTED = 'REJECTED', 'Rejeté'

    class ProcedureStatus(models.TextChoices):
        OPEN = 'OPEN', 'Ouvert'
        ACTION_TAKEN = 'ACTION_TAKEN', 'Mesure prise'
        REFERRED = 'REFERRED', 'Transmis'
        CLOSED = 'CLOSED', 'Clôturé'
        CANCELLED = 'CANCELLED', 'Annulé'

    class DCPJStatus(models.TextChoices):
        NOT_SENT = 'NOT_SENT', 'Non transmis'
        SENT = 'SENT', 'Transmis'
        ACKNOWLEDGED = 'ACKNOWLEDGED', 'Accuse reception'
        FAILED = 'FAILED', 'Echec transmission'

    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    case_number = models.CharField(max_length=24, unique=True, db_index=True, editable=False)
    delit_type = models.ForeignKey(DelitType, on_delete=models.PROTECT, related_name='cases')
    source_type = models.CharField(max_length=30, choices=SourceType.choices, db_index=True)
    scan = models.ForeignKey('scans.Scan', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    ticket = models.ForeignKey('tickets.Ticket', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    verbalization = models.ForeignKey('tickets.TicketVerbalization', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    alert = models.ForeignKey('alerts.Alert', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    infraction = models.ForeignKey('infractions.Infraction', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    driver = models.ForeignKey('drivers.Driver', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    vehicle = models.ForeignKey('vehicles.Vehicle', on_delete=models.PROTECT, null=True, blank=True, related_name='delit_cases')
    plate_number_snapshot = models.CharField(max_length=20, blank=True, default='', db_index=True)
    facts = models.TextField()
    detected_at = models.DateTimeField(default=timezone.now, db_index=True)
    detected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='detected_delit_cases')
    location_label = models.CharField(max_length=255, blank=True, default='')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    qualification_status = models.CharField(max_length=20, choices=QualificationStatus.choices, default=QualificationStatus.POTENTIAL, db_index=True)
    procedure_status = models.CharField(max_length=20, choices=ProcedureStatus.choices, default=ProcedureStatus.OPEN, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reviewed_delit_cases')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True, default='')
    referred_to = models.CharField(max_length=160, blank=True, default='')
    external_reference = models.CharField(max_length=120, blank=True, default='')
    referred_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='closed_delit_cases')
    closure_reason = models.TextField(blank=True, default='')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='cancelled_delit_cases')
    cancellation_reason = models.TextField(blank=True, default='')
    deduplication_key = models.CharField(max_length=255, blank=True, default='', db_index=True)
    dcpj_status = models.CharField(max_length=20, choices=DCPJStatus.choices, default=DCPJStatus.NOT_SENT, db_index=True)
    dcpj_reference = models.CharField(max_length=80, blank=True, default='', db_index=True)
    dcpj_sent_at = models.DateTimeField(null=True, blank=True)
    dcpj_last_error = models.TextField(blank=True, default='')
    dcpj_payload_snapshot = models.JSONField(default=dict, blank=True)
    dcpj_response_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-detected_at', '-id')
        indexes = [
            models.Index(fields=['qualification_status','procedure_status','detected_at'], name='delit_case_status_idx'),
            models.Index(fields=['driver','procedure_status'], name='delit_driver_status_idx'),
            models.Index(fields=['vehicle','procedure_status'], name='delit_vehicle_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['deduplication_key'], condition=~models.Q(deduplication_key=''), name='unique_delit_dedup_key'),
        ]

    def clean(self):
        super().clean()
        self.facts = (self.facts or '').strip()
        self.location_label = (self.location_label or '').strip()
        self.review_note = (self.review_note or '').strip()
        self.referred_to = (self.referred_to or '').strip()
        self.external_reference = (self.external_reference or '').strip()
        self.plate_number_snapshot = (self.plate_number_snapshot or '').strip().upper()
        self.closure_reason = (self.closure_reason or '').strip()
        self.cancellation_reason = (self.cancellation_reason or '').strip()
        self.dcpj_reference = (self.dcpj_reference or '').strip()
        self.dcpj_last_error = (self.dcpj_last_error or '').strip()
        if len(self.facts) < 10:
            raise ValidationError({'facts':'Les faits doivent contenir au moins 10 caractères.'})
        if self.verbalization_id and self.ticket_id and self.verbalization.ticket_id != self.ticket_id:
            raise ValidationError({'verbalization':'La verbalisation ne correspond pas au PV sélectionné.'})
        if not any([self.scan_id,self.ticket_id,self.verbalization_id,self.alert_id,self.driver_id,self.vehicle_id,self.plate_number_snapshot]):
            raise ValidationError('Au moins une source ou une entité métier doit être liée au dossier.')
        if self.qualification_status in {self.QualificationStatus.CONFIRMED,self.QualificationStatus.REJECTED}:
            if not self.reviewed_by_id or not self.reviewed_at or len(self.review_note) < 5:
                raise ValidationError({'review_note':'Une décision doit être datée, attribuée et motivée.'})
        if self.procedure_status == self.ProcedureStatus.REFERRED:
            if not self.referred_to or not self.referred_at:
                raise ValidationError({'referred_to':'La destination et la date de transmission sont obligatoires.'})
        if self.procedure_status == self.ProcedureStatus.CLOSED:
            if not self.closed_by_id or not self.closed_at or len(self.closure_reason) < 5:
                raise ValidationError({'closure_reason':'La clôture doit être attribuée, datée et motivée.'})
        if self.procedure_status == self.ProcedureStatus.CANCELLED:
            if not self.cancelled_by_id or not self.cancelled_at or len(self.cancellation_reason) < 5:
                raise ValidationError({'cancellation_reason':'L’annulation doit être attribuée, datée et motivée.'})

    def save(self,*args,**kwargs):
        if not self.case_number:
            from .services import generate_case_number
            self.case_number = generate_case_number()
        self.full_clean()
        super().save(*args,**kwargs)

    def __str__(self):
        return self.case_number


class DelitAction(TimeStampedModel):
    class ActionType(models.TextChoices):
        IDENTITY_CHECK = 'IDENTITY_CHECK', 'Contrôle d’identité'
        LICENSE_RETAINED = 'LICENSE_RETAINED', 'Permis retenu'
        DOCUMENT_SEIZED = 'DOCUMENT_SEIZED', 'Document saisi'
        VEHICLE_IMMOBILIZED = 'VEHICLE_IMMOBILIZED', 'Véhicule immobilisé'
        VEHICLE_TOWED = 'VEHICLE_TOWED', 'Véhicule remorqué'
        PERSON_INTERCEPTED = 'PERSON_INTERCEPTED', 'Personne interceptée'
        PERSON_ARRESTED = 'PERSON_ARRESTED', 'Personne arrêtée'
        REFERRED_TO_AUTHORITY = 'REFERRED_TO_AUTHORITY', 'Transmis à une autorité'
        DOCUMENT_RETURNED = 'DOCUMENT_RETURNED', 'Document restitué'
        VEHICLE_RELEASED = 'VEHICLE_RELEASED', 'Véhicule libéré'
        PERSON_RELEASED = 'PERSON_RELEASED', 'Personne libérée'
        OTHER = 'OTHER', 'Autre'

    case = models.ForeignKey(DelitCase,on_delete=models.CASCADE,related_name='actions')
    action_type = models.CharField(max_length=32,choices=ActionType.choices,db_index=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='delit_actions')
    performed_at = models.DateTimeField(default=timezone.now,db_index=True)
    location_label = models.CharField(max_length=255,blank=True,default='')
    authority = models.CharField(max_length=160,blank=True,default='')
    reference_number = models.CharField(max_length=120,blank=True,default='')
    description = models.TextField()

    class Meta: ordering=('performed_at','id')

    def save(self,*args,**kwargs):
        self.description=(self.description or '').strip()
        self.full_clean(); super().save(*args,**kwargs)


class DelitEvidence(TimeStampedModel):
    class EvidenceType(models.TextChoices):
        PHOTO='PHOTO','Photo'; VIDEO='VIDEO','Vidéo'; AUDIO='AUDIO','Audio'; DOCUMENT='DOCUMENT','Document'; STATEMENT='STATEMENT','Déclaration'; OTHER='OTHER','Autre'

    case = models.ForeignKey(DelitCase,on_delete=models.CASCADE,related_name='evidence')
    scan = models.ForeignKey('scans.Scan',on_delete=models.PROTECT,null=True,blank=True,related_name='delit_evidence')
    ticket_proof = models.ForeignKey('tickets.TicketProof',on_delete=models.PROTECT,null=True,blank=True,related_name='delit_evidence')
    alert_evidence = models.ForeignKey('alerts.AlertEvidence',on_delete=models.PROTECT,null=True,blank=True,related_name='delit_evidence')
    file = models.FileField(upload_to=delit_evidence_upload_path,storage=private_delit_evidence_storage,null=True,blank=True)
    evidence_type = models.CharField(max_length=12,choices=EvidenceType.choices)
    mime_type = models.CharField(max_length=120,blank=True,default='')
    size_bytes = models.PositiveBigIntegerField(null=True,blank=True)
    checksum_sha256 = models.CharField(max_length=64,blank=True,default='')
    duration_seconds = models.PositiveIntegerField(null=True,blank=True)
    caption = models.CharField(max_length=255,blank=True,default='')
    captured_at = models.DateTimeField(null=True,blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='delit_evidence')

    class Meta: ordering=('created_at','id')

    def clean(self):
        super().clean()
        sources=sum(bool(x) for x in [self.scan_id,self.ticket_proof_id,self.alert_evidence_id,self.file])
        if sources != 1:
            raise ValidationError('Une preuve doit avoir exactement une source : scan, preuve de PV, preuve d’alerte ou fichier.')

    def save(self,*args,**kwargs):
        self.full_clean(); super().save(*args,**kwargs)


class DelitStatusHistory(models.Model):
    case=models.ForeignKey(DelitCase,on_delete=models.CASCADE,related_name='history')
    previous_qualification_status=models.CharField(max_length=20,blank=True,default='')
    new_qualification_status=models.CharField(max_length=20)
    previous_procedure_status=models.CharField(max_length=20,blank=True,default='')
    new_procedure_status=models.CharField(max_length=20)
    changed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='delit_status_changes')
    changed_at=models.DateTimeField(default=timezone.now,db_index=True)
    reason=models.TextField(blank=True,default='')
    class Meta: ordering=('changed_at','id')

