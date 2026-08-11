from django.test import SimpleTestCase

from apps.core.security import sanitize_mapping


class SecurityRedactionTests(SimpleTestCase):
    def test_sanitize_mapping_redacts_documents_proofs_and_tokens(self):
        sanitized = sanitize_mapping(
            {
                "access_token": "jwt-value",
                "authorization": "Bearer jwt-value",
                "document": "private.pdf",
                "proof_file": "photo.jpg",
                "signature_payload": "points",
                "dossier_number": "D-123456",
                "nested": {"refresh": "refresh-token", "plate_number": "AA12345"},
            }
        )

        self.assertEqual(sanitized["access_token"], "<redacted>")
        self.assertEqual(sanitized["authorization"], "<redacted>")
        self.assertEqual(sanitized["document"], "<redacted>")
        self.assertEqual(sanitized["proof_file"], "<redacted>")
        self.assertEqual(sanitized["signature_payload"], "<redacted>")
        self.assertEqual(sanitized["dossier_number"], "<masked>")
        self.assertEqual(sanitized["nested"]["refresh"], "<redacted>")
        self.assertEqual(sanitized["nested"]["plate_number"], "AA***45")
