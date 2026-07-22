from rest_framework import serializers

from .models import Infraction


class InfractionSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    penalty_type_label = serializers.CharField(
        source="get_penalty_type_display",
        read_only=True,
    )
    legal_classification_label = serializers.CharField(
        source="get_legal_classification_display",
        read_only=True,
    )
    penalty_summary = serializers.CharField(
        read_only=True,
    )

    class Meta:
        model = Infraction
        fields = (
            "id",
            "code",
            "number",
            "label",
            "article",
            "category",
            "category_label",
            "penalty_type",
            "penalty_type_label",
            "amount",
            "minimum_amount",
            "maximum_amount",
            "amount_options",
            "penalty_text",
            "penalty_summary",
            "currency",
            "legal_classification",
            "legal_classification_label",
            "requires_authority_review",
            "authority_review_note",
            "active",
            "display_order",
            "updated_at",
        )
        read_only_fields = fields
