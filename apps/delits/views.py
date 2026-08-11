from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from apps.core.services import log_action
from apps.core.openapi import BinaryReferenceSerializer, DetailErrorSerializer
from .models import DelitType, DelitCase, DelitAction, DelitEvidence
from .pagination import DelitPagination
from .permissions import DelitPermission
from .serializers import (
    DelitTypeSerializer, DelitCaseSerializer, DelitActionSerializer,
    DelitEvidenceSerializer, ReasonSerializer, ReferSerializer,
)
from .dcpj import send_case_to_dcpj_demo
from .services import transition_case


class DelitTypeViewSet(ReadOnlyModelViewSet):
    serializer_class=DelitTypeSerializer
    permission_classes=[DelitPermission]
    pagination_class=None
    http_method_names=['get','head','options']
    def get_queryset(self):
        return DelitType.objects.filter(active=True).order_by('display_order','code')


class DelitCaseViewSet(ModelViewSet):
    serializer_class=DelitCaseSerializer
    permission_classes=[DelitPermission]
    parser_classes=[JSONParser,MultiPartParser,FormParser]
    pagination_class=DelitPagination
    http_method_names=['get','post','patch','head','options']
    filterset_fields=('delit_type','source_type','qualification_status','procedure_status','scan','ticket','verbalization','alert','driver','vehicle','detected_by')
    search_fields=('case_number','facts','location_label','external_reference','referred_to')

    def get_queryset(self):
        return DelitCase.objects.select_related(
            'delit_type','scan','ticket','verbalization','alert','infraction','driver','vehicle',
            'detected_by','detected_by__person','reviewed_by','closed_by','cancelled_by'
        ).prefetch_related('actions','evidence','history').order_by('-detected_at','-id')

    def perform_create(self,serializer):
        case=serializer.save()
        log_action(self.request.user,case,'CREATE',{'source_type':case.source_type,'qualification_status':case.qualification_status})

    def perform_update(self,serializer):
        case=serializer.save()
        log_action(self.request.user,case,'UPDATE')

    @action(detail=True,methods=['post'],url_path='submit-review')
    def submit_review(self,request,pk=None):
        case=self.get_object()
        s=ReasonSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.qualification_status != DelitCase.QualificationStatus.POTENTIAL:
            return Response({'detail':'Le dossier ne peut plus être soumis.'},status=409)
        transition_case(case,actor=request.user,qualification_status=DelitCase.QualificationStatus.UNDER_REVIEW,reason=s.validated_data['reason'])
        return Response(self.get_serializer(case).data)

    @action(detail=True,methods=['post'])
    def confirm(self,request,pk=None):
        case=self.get_object(); s=ReasonSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.qualification_status not in {DelitCase.QualificationStatus.POTENTIAL,DelitCase.QualificationStatus.UNDER_REVIEW}:
            return Response({'detail':'Transition impossible.'},status=409)
        transition_case(case,actor=request.user,qualification_status=DelitCase.QualificationStatus.CONFIRMED,reason=s.validated_data['reason'],reviewed_by=request.user,reviewed_at=timezone.now(),review_note=s.validated_data['reason'])
        return Response(self.get_serializer(case).data)

    @action(detail=True,methods=['post'])
    def reject(self,request,pk=None):
        case=self.get_object(); s=ReasonSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.qualification_status not in {DelitCase.QualificationStatus.POTENTIAL,DelitCase.QualificationStatus.UNDER_REVIEW}:
            return Response({'detail':'Transition impossible.'},status=409)
        transition_case(case,actor=request.user,qualification_status=DelitCase.QualificationStatus.REJECTED,procedure_status=DelitCase.ProcedureStatus.CLOSED,reason=s.validated_data['reason'],reviewed_by=request.user,reviewed_at=timezone.now(),review_note=s.validated_data['reason'],closed_by=request.user,closed_at=timezone.now(),closure_reason=s.validated_data['reason'])
        return Response(self.get_serializer(case).data)

    @action(detail=True,methods=['post'],url_path='actions')
    def add_action(self,request,pk=None):
        case=self.get_object()
        if case.procedure_status in {DelitCase.ProcedureStatus.CLOSED,DelitCase.ProcedureStatus.CANCELLED}:
            return Response({'detail':'Le dossier est fermé.'},status=409)
        s=DelitActionSerializer(data=request.data,context={'request':request}); s.is_valid(raise_exception=True)
        item=s.save(case=case,performed_by=request.user)
        if case.procedure_status == DelitCase.ProcedureStatus.OPEN:
            transition_case(case,actor=request.user,procedure_status=DelitCase.ProcedureStatus.ACTION_TAKEN,reason=f'Action enregistrée : {item.action_type}.')
        log_action(request.user,case,'ADD_ACTION',{'action_id':item.pk,'action_type':item.action_type})
        return Response(DelitActionSerializer(item).data,status=201)

    @action(detail=True,methods=['post'],url_path='evidence')
    def add_evidence(self,request,pk=None):
        case=self.get_object()
        if case.procedure_status in {DelitCase.ProcedureStatus.CLOSED,DelitCase.ProcedureStatus.CANCELLED}:
            return Response({'detail':'Le dossier est fermé.'},status=409)
        s=DelitEvidenceSerializer(data=request.data,context={'request':request}); s.is_valid(raise_exception=True)
        item=s.save(case=case,created_by=request.user)
        log_action(request.user,case,'ADD_EVIDENCE',{'evidence_id':item.pk,'evidence_type':item.evidence_type})
        return Response(DelitEvidenceSerializer(item,context={'request':request}).data,status=201)

    @extend_schema(parameters=[OpenApiParameter("evidence_id", OpenApiTypes.INT, OpenApiParameter.PATH)], responses={200: OpenApiResponse(response=OpenApiTypes.BINARY, description="Fichier de preuve ou reference JSON"), 409: DetailErrorSerializer})
    @action(detail=True,methods=['get'],url_path=r'evidence/(?P<evidence_id>[^/.]+)/download')
    def evidence_download(self,request,pk=None,evidence_id=None):
        case=self.get_object(); item=case.evidence.filter(pk=evidence_id).first()
        if item is None:
            raise Http404
        if item.file:
            try: item.file.open('rb')
            except (FileNotFoundError,OSError): raise Http404
            response=FileResponse(item.file,content_type=item.mime_type or 'application/octet-stream')
            response['Cache-Control']='private, no-store'
            return response
        return Response({'detail':'Cette preuve référence une ressource existante.','scan':item.scan_id,'ticket_proof':item.ticket_proof_id,'alert_evidence':item.alert_evidence_id})

    @action(detail=True,methods=['post'])
    def refer(self,request,pk=None):
        case=self.get_object(); s=ReferSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.qualification_status != DelitCase.QualificationStatus.CONFIRMED:
            return Response({'detail':'Seul un délit confirmé peut être transmis.'},status=409)
        transition_case(case,actor=request.user,procedure_status=DelitCase.ProcedureStatus.REFERRED,reason=s.validated_data['reason'],referred_to=s.validated_data['referred_to'],external_reference=s.validated_data.get('external_reference',''),referred_at=timezone.now())
        return Response(self.get_serializer(case).data)

    @action(detail=True,methods=['post'])
    def close(self,request,pk=None):
        case=self.get_object(); s=ReasonSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.procedure_status in {DelitCase.ProcedureStatus.CLOSED,DelitCase.ProcedureStatus.CANCELLED}:
            return Response({'detail':'Le dossier est déjà fermé.'},status=409)
        transition_case(case,actor=request.user,procedure_status=DelitCase.ProcedureStatus.CLOSED,reason=s.validated_data['reason'],closed_by=request.user,closed_at=timezone.now(),closure_reason=s.validated_data['reason'])
        return Response(self.get_serializer(case).data)

    @action(detail=True,methods=['post'])
    def cancel(self,request,pk=None):
        case=self.get_object(); s=ReasonSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.procedure_status in {DelitCase.ProcedureStatus.CLOSED,DelitCase.ProcedureStatus.CANCELLED}:
            return Response({'detail':'Le dossier est déjà fermé.'},status=409)
        transition_case(case,actor=request.user,procedure_status=DelitCase.ProcedureStatus.CANCELLED,reason=s.validated_data['reason'],cancelled_by=request.user,cancelled_at=timezone.now(),cancellation_reason=s.validated_data['reason'])
        return Response(self.get_serializer(case).data)
