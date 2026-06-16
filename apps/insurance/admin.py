from django.contrib import admin

from .models import InsurancePolicy


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ("policy_number", "vehicle", "insurer", "valid_until", "status")
    search_fields = ("policy_number", "insurer", "vehicle__plate_number")
    list_filter = ("status", "valid_until")

