from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.vision.data_collection_validator import (
    load_strict_json,
    load_strict_jsonl,
    validate_no_forbidden_output_fields,
)
from app.vision.pilot_collection_validator import (
    PilotCollectionReadinessValidator,
    PilotCollectionValidationError,
)


class PilotCollectionValidatorStage14Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_smoke_outputs_and_fixture_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            report = PilotCollectionReadinessValidator().validate(
                output_root=output
            )
            self.assertEqual(
                report["technical_judgment"],
                "pilot_collection_readiness_contract_smoke_completed_with_metadata_fixtures",
            )
            self.assertEqual(report["fixture_counts"]["participant_count"], 6)
            self.assertEqual(report["fixture_counts"]["consent_granted_count"], 5)
            self.assertEqual(report["fixture_counts"]["consent_withdrawn_count"], 1)
            self.assertEqual(report["fixture_counts"]["session_count"], 6)
            self.assertEqual(report["fixture_counts"]["answer_count"], 12)
            self.assertEqual(report["fixture_counts"]["quality_check_count"], 66)
            self.assertEqual(
                {item.name for item in output.iterdir()},
                set(PilotCollectionReadinessValidator.OUTPUT_NAMES),
            )

    def test_success_exclusion_withdrawal_and_rerecord_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = PilotCollectionReadinessValidator().validate(
                output_root=Path(directory) / "output"
            )
            outcomes = report["outcomes"]
            self.assertEqual(outcomes["release_eligible_count"], 2)
            self.assertEqual(outcomes["release_blocked_count"], 4)
            self.assertEqual(outcomes["excluded_session_count"], 2)
            self.assertEqual(outcomes["withdrawn_session_count"], 1)
            self.assertEqual(outcomes["recording_required_count"], 1)
            self.assertEqual(outcomes["file_hash_failure_count"], 1)
            self.assertEqual(outcomes["baseline_failure_count"], 1)

    def test_outputs_are_strict_and_have_no_forbidden_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            PilotCollectionReadinessValidator().validate(output_root=output)
            for path in output.glob("*.json"):
                value = load_strict_json(path)
                validate_no_forbidden_output_fields(value)
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("NaN", text)
                self.assertNotIn("Infinity", text)
            for name in (
                "fixture_pilot_sessions.jsonl",
                "fixture_quality_checks.jsonl",
            ):
                values = load_strict_jsonl(output / name)
                self.assertTrue(values)
                for value in values:
                    validate_no_forbidden_output_fields(value)

    def test_session_and_quality_jsonl_row_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            PilotCollectionReadinessValidator().validate(output_root=output)
            self.assertEqual(
                len(load_strict_jsonl(output / "fixture_pilot_sessions.jsonl")),
                6,
            )
            self.assertEqual(
                len(load_strict_jsonl(output / "fixture_quality_checks.jsonl")),
                66,
            )

    def test_withdrawal_output_never_claims_actual_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            PilotCollectionReadinessValidator().validate(output_root=output)
            value = load_strict_json(
                output / "fixture_withdrawal_results.json"
            )
            self.assertTrue(value["results"])
            self.assertTrue(
                all(
                    not item["actual_file_deleted"]
                    for item in value["results"]
                )
            )

    def test_release_results_never_freeze_or_operationally_approve(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            PilotCollectionReadinessValidator().validate(output_root=output)
            value = load_strict_json(
                output / "fixture_dataset_release_results.json"
            )
            self.assertTrue(
                all(
                    not item["dataset_frozen"]
                    and not item["operationally_approved"]
                    for item in value["results"]
                )
            )

    def test_smoke_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validator = PilotCollectionReadinessValidator()
            first = validator.validate(output_root=root / "first")
            second = validator.validate(output_root=root / "second")
            self.assertEqual(first["output_sha256"], second["output_sha256"])

    def test_existing_output_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            validator = PilotCollectionReadinessValidator()
            validator.validate(output_root=output)
            with self.assertRaises(PilotCollectionValidationError):
                validator.validate(output_root=output)
            validator.validate(output_root=output, overwrite=True)

    def test_cli_exit_codes(self):
        script = self.root / "scripts" / "validate_pilot_collection_readiness.py"
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
            self.assertEqual(json.loads(result.stdout)["status"], "completed")
        usage = subprocess.run(
            [sys.executable, str(script), "--bad-option"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(usage.returncode, 2)


if __name__ == "__main__":
    unittest.main()
