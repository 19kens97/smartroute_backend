import tempfile
from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import TestCase


class OpenApiSchemaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as schema_file:
            cls.schema_path = Path(schema_file.name)
        call_command("spectacular", file=str(cls.schema_path), validate=True, verbosity=0)
        cls.schema = yaml.safe_load(cls.schema_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.schema_path.unlink(missing_ok=True)
        finally:
            super().tearDownClass()

    def _path_parameters(self, path, method="get"):
        return {
            parameter["name"]: parameter
            for parameter in self.schema["paths"][path][method]["parameters"]
            if parameter["in"] == "path"
        }

    def test_custom_path_parameters_are_integer_typed(self):
        cases = {
            "/api/alerts/{id}/evidence/{evidence_pk}/": ["evidence_pk"],
            "/api/delits/{id}/evidence/{evidence_id}/download/": ["evidence_id"],
            "/api/tickets/{id}/verbalizations/{verbalization_id}/proofs/": ["verbalization_id"],
            "/api/tickets/{id}/verbalizations/{verbalization_id}/proofs/{proof_id}/download/": ["verbalization_id", "proof_id"],
        }

        for path, names in cases.items():
            params = self._path_parameters(path, "post" if path.endswith("proofs/") else "get")
            for name in names:
                self.assertEqual(params[name]["schema"]["type"], "integer")

    def test_binary_responses_are_documented_for_downloads(self):
        for path in [
            "/api/alerts/{id}/evidence/{evidence_pk}/",
            "/api/delits/{id}/evidence/{evidence_id}/download/",
            "/api/scans/history/{id}/image/",
            "/api/tickets/{id}/verbalizations/{verbalization_id}/proofs/{proof_id}/download/",
        ]:
            content = self.schema["paths"][path]["get"]["responses"]["200"]["content"]
            media_schema = next(iter(content.values()))["schema"]
            self.assertEqual(media_schema["format"], "binary")

    def test_api_view_endpoints_have_documented_success_responses(self):
        cases = [
            ("/api/auth/mobile/login/", "post"),
            ("/api/auth/change-password/", "post"),
            ("/api/dashboard/summary/", "get"),
            ("/api/sync/push/", "post"),
        ]

        for path, method in cases:
            responses = self.schema["paths"][path][method]["responses"]
            self.assertIn("200", responses)
            self.assertIn("content", responses["200"])

    def test_enum_overrides_use_stable_domain_names(self):
        schemas = self.schema["components"]["schemas"]
        for enum_name in [
            "AlertCategoryEnum",
            "InfractionCategoryEnum",
            "AlertStatusEnum",
            "TicketStatusEnum",
            "TicketVerbalizationStatusEnum",
            "InsurancePolicyStatusEnum",
            "AlertEvidenceTypeEnum",
            "TicketProofEvidenceTypeEnum",
            "DelitEvidenceTypeEnum",
            "SyncEntityTypeEnum",
        ]:
            self.assertIn(enum_name, schemas)