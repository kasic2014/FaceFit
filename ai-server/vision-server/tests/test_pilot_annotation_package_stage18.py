from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from app.vision.pilot_annotation_package import (
    BLIND_FLAG_NAMES,
    annotation_readiness_status,
    build_empty_template,
    cross_rater_similarity_warnings,
    registry_from_dict,
    validate_rater_submission,
)
from app.vision.pilot_video_intake import (
    PilotVideoIntakeError,
    load_strict_json,
    write_strict_json,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "output" / "pilot_annotation" / "SES_000001"


class PilotAnnotationPackageStage18Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = registry_from_dict(load_strict_json(
            ROOT / "config" / "data_collection" / "fixtures"
            / "annotation_registry.json"
        ))
        cls.answers = load_strict_json(
            ROOT / "data" / "pilot" / "incoming"
            / "PTC_000001_SES_000001.metadata.json"
        )["answers"]

    def _valid(self, rater_id: str = "RATER_A") -> dict:
        value = build_empty_template(rater_id)
        value["completed_at"] = "2026-07-29T21:30:00+09:00"
        value["events"] = [{
            "annotation_event_id": f"{rater_id}_EVT_000001",
            "answer_id": "ANS_000001",
            "interval_id": "INT_ANSWER_001",
            "label_id": "HEAD_TURN_LEFT",
            "direction": "LEFT",
            "start_timestamp_ms": 15_000,
            "end_timestamp_ms": 17_000,
            "rater_confidence": None,
            "note": None,
        }]
        return value

    def test_rater_packages_are_separate(self) -> None:
        a = load_strict_json(
            OUTPUT / "rater_a" / "annotation_events.template.json"
        )
        b = load_strict_json(
            OUTPUT / "rater_b" / "annotation_events.template.json"
        )
        self.assertEqual(a["rater_id"], "RATER_A")
        self.assertEqual(b["rater_id"], "RATER_B")
        self.assertNotEqual(a, b)
        for directory, rater_id in (
            ("rater_a", "RATER_A"),
            ("rater_b", "RATER_B"),
        ):
            result_path = OUTPUT / directory / "annotation_events.json"
            if result_path.exists():
                self.assertEqual(
                    load_strict_json(result_path)["rater_id"],
                    rater_id,
                )

    def test_packages_exclude_model_metric_information(self) -> None:
        for directory in ("rater_a", "rater_b"):
            for name in (
                "answer_intervals.json",
                "annotation_labels.json",
                "annotation_events.template.json",
            ):
                value = load_strict_json(OUTPUT / directory / name)
                serialized = str(value).lower()
                self.assertNotIn("head_pose_value", serialized)
                self.assertNotIn("jump_candidate_timestamp", serialized)
                self.assertNotIn("stage10_metric_value", serialized)

    def test_templates_have_empty_events(self) -> None:
        for rater_id in ("RATER_A", "RATER_B"):
            value = build_empty_template(rater_id)
            self.assertEqual(value["events"], [])
            self.assertIsNone(value["completed_at"])

    def test_valid_annotation_input(self) -> None:
        result = validate_rater_submission(
            self._valid(),
            expected_rater_id="RATER_A",
            answers=self.answers,
            registry=self.registry,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["event_count"], 1)

    def test_event_outside_answer_is_blocked(self) -> None:
        value = self._valid()
        value["events"][0]["start_timestamp_ms"] = 10_000
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_rater_submission(
                value,
                expected_rater_id="RATER_A",
                answers=self.answers,
                registry=self.registry,
            )

    def test_unknown_label_and_wrong_direction_are_blocked(self) -> None:
        unknown = self._valid()
        unknown["events"][0]["label_id"] = "CONFIDENCE"
        with self.assertRaisesRegex(ValueError, "unknown label"):
            validate_rater_submission(
                unknown,
                expected_rater_id="RATER_A",
                answers=self.answers,
                registry=self.registry,
            )
        direction = self._valid()
        direction["events"][0]["direction"] = "RIGHT"
        with self.assertRaisesRegex(ValueError, "direction"):
            validate_rater_submission(
                direction,
                expected_rater_id="RATER_A",
                answers=self.answers,
                registry=self.registry,
            )
        directionless = self._valid()
        directionless["events"][0]["label_id"] = "FACE_NOT_VISIBLE"
        with self.assertRaisesRegex(ValueError, "direction=null"):
            validate_rater_submission(
                directionless,
                expected_rater_id="RATER_A",
                answers=self.answers,
                registry=self.registry,
            )

    def test_exact_duplicate_event_is_blocked(self) -> None:
        value = self._valid()
        duplicate = copy.deepcopy(value["events"][0])
        duplicate["annotation_event_id"] = "RATER_A_EVT_000002"
        value["events"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "exact duplicate"):
            validate_rater_submission(
                value,
                expected_rater_id="RATER_A",
                answers=self.answers,
                registry=self.registry,
            )

    def test_all_blind_flags_must_be_true(self) -> None:
        for flag in BLIND_FLAG_NAMES:
            value = self._valid()
            value[flag] = False
            with self.subTest(flag=flag), self.assertRaisesRegex(
                ValueError, "blind"
            ):
                validate_rater_submission(
                    value,
                    expected_rater_id="RATER_A",
                    answers=self.answers,
                    registry=self.registry,
                )

    def test_one_valid_submission_waits_for_second_rater(self) -> None:
        self.assertEqual(
            annotation_readiness_status(
                {"result_file_exists": True, "valid": True},
                {"result_file_exists": False, "valid": None},
            ),
            "awaiting_second_rater_annotation",
        )

    def test_two_valid_submissions_are_ready_for_agreement(self) -> None:
        self.assertEqual(
            annotation_readiness_status(
                {"result_file_exists": True, "valid": True},
                {"result_file_exists": True, "valid": True},
            ),
            "rater_annotations_ready_for_agreement",
        )

    def test_invalid_present_submission_fails_validation(self) -> None:
        self.assertEqual(
            annotation_readiness_status(
                {"result_file_exists": True, "valid": False},
                {"result_file_exists": False, "valid": None},
            ),
            "rater_annotation_validation_failed",
        )

    def test_identical_event_content_only_produces_warning(self) -> None:
        a = self._valid("RATER_A")
        b = self._valid("RATER_B")
        self.assertEqual(
            cross_rater_similarity_warnings(a, b),
            ["IDENTICAL_EVENT_CONTENT"],
        )

    def test_strict_json_and_forbidden_fields(self) -> None:
        value = self._valid()
        value["posture_score"] = 0.9
        with self.assertRaisesRegex(ValueError, "fields invalid"):
            validate_rater_submission(
                value,
                expected_rater_id="RATER_A",
                answers=self.answers,
                registry=self.registry,
            )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.json"
            path.write_text('{"events":[],"events":[]}', encoding="utf-8")
            with self.assertRaises(PilotVideoIntakeError):
                load_strict_json(path)
            with self.assertRaises(PilotVideoIntakeError):
                write_strict_json(path, {"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
