"""Focused Stage 29 Backend handoff contract tests."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest


HANDOFF_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = HANDOFF_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import export_ai_contracts as exporter
import validate_handoff_package as validator


class RequiredFileTests(unittest.TestCase):
    def test_all_required_files_exist(self):
        missing = [name for name in validator.REQUIRED_FILES if not (HANDOFF_ROOT / name).is_file()]
        self.assertEqual(missing, [])

    def test_recommended_counts(self):
        self.assertEqual(len(exporter.schemas()), 9)
        self.assertEqual(len(exporter.examples()), 10)
        self.assertEqual(len(validator.REQUIRED_FILES), 28)

    def test_package_validator_passes_without_runtime_openapi(self):
        result = validator.validate_package(HANDOFF_ROOT, verify_openapi=False)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["schemaCount"], 9)
        self.assertEqual(result["exampleCount"], 10)


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            path.name: validator.strict_load(path)
            for path in (HANDOFF_ROOT / "contracts").glob("*.json")
        }

    def test_schema_dialect(self):
        for name, schema in self.schemas.items():
            with self.subTest(name=name):
                self.assertEqual(schema["$schema"], exporter.SCHEMA_URI)

    def test_schema_documents_have_explicit_additional_properties(self):
        for name, schema in self.schemas.items():
            with self.subTest(name=name):
                validator.validate_schema_document(schema, name)

    def test_session_and_answer_patterns(self):
        self.assertIsNotNone(re.fullmatch(exporter.SESSION_PATTERN, "SES_000001"))
        self.assertIsNotNone(re.fullmatch(exporter.ANSWER_PATTERN, "ANS_000004"))
        self.assertIsNone(re.fullmatch(exporter.SESSION_PATTERN, "SESSION1"))

    def test_vision_status_enum(self):
        values = self.schemas["vision-job-response.schema.json"]["properties"]["status"]["enum"]
        self.assertEqual(values, exporter.VISION_STATUSES)

    def test_analysis_status_enum(self):
        values = self.schemas["analysis-job-response.schema.json"]["properties"]["status"]["enum"]
        self.assertEqual(values, exporter.ANALYSIS_STATUSES)

    def test_force_rebuild_is_boolean(self):
        for name in ("vision-job-request.schema.json", "analysis-job-request.schema.json"):
            self.assertEqual(self.schemas[name]["properties"]["forceRebuild"]["type"], "boolean")

    def test_vision_scores_only_allow_null(self):
        self.assertEqual(
            self.schemas["vision-feedback.schema.json"]["properties"]["scores"]["type"],
            "null",
        )

    def test_integrated_scoring_is_const_false(self):
        scoring = self.schemas["integrated-session.schema.json"]["properties"]["scoringAvailable"]
        self.assertIs(scoring["const"], False)

    def test_transcript_text_is_nullable(self):
        answer = self.schemas["transcription-response.schema.json"]["properties"]["answers"]["items"]
        self.assertEqual(answer["properties"]["text"]["anyOf"][1], {"type": "null"})

    def test_generated_schemas_match_committed_files(self):
        for name, expected in exporter.schemas().items():
            with self.subTest(name=name):
                self.assertEqual(self.schemas[name], expected)


class ExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = {
            path.name: validator.strict_load(path)
            for path in (HANDOFF_ROOT / "examples").glob("*.json")
        }
        cls.schemas = {
            path.name: validator.strict_load(path)
            for path in (HANDOFF_ROOT / "contracts").glob("*.json")
        }

    def test_all_examples_match_deterministic_export(self):
        self.assertEqual(self.examples, exporter.examples())

    def test_schema_mapped_examples_validate(self):
        for example_name, schema_name in validator.EXAMPLE_SCHEMA.items():
            with self.subTest(example=example_name):
                validator.validate_instance(self.examples[example_name], self.schemas[schema_name])

    def test_job_requests_do_not_force_rebuild(self):
        self.assertIs(self.examples["vision-job-request.json"]["forceRebuild"], False)
        self.assertIs(self.examples["analysis-job-request.json"]["forceRebuild"], False)

    def test_redacted_transcription_has_no_text(self):
        payload = self.examples["transcription-response-redacted.json"]
        answer = payload["answers"][0]
        self.assertIsNone(answer["text"])
        self.assertTrue(all(item["text"] is None for item in answer["segments"]))
        self.assertTrue(all(item["text"] is None for item in answer["words"]))
        self.assertIs(answer["textExposed"], False)

    def test_integrated_example_has_expected_counts(self):
        payload = self.examples["integrated-session-response.json"]
        self.assertEqual(len(payload["answers"]), 4)
        self.assertEqual(payload["components"]["transcription"]["segmentCount"], 27)
        self.assertEqual(payload["components"]["transcription"]["wordCount"], 307)
        self.assertEqual(payload["components"]["speechCharacteristics"]["fillerCandidateCount"], 1)
        self.assertEqual(payload["components"]["speechCharacteristics"]["pitchAvailableAnswerCount"], 4)

    def test_integrated_example_status_and_scoring(self):
        payload = self.examples["integrated-session-response.json"]
        self.assertEqual(payload["status"], "INTEGRATED_READY_WITH_WARNINGS")
        self.assertIs(payload["scoringAvailable"], False)

    def test_official_intervals(self):
        answers = self.examples["integrated-session-response.json"]["answers"]
        intervals = [(row["interval"]["startMs"], row["interval"]["endMs"]) for row in answers]
        self.assertEqual(intervals, [(11000, 50000), (51000, 107000), (108000, 160000), (161000, 192000)])

    def test_common_error_and_warning(self):
        validator.validate_error_example(self.examples["common-error-response.json"])
        validator.validate_instance(self.examples["common-warning.json"], exporter._warning())

    def test_examples_pass_privacy_scan(self):
        for name, payload in self.examples.items():
            with self.subTest(name=name):
                validator.validate_privacy(payload)

    def test_examples_are_strict_json(self):
        for path in (HANDOFF_ROOT / "examples").glob("*.json"):
            with self.subTest(path=path.name):
                validator.strict_load(path)


class ValidatorFailureTests(unittest.TestCase):
    def test_rejects_nan_and_infinity(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(validator.HandoffValidationError):
                validator.validate_instance(value, {"type": "number"})

    def test_rejects_extra_property(self):
        with self.assertRaises(validator.HandoffValidationError):
            validator.validate_instance(
                {"value": 1, "extra": 2},
                {"type": "object", "additionalProperties": False, "required": ["value"], "properties": {"value": {"type": "integer"}}},
            )

    def test_rejects_participant_reference(self):
        with self.assertRaises(validator.HandoffValidationError):
            validator.validate_privacy({"message": "PTC_999999"})

    def test_rejects_internal_path(self):
        with self.assertRaises(validator.HandoffValidationError):
            validator.validate_privacy({"message": "C:\\internal\\result.json"})

    def test_rejects_transcript_text(self):
        with self.assertRaises(validator.HandoffValidationError):
            validator.validate_privacy({"text": "synthetic transcript body"})

    def test_rejects_score_field(self):
        with self.assertRaises(validator.HandoffValidationError):
            validator.validate_privacy({"score": 10})

    def test_rejects_missing_required_file(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "handoff"
            shutil.copytree(HANDOFF_ROOT, copy)
            (copy / "README.md").unlink()
            with self.assertRaises(validator.HandoffValidationError):
                validator.validate_package(copy, verify_openapi=False)

    def test_rejects_openapi_missing_path(self):
        vision = {"paths": {}, "components": {"schemas": {"JobStatus": {"enum": exporter.VISION_STATUSES}}}}
        analysis = {"paths": {path: {} for path in exporter.ANALYSIS_PATHS}, "components": {"schemas": {"JobStatus": {"enum": exporter.ANALYSIS_STATUSES}}}}
        with self.assertRaises(RuntimeError):
            exporter.validate_openapi(vision, analysis)

    def test_rejects_openapi_status_drift(self):
        vision = {"paths": {path: {} for path in exporter.VISION_PATHS}, "components": {"schemas": {"JobStatus": {"enum": ["FAILED"]}}}}
        analysis = {"paths": {path: {} for path in exporter.ANALYSIS_PATHS}, "components": {"schemas": {"JobStatus": {"enum": exporter.ANALYSIS_STATUSES}}}}
        with self.assertRaises(RuntimeError):
            exporter.validate_openapi(vision, analysis)


class DocumentationTests(unittest.TestCase):
    def test_endpoint_documentation_is_complete(self):
        text = (HANDOFF_ROOT / "README.md").read_text(encoding="utf-8") + (HANDOFF_ROOT / "docs" / "backend-integration-guide.md").read_text(encoding="utf-8")
        for path in exporter.VISION_PATHS | exporter.ANALYSIS_PATHS:
            self.assertIn(path, text)

    def test_error_and_warning_reference_is_complete(self):
        reference = (HANDOFF_ROOT / "docs" / "error-warning-reference.md").read_text(encoding="utf-8")
        for code in validator.VISION_ERROR_CODES | validator.ANALYSIS_ERROR_CODES | validator.INTEGRATION_ERROR_CODES | validator.WARNING_CODES:
            self.assertIn(code, reference)

    def test_polling_is_bounded(self):
        text = (HANDOFF_ROOT / "docs" / "polling-and-retry-policy.md").read_text(encoding="utf-8")
        self.assertIn("무한 polling", text)
        self.assertIn("bounded", text)

    def test_gpu_limitation_is_not_hidden(self):
        text = (HANDOFF_ROOT / "docs" / "ai-development-completion-report.md").read_text(encoding="utf-8")
        self.assertIn("GPU Docker 실제 forceRebuild 전사 미검증", text)

    def test_backend_and_frontend_code_are_out_of_scope(self):
        text = (HANDOFF_ROOT / "docs" / "ai-development-completion-report.md").read_text(encoding="utf-8")
        self.assertIn("Backend Java, Frontend, DB", text)

    def test_export_cli_has_no_media_or_identity_options(self):
        options = {option for action in exporter.parser()._actions for option in action.option_strings}
        for forbidden in ("--video-path", "--audio-path", "--participant-id", "--transcript-path"):
            self.assertNotIn(forbidden, options)


if __name__ == "__main__":
    unittest.main()
