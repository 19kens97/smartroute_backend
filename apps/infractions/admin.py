from django.contrib import admin
from django.db import transaction

from .models import Infraction
from .services import (
    invalidate_infraction_catalog_cache,
)


@admin.register(Infraction)
class InfractionAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "code",
        "label",
        "category",
        "penalty_type",
        "penalty_summary",
        "legal_classification",
        "requires_authority_review",
        "active",
    )
    list_filter = (
        "active",
        "category",
        "penalty_type",
        "legal_classification",
        "requires_authority_review",
    )
    search_fields = (
        "code",
        "label",
        "official_label",
        "article",
        "penalty_text",
        "authority_review_note",
    )
    ordering = (
        "display_order",
        "code",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "penalty_summary",
    )
    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "number",
                    "code",
                    "official_label",
                    "label",
                    "article",
                    "category",
                    "display_order",
                    "active",
                )
            },
        ),
        (
            "Sanction",
            {
                "fields": (
                    "penalty_type",
                    "amount",
                    "minimum_amount",
                    "maximum_amount",
                    "amount_options",
                    "penalty_text",
                    "currency",
                    "penalty_summary",
                )
            },
        ),
        (
            "Qualification et orientation",
            {
                "fields": (
                    "legal_classification",
                    "requires_authority_review",
                    "authority_review_note",
                )
            },
        ),
        (
            "Métadonnées",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        super().save_model(
            request,
            obj,
            form,
            change,
        )
        transaction.on_commit(
            invalidate_infraction_catalog_cache
        )
