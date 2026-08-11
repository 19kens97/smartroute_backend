import socket
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import serializers

from .services import MEDIA_TYPE_DOCUMENT, MEDIA_TYPE_IMAGE, _scan_with_clamav_tcp, scan_file_for_virus, validate_uploaded_media


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

    @override_settings(ANTIVIRUS_SCANNER="disabled", ANTIVIRUS_REQUIRED=False)
    def test_antivirus_can_be_disabled_in_development(self):
        self.assertEqual(scan_file_for_virus(None), "NOT_CONFIGURED")

    @override_settings(ANTIVIRUS_SCANNER="disabled", ANTIVIRUS_REQUIRED=True)
    def test_antivirus_required_fails_closed_when_not_configured(self):
        with self.assertRaises(serializers.ValidationError):
            scan_file_for_virus(None)

    @override_settings(ANTIVIRUS_SCANNER="clamav_tcp", ANTIVIRUS_REQUIRED=True)
    @patch("apps.media_storage.services._scan_with_clamav_tcp", return_value="CLEAN")
    def test_clean_antivirus_scan_is_recorded(self, _scan):
        jpeg = SimpleUploadedFile("ok.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg")

        metadata = self.validate_image(jpeg)

        self.assertEqual(metadata["virus_scan_status"], "CLEAN")

    @override_settings(ANTIVIRUS_SCANNER="clamav_tcp", ANTIVIRUS_REQUIRED=True)
    @patch("apps.media_storage.services._scan_with_clamav_tcp", return_value="INFECTED")
    def test_infected_upload_is_rejected(self, _scan):
        self.assert_invalid(SimpleUploadedFile("bad.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg"))

    @override_settings(ANTIVIRUS_SCANNER="clamav_tcp", ANTIVIRUS_REQUIRED=True)
    @patch("apps.media_storage.services._scan_with_clamav_tcp", return_value="UNAVAILABLE")
    def test_required_unavailable_scanner_rejects_upload(self, _scan):
        self.assert_invalid(SimpleUploadedFile("ok.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg"))

    @override_settings(ANTIVIRUS_SCANNER="clamav_tcp", ANTIVIRUS_REQUIRED=False)
    @patch("apps.media_storage.services._scan_with_clamav_tcp", return_value="UNAVAILABLE")
    def test_optional_unavailable_scanner_allows_upload_in_development(self, _scan):
        jpeg = SimpleUploadedFile("ok.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg")

        metadata = self.validate_image(jpeg)

        self.assertEqual(metadata["virus_scan_status"], "UNAVAILABLE")

    @override_settings(ANTIVIRUS_CLAMAV_HOST="127.0.0.1", ANTIVIRUS_CLAMAV_PORT=3310, ANTIVIRUS_TIMEOUT_SECONDS=0.01)
    @patch("apps.media_storage.services.socket.create_connection", side_effect=socket.timeout("timed out"))
    def test_clamav_timeout_is_unavailable(self, _connect):
        upload = SimpleUploadedFile("ok.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg")

        self.assertEqual(_scan_with_clamav_tcp(upload), "UNAVAILABLE")

    @override_settings(ANTIVIRUS_CLAMAV_HOST="127.0.0.1", ANTIVIRUS_CLAMAV_PORT=3310, ANTIVIRUS_TIMEOUT_SECONDS=1)
    @patch("apps.media_storage.services.socket.create_connection")
    def test_clamav_malformed_response_is_unavailable(self, connect):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.recv.return_value = b"stream: ???\n"
        connect.return_value = connection
        upload = SimpleUploadedFile("ok.jpg", b"\xff\xd8\xff\xe0image", content_type="image/jpeg")

        self.assertEqual(_scan_with_clamav_tcp(upload), "UNAVAILABLE")
