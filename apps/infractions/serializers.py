from rest_framework import serializers
from .models import Infraction


class InfractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Infraction
        fields = (
            "id",
            "code",
            "number",
            "label",
            "article",
            "category",
            "amount",
            "penalty_text",
            "active",
            "display_order",
            "updated_at",
        )
        read_only_fields = fields
