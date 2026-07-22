from django.conf import settings
from rest_framework import serializers

from apps.media_storage.services import (
    MEDIA_TYPE_DOCUMENT,
    validate_uploaded_media,
)

from .models import Document


class DocumentReadSerializer(serializers.ModelSerializer):
    vehicle_id = serializers.IntegerField(
        source="vehicle.pk",
        read_only=True,
    )
    uploaded_by_id = serializers.IntegerField(
        source="uploaded_by.pk",
        read_only=True,
        allow_null=True,
    )
    document_type_label = serializers.CharField(
        source="get_document_type_display",
        read_only=True,
    )
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "vehicle_id",
            "document_type",
            "document_type_label",
            "title",
            "description",
            "original_filename",
            "mime_type",
            "size_bytes",
            "uploaded_by_id",
            "created_at",
            "updated_at",
            "download_url",
        )
        read_only_fields = fields

    def get_download_url(self, obj):
        request = self.context.get("request")
        relative_url = f"/api/documents/{obj.pk}/download/"
        return (
            request.build_absolute_uri(relative_url)
            if request
            else relative_url
        )


class DocumentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "vehicle",
            "document_type",
            "title",
            "description",
            "file",
        )

    def validate_file(self, value):
        validate_uploaded_media(
            value,
            media_type=MEDIA_TYPE_DOCUMENT,
            allowed_mime_types=[
                "application/pdf",
                "image/jpeg",
                "image/png",
            ],
            allowed_extensions=[
                ".pdf",
                ".jpg",
                ".jpeg",
                ".png",
            ],
            max_size_mb=getattr(
                settings,
                "MAX_DOCUMENT_SIZE_MB",
                getattr(settings, "SECURE_UPLOAD_MAX_MB", 5),
            ),
        )
        return value

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Le titre du document est obligatoire."
            )
        return value

    def to_representation(self, instance):
        return DocumentReadSerializer(
            instance,
            context=self.context,
        ).data


class DocumentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "document_type",
            "title",
            "description",
        )
        extra_kwargs = {
            "document_type": {"required": False},
            "title": {"required": False},
            "description": {"required": False},
        }

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Le titre du document est obligatoire."
            )
        return value

    def to_representation(self, instance):
        return DocumentReadSerializer(
            instance,
            context=self.context,
        ).data
