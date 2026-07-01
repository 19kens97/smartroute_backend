from django.conf import settings
from rest_framework import serializers

from apps.media_storage.services import MEDIA_TYPE_DOCUMENT, validate_uploaded_media
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = "__all__"
        read_only_fields = ("uploaded_by",)

    def validate_file(self, value):
        validate_uploaded_media(
            value,
            media_type=MEDIA_TYPE_DOCUMENT,
            allowed_mime_types=["application/pdf", "image/jpeg", "image/png"],
            allowed_extensions=[".pdf", ".jpg", ".jpeg", ".png"],
            max_size_mb=getattr(settings, "MAX_DOCUMENT_SIZE_MB", getattr(settings, "SECURE_UPLOAD_MAX_MB", 5)),
        )
        return value
