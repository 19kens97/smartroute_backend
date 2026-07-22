from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel
from apps.media_storage.services import document_upload_path
from apps.vehicles.models import Vehicle


def upload_doc_path(instance, filename):
    """Compatibilité avec la migration initiale existante."""
    return document_upload_path(instance, filename)


class Document(TimeStampedModel):
    """Pièce jointe numérique associée à un véhicule."""

    class DocumentType(models.TextChoices):
        VEHICLE_PHOTO = "VEHICLE_PHOTO", "Photo du véhicule"
        REGISTRATION_COPY = "REGISTRATION_COPY", "Copie de carte grise"
        INSURANCE_COPY = "INSURANCE_COPY", "Copie d'assurance"
        INSPECTION_COPY = "INSPECTION_COPY", "Copie de contrôle technique"
        SUPPORTING_DOCUMENT = "SUPPORTING_DOCUMENT", "Pièce justificative"
        OTHER = "OTHER", "Autre"

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_vehicle_documents",
    )
    document_type = models.CharField(
        max_length=40,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
        db_index=True,
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=document_upload_path)
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        editable=False,
    )
    mime_type = models.CharField(
        max_length=120,
        blank=True,
        default="",
        editable=False,
    )
    size_bytes = models.PositiveBigIntegerField(
        default=0,
        editable=False,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["vehicle", "document_type"],
                name="doc_vehicle_type_idx",
            ),
        ]
        verbose_name = "Pièce jointe véhicule"
        verbose_name_plural = "Pièces jointes véhicule"

    def clean(self):
        super().clean()
        self.title = (self.title or "").strip()
        self.description = (self.description or "").strip()
        if not self.title:
            raise ValidationError(
                {"title": "Le titre du document est obligatoire."}
            )

    def save(self, *args, **kwargs):
        if self.file:
            uploaded_file = getattr(self.file, "file", None)
            if uploaded_file is not None:
                self.original_filename = Path(
                    getattr(uploaded_file, "name", self.file.name)
                ).name
                self.mime_type = getattr(
                    uploaded_file,
                    "content_type",
                    self.mime_type or "",
                ) or ""
                self.size_bytes = getattr(
                    uploaded_file,
                    "size",
                    self.size_bytes or 0,
                ) or 0
            elif not self.original_filename:
                self.original_filename = Path(self.file.name).name

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} — {self.vehicle}"
