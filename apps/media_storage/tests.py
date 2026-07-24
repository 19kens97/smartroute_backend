from django.test import SimpleTestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from .services import MEDIA_TYPE_DOCUMENT, MEDIA_TYPE_IMAGE, scan_file_for_virus, validate_uploaded_media


class MediaValidationTests(SimpleTestCase):
    def validate_image(self, file_obj):
        return validate_uploaded_media(
            file_obj,
            media_type=MEDIA_TYPE_IMAGE,
            allowed_mime_types=["image/jpeg", "image/png"],
            allowed_extensions=[".jpg", ".jpeg", ".png"],
            max_size_mb=1,
        )

    def validate_document(self, file_obj):
        return validate_uploaded_media(
            file_obj,
            media_type=MEDIA_TYPE_DOCUMENT,
            allowed_mime_types=["application/pdf"],
            allowed_extensions=[".pdf"],
            max_size_mb=1,
        )

    def assert_invalid(self, file_obj, validator=None):
        with self.assertRaises(serializers.ValidationError):
            (validator or self.validate_image)(file_obj)

    def test_valid_jpeg_png_and_pdf_magic_bytes_are_accepted(self):
        jpeg = SimpleUploadedFile("ok.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg")
        png = SimpleUploadedFile("ok.png", b"\x89PNG\r\n\x1a\nimage", content_type="image/png")
        pdf = SimpleUploadedFile("ok.pdf", b"%PDF-1.7\nbody", content_type="application/pdf")

        self.assertEqual(self.validate_image(jpeg)["mime_type"], "image/jpeg")
        self.assertEqual(self.validate_image(png)["mime_type"], "image/png")
        self.assertEqual(self.validate_document(pdf)["mime_type"], "application/pdf")

    def test_disguised_jpeg_png_and_pdf_are_rejected(self):
        self.assert_invalid(SimpleUploadedFile("fake.jpg", b"<script>", content_type="image/jpeg"))
        self.assert_invalid(SimpleUploadedFile("fake.png", b"not-a-png", content_type="image/png"))
        self.assert_invalid(
            SimpleUploadedFile("fake.pdf", b"MZ executable", content_type="application/pdf"),
            validator=self.validate_document,
        )

    def test_misleading_content_type_is_rejected(self):
        self.assert_invalid(SimpleUploadedFile("fake.jpg", b"%PDF-1.7", content_type="image/jpeg"))

    def test_dangerous_double_extension_and_empty_file_are_rejected(self):
        self.assert_invalid(SimpleUploadedFile("proof.jpg.exe", b"\xff\xd8\xff", content_type="image/jpeg"))
        self.assert_invalid(SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg"))

    @override_settings(MAX_IMAGE_SIZE_MB=1)
    def test_oversized_file_is_rejected(self):
        oversized = SimpleUploadedFile("big.jpg", b"\xff\xd8\xff" + b"x" * (1024 * 1024 + 1), content_type="image/jpeg")
        self.assert_invalid(oversized)

    def test_antivirus_hook_is_explicitly_not_configured_yet(self):
        self.assertEqual(scan_file_for_virus(None), "NOT_CONFIGURED")
