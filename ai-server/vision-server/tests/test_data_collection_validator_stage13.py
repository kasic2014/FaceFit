from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.vision.data_collection_validator import (
    DEFAULT_FIXTURE_DIRECTORY,
    DataCollectionAnnotationContractValidator,
    DataCollectionFixtureRegistry,
    DataCollectionValidationError,
    dumps_strict,
    load_strict_json,
    load_strict_jsonl,
    validate_no_forbidden_output_fields,
)


class DataCollectionValidatorStage13Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_fixture_registry_counts_and_references(self):
        registry = DataCollectionFixtureRegistry(DEFAULT_FIXTURE_DIRECTORY)
        leakage = registry.validate()
        self.assertEqual(len(registry.participants), 6)
        self.assertEqual(len(registry.raters), 3)
        self.assertEqual(len(registry.recording_sessions), 6)
        self.assertEqual(len(registry.answers), 12)
        self.assertEqual(len(registry.annotation_registry.labels), 19)
        self.assertFalse(leakage["leakage_detected"])

    def test_smoke_creates_exact_required_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage13"
            report = DataCollectionAnnotationContractValidator().validate(
                output_root=destination
            )
            self.assertEqual(
                report["technical_judgment"],
                "data_collection_annotation_contract_smoke_completed_with_metadata_fixtures",
            )
            self.assertEqual(
                {path.name for path in destination.iterdir()},
                set(DataCollectionAnnotationContractValidator.OUTPUT_NAMES),
            )
            self.assertEqual(len(report["output_sha256"]), 9)

    def test_smoke_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            validator = DataCollectionAnnotationContractValidator()
            first_report = validator.validate(output_root=first)
            second_report = validator.validate(output_root=second)
            self.assertEqual(
                first_report["output_sha256"],
                second_report["output_sha256"],
            )

    def test_existing_output_requires_explicit_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage13"
            validator = DataCollectionAnnotationContractValidator()
            validator.validate(output_root=destination)
            with self.assertRaises(DataCollectionValidationError) as context:
                validator.validate(output_root=destination)
            self.assertEqual(context.exception.code, "OUTPUT_ALREADY_EXISTS")
            validator.validate(output_root=destination, overwrite=True)

    def test_all_json_outputs_are_strict_and_finite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage13"
            DataCollectionAnnotationContractValidator().validate(
                output_root=destination
            )
            for path in destination.glob("*.json"):
                value = load_strict_json(path)
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("NaN", text)
                self.assertNotIn("Infinity", text)
                validate_no_forbidden_output_fields(value)
            rows = load_strict_jsonl(
                destination / "fixture_annotation_events.jsonl"
            )
            self.assertEqual(len(rows), 12)

    def test_jsonl_rejects_nan_blank_and_non_object(self):
        for text in ('{"x":NaN}\n', "\n", "[]\n"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.jsonl"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(DataCollectionValidationError):
                    load_strict_jsonl(path)

    def test_strict_dumps_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            dumps_strict({"value": math.nan})
        with self.assertRaises(ValueError):
            dumps_strict({"value": math.inf})

    def test_forbidden_score_and_inference_fields_are_rejected(self):
        for key in (
            "score", "posture_score", "pass", "hirability",
            "anxiety", "diagnosis", "threshold",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_no_forbidden_output_fields({key: None})

    def test_required_blinding_field_with_scores_word_is_allowed(self):
        validate_no_forbidden_output_fields(
            {"blinded_to_stage11_fixture_scores": True}
        )

    def test_original_and_adjudicated_events_are_separate(self):
        registry = DataCollectionFixtureRegistry(DEFAULT_FIXTURE_DIRECTORY)
        original = {
            item.event_id for item in registry.events
            if item.layer.endswith("_ORIGINAL")
        }
        adjudicated = {
            item.event_id for item in registry.events
            if item.layer == "ADJUDICATED_RESULT"
        }
        self.assertTrue(original)
        self.assertTrue(adjudicated)
        self.assertTrue(original.isdisjoint(adjudicated))

    def test_cli_success_and_usage_exit_codes(self):
        script = self.root / "scripts" / (
            "validate_data_collection_annotation_contract.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, str(script),
                    "--output-root", str(Path(directory) / "output"),
                ],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value["status"], "completed")
        usage = subprocess.run(
            [sys.executable, str(script), "--unknown"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(usage.returncode, 2)


if __name__ == "__main__":
    unittest.main()
