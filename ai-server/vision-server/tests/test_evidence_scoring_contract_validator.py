from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.vision.evidence_scoring_contract_validator import (
    EvidenceScoringContractValidationError,
    EvidenceScoringContractValidator,
    load_strict_jsonl,
)


def summary(value: float):
    return {"available": True, "count": 5, "absolute_p95": value}


def aggregate(interval_id: str):
    availability = {
        "available": True,
        "availability_ratio": 1.0,
        "longest_missing_duration_ms": 0,
    }
    return {
        "interval_id": interval_id,
        "head_pose": {
            "relative_yaw_deg": summary(1.0),
            "relative_pitch_deg": summary(1.0),
            "relative_roll_deg": summary(1.0),
            "availability": dict(availability),
        },
        "posture": {
            "relative_shoulder_tilt_deg": summary(1.0),
            "shoulder_center_velocity_norm_per_sec": {
                "available": True,
                "count": 5,
                "p95": 0.1,
            },
            "relative_nose_shoulder_offset_x_norm": summary(0.1),
            "shoulder_availability": dict(availability),
            "nose_alignment_availability": dict(availability),
        },
        "data_quality": {
            "available": True,
            "total_frame_count": 5,
            "head_pose_availability_ratio": 1.0,
            "posture_availability_ratio": 1.0,
            "quality_score": 1.0,
            "target_continuity_ratio": 1.0,
        },
    }


class EvidenceScoringContractValidatorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.fixtures = self.root / "config" / "evidence" / "fixtures"

    def test_synthetic_stage10_smoke_writes_only_fixture_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source_dir = work / "SYNTHETIC_VIDEO"
            source_dir.mkdir()
            source = source_dir / "interval_aggregates.jsonl"
            source.write_text(
                json.dumps(aggregate("I1"), allow_nan=False) + "\n",
                encoding="utf-8",
            )
            output = work / "output"
            report = EvidenceScoringContractValidator().validate(
                source,
                fixture_directory=self.fixtures,
                output_root=output,
            )
            destination = output / "SYNTHETIC_VIDEO"
            self.assertEqual(
                report["technical_judgment"],
                "evidence_scoring_contract_smoke_completed_with_test_fixtures",
            )
            self.assertFalse(report["real_user_score_generated"])
            self.assertEqual(report["smoke_counts"]["result_count"], 3)
            rows = load_strict_jsonl(
                destination / "fixture_metric_score_results.jsonl"
            )
            self.assertTrue(
                all(
                    row["metric_score_result"]["status"]
                    == "SCORED_TEST_FIXTURE"
                    for row in rows
                )
            )
            self.assertTrue(
                all(
                    "test_fixture_score" in row["metric_score_result"]
                    for row in rows
                )
            )
            self.assertEqual(
                {
                    path.name for path in destination.iterdir()
                },
                {
                    "validation_report.json",
                    "validation_report.md",
                    "loaded_evidence_registry.json",
                    "fixture_metric_score_results.jsonl",
                    "evidence_conflicts.json",
                },
            )

    def test_invalid_name_missing_file_and_existing_output_fail_explicitly(self):
        validator = EvidenceScoringContractValidator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(EvidenceScoringContractValidationError):
                validator.validate(root / "wrong.jsonl")
            source_dir = root / "VIDEO"
            source_dir.mkdir()
            source = source_dir / "interval_aggregates.jsonl"
            source.write_text(
                json.dumps(aggregate("I1")) + "\n",
                encoding="utf-8",
            )
            validator.validate(
                source,
                fixture_directory=self.fixtures,
                output_root=root / "output",
            )
            with self.assertRaises(EvidenceScoringContractValidationError) as context:
                validator.validate(
                    source,
                    fixture_directory=self.fixtures,
                    output_root=root / "output",
                )
            self.assertEqual(context.exception.code, "OUTPUT_ALREADY_EXISTS")

    def test_stage10_strict_jsonl_rejects_nan_blank_and_non_object(self):
        for text in ('{"x": NaN}\n', "\n", "[]\n"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "interval_aggregates.jsonl"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(
                    EvidenceScoringContractValidationError
                ):
                    load_strict_jsonl(path)


if __name__ == "__main__":
    unittest.main()
