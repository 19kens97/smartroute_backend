from django.contrib import admin
from .models import DelitType, DelitCase, DelitAction, DelitEvidence, DelitStatusHistory


@admin.register(DelitType)
class DelitTypeAdmin(admin.ModelAdmin):
    list_display=('code','label','active','display_order')
    list_filter=('active',)
    search_fields=('code','label','description','legal_basis')


class DelitActionInline(admin.TabularInline):
    model=DelitAction; extra=0; can_delete=False; readonly_fields=('action_type','performed_by','performed_at','location_label','authority','reference_number','description','created_at')


class DelitEvidenceInline(admin.TabularInline):
    model=DelitEvidence; extra=0; can_delete=False; readonly_fields=('evidence_type','scan','ticket_proof','alert_evidence','file','mime_type','size_bytes','checksum_sha256','caption','created_by','created_at')


class DelitHistoryInline(admin.TabularInline):
    model=DelitStatusHistory; extra=0; can_delete=False; readonly_fields=('previous_qualification_status','new_qualification_status','previous_procedure_status','new_procedure_status','changed_by','changed_at','reason')


@admin.register(DelitCase)
class DelitCaseAdmin(admin.ModelAdmin):
    inlines=(DelitActionInline,DelitEvidenceInline,DelitHistoryInline)
    list_display=('case_number','delit_type','qualification_status','procedure_status','source_type','driver','vehicle','detected_by','detected_at')
    list_filter=('qualification_status','procedure_status','source_type','delit_type','detected_at')
    search_fields=('case_number','facts','location_label','external_reference','referred_to')
    readonly_fields=('case_number','client_uuid','detected_by','detected_at','reviewed_by','reviewed_at','closed_at','closed_by','cancelled_at','cancelled_by','created_at','updated_at')
    def has_delete_permission(self,request,obj=None): return False


for model in (DelitAction,DelitEvidence,DelitStatusHistory):
    admin.site.register(model)
