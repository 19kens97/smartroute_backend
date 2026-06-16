from pathlib import Path
from django.conf import settings
from rest_framework import serializers
from .models import Document

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = "__all__"
        read_only_fields = ("uploaded_by",)

    def validate_file(self, value):
        ext = Path(value.name).suffix.lower()
        if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise serializers.ValidationError("Unsupported file extension.")
        if value.size > settings.SECURE_UPLOAD_MAX_MB * 1024 * 1024:
            raise serializers.ValidationError("File too large.")
        return value
