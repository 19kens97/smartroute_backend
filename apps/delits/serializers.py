import hashlib
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from apps.media_storage.services import (
    MEDIA_TYPE_AUDIO, MEDIA_TYPE_IMAGE, MEDIA_TYPE_VIDEO,
    get_audio_limits, get_image_limits, get_video_limits, scan_file_for_virus, validate_uploaded_media,
)
from .models import DelitType, DelitCase, DelitAction, DelitEvidence, DelitStatusHistory
from .services import create_potential_delit_case


class DelitTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model=DelitType
        fields=('id','code','label','description','legal_basis','active','display_order')
        read_only_fields=fields


class DelitActionSerializer(serializers.ModelSerializer):
    class Meta:
        model=DelitAction
        fields=('id','action_type','performed_by','performed_at','location_label','authority','reference_number','description','created_at')
        read_only_fields=('performed_by','created_at')


class DelitEvidenceSerializer(serializers.ModelSerializer):
    url=serializers.SerializerMethodField()
    class Meta:
        model=DelitEvidence
        fields=('id','scan','ticket_proof','alert_evidence','file','url','evidence_type','mime_type','size_bytes','checksum_sha256','duration_seconds','caption','captured_at','created_by','created_at')
        read_only_fields=('url','mime_type','size_bytes','checksum_sha256','created_by','created_at')
        extra_kwargs={'file':{'write_only':True,'required':False}}

    @extend_schema_field(serializers.URLField())
    def get_url(self,obj):
        request=self.context.get('request')
        path=f"/api/delits/{obj.case_id}/evidence/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request else path

    def validate(self,attrs):
        sources=sum(bool(attrs.get(k)) for k in ('scan','ticket_proof','alert_evidence','file'))
        if sources != 1:
            raise serializers.ValidationError('Fournissez exactement une source de preuve.')
        file_obj=attrs.get('file')
        if file_obj:
            et=attrs.get('evidence_type')
            duration=attrs.get('duration_seconds')
            if et==DelitEvidence.EvidenceType.PHOTO:
                meta=validate_uploaded_media(file_obj,media_type=MEDIA_TYPE_IMAGE,duration_seconds=duration,field_name='file',**get_image_limits())
            elif et==DelitEvidence.EvidenceType.VIDEO:
                meta=validate_uploaded_media(file_obj,media_type=MEDIA_TYPE_VIDEO,duration_seconds=duration,field_name='file',**get_video_limits())
            elif et==DelitEvidence.EvidenceType.AUDIO:
                meta=validate_uploaded_media(file_obj,media_type=MEDIA_TYPE_AUDIO,duration_seconds=duration,field_name='file',**get_audio_limits())
            else:
                virus_scan_status=scan_file_for_virus(file_obj)
                content=file_obj.read(); file_obj.seek(0)
                meta={'mime_type':getattr(file_obj,'content_type','application/octet-stream'),'size_bytes':file_obj.size,'checksum_sha256':hashlib.sha256(content).hexdigest(),'virus_scan_status':virus_scan_status}
            attrs.update(meta)
        return attrs


class DelitHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model=DelitStatusHistory
        fields=('id','previous_qualification_status','new_qualification_status','previous_procedure_status','new_procedure_status','changed_by','changed_at','reason')
        read_only_fields=fields


class DelitCaseSerializer(serializers.ModelSerializer):
    delit_type_detail=DelitTypeSerializer(source='delit_type',read_only=True)
    detected_by_name=serializers.SerializerMethodField()
    detected_by_badge_number=serializers.SerializerMethodField()
    actions=DelitActionSerializer(many=True,read_only=True)
    evidence=DelitEvidenceSerializer(many=True,read_only=True)
    history=DelitHistorySerializer(many=True,read_only=True)

    class Meta:
        model=DelitCase
        fields=(
            'id','client_uuid','case_number','delit_type','delit_type_detail','source_type',
            'scan','ticket','verbalization','alert','infraction','driver','vehicle',
            'plate_number_snapshot','facts','detected_at','detected_by','detected_by_name','detected_by_badge_number','location_label','latitude','longitude',
            'qualification_status','procedure_status','reviewed_by','reviewed_at','review_note',
            'referred_to','external_reference','referred_at','closed_at','closed_by','closure_reason',
            'cancelled_at','cancelled_by','cancellation_reason','actions','evidence','history','created_at','updated_at'
        )
        read_only_fields=(
            'case_number','source_type','detected_by','detected_by_name','detected_by_badge_number','dcpj_status','dcpj_reference','dcpj_sent_at','dcpj_last_error','dcpj_payload_snapshot','dcpj_response_snapshot','qualification_status','procedure_status','reviewed_by','reviewed_at','review_note',
            'referred_to','external_reference','referred_at','closed_at','closed_by','closure_reason',
            'cancelled_at','cancelled_by','cancellation_reason','actions','evidence','history','created_at','updated_at'
        )

    @extend_schema_field(serializers.CharField())
    def get_detected_by_name(self,obj):
        person=getattr(obj.detected_by,'person',None)
        if person:
            return f"{person.first_name} {person.last_name}".strip()
        return getattr(obj.detected_by,'email','') or getattr(obj.detected_by,'username','')

    @extend_schema_field(serializers.CharField())
    def get_detected_by_badge_number(self,obj):
        profile=getattr(obj.detected_by,'agent_profile',None)
        return getattr(profile,'badge_number','') or ''

    def validate(self,attrs):
        verbalization=attrs.get('verbalization')
        ticket=attrs.get('ticket')
        if verbalization and ticket and verbalization.ticket_id != ticket.id:
            raise serializers.ValidationError({'verbalization':'Cette verbalisation ne correspond pas au PV.'})
        if verbalization and not ticket:
            attrs['ticket']=verbalization.ticket
        if self.instance is not None:
            allowed={'facts','location_label','latitude','longitude','driver','vehicle','plate_number_snapshot','scan','ticket','verbalization','alert','infraction'}
            forbidden=set(attrs)-allowed
            if forbidden:
                raise serializers.ValidationError({k:'Champ non modifiable directement.' for k in forbidden})
        return attrs

    def create(self,validated_data):
        request=self.context['request']
        validated_data.pop('source_type', None)
        case,created=create_potential_delit_case(detected_by=request.user,**validated_data)
        if not created:
            raise serializers.ValidationError({'non_field_errors':[f'Un dossier existe déjà : {case.case_number}.'],'existing_case_id':case.pk})
        return case


class ReasonSerializer(serializers.Serializer):
    reason=serializers.CharField(min_length=5,max_length=2000)


class ReferSerializer(serializers.Serializer):
    referred_to=serializers.CharField(min_length=2,max_length=160)
    external_reference=serializers.CharField(required=False,allow_blank=True,max_length=120)
    reason=serializers.CharField(min_length=5,max_length=2000)

