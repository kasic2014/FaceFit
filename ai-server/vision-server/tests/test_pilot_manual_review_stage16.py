from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.vision.dataset_manifest_models import DatasetSplitAssignment
from app.vision.pilot_manual_review import (
    PilotManualReviewDecision,
    context_frame_timestamps,
    create_development_split_assignment,
    map_gate_status,
    select_representative_candidates,
    validate_frame_timestamp,
)
from app.vision.pilot_video_intake import (
    PilotVideoIntakeError,
    assert_no_forbidden_semantics,
    load_strict_json,
    write_strict_json,
)


class PilotManualReviewStage16Tests(unittest.TestCase):
    def test_stage15_results_load_strictly(self) -> None:
        root = (
            Path(__file__).resolve().parents[1]
            / "data" / "output" / "pilot_video_intake_validation"
            / "SES_000001"
        )
        report = load_strict_json(root / "validation_report.json")
        quality = load_strict_json(root / "quality_check_results.json")
        self.assertEqual(
            report["final_decision"], "pilot_video_manual_review_required"
        )
        self.assertTrue(
            quality["summary"]["automatic_validation_passed"]
        )

    def test_candidate_context_is_exact_and_in_range(self) -> None:
        self.assertEqual(
            context_frame_timestamps(10_000, duration_ms=20_000),
            (9_500, 10_000, 10_500),
        )

    def test_out_of_video_frame_request_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_frame_timestamp(-1, 10_000)
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_frame_timestamp(10_000, 10_000)
        with self.assertRaisesRegex(ValueError, "outside"):
            context_frame_timestamps(200, duration_ms=10_000)

    def test_manual_review_decision_enum(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid manual"):
            PilotManualReviewDecision(
                "PTC_000001", "SES_000001", None, "AUTO_APPROVED",
                (), None, None,
            )

    def test_pending_template_cannot_claim_reviewer(self) -> None:
        with self.assertRaisesRegex(ValueError, "pending"):
            PilotManualReviewDecision(
                "PTC_000001", "SES_000001", "REVIEWER_001",
                "REVIEW_PENDING", (), None, None,
            )

    def test_completed_decision_requires_reviewer_and_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "reviewer_id"):
            PilotManualReviewDecision(
                "PTC_000001", "SES_000001", None,
                "APPROVED_FOR_ANNOTATION",
                ("VIDEO_USABLE_FOR_OBSERVABLE_ANNOTATION",),
                "2026-07-29T20:00:00+09:00", None,
            )
        value = PilotManualReviewDecision(
            "PTC_000001", "SES_000001", "REVIEWER_001",
            "APPROVED_FOR_ANNOTATION",
            ("VIDEO_USABLE_FOR_OBSERVABLE_ANNOTATION",),
            "2026-07-29T20:00:00+09:00", None,
        )
        self.assertEqual(value.reviewer_id, "REVIEWER_001")

    def test_missing_decision_blocks_approval(self) -> None:
        self.assertEqual(
            map_gate_status(
                None, split_valid=True, automatic_quality_passed=True
            ),
            "awaiting_human_manual_review_decision",
        )

    def test_gate_status_mapping(self) -> None:
        recording = PilotManualReviewDecision(
            "PTC_000001", "SES_000001", "REVIEWER_001",
            "RECORDING_REQUIRED",
            ("VIDEO_NOT_USABLE_FOR_ANNOTATION",),
            "2026-07-29T20:00:00+09:00", None,
        )
        excluded = PilotManualReviewDecision(
            "PTC_000001", "SES_000001", "REVIEWER_001",
            "EXCLUDED", ("OTHER",),
            "2026-07-29T20:00:00+09:00", None,
        )
        approved = PilotManualReviewDecision(
            "PTC_000001", "SES_000001", "REVIEWER_001",
            "APPROVED_FOR_ANNOTATION",
            ("VIDEO_USABLE_FOR_OBSERVABLE_ANNOTATION",),
            "2026-07-29T20:00:00+09:00", None,
        )
        self.assertEqual(
            map_gate_status(
                recording, split_valid=True, automatic_quality_passed=True
            ),
            "pilot_video_recording_required",
        )
        self.assertEqual(
            map_gate_status(
                excluded, split_valid=True, automatic_quality_passed=True
            ),
            "pilot_video_excluded",
        )
        self.assertEqual(
            map_gate_status(
                approved, split_valid=True, automatic_quality_passed=True
            ),
            "pilot_video_annotation_ready",
        )
        self.assertEqual(
            map_gate_status(
                approved, split_valid=False, automatic_quality_passed=True
            ),
            "awaiting_human_manual_review_decision",
        )

    def test_development_split_and_linkage_have_no_leakage(self) -> None:
        assignment, linkage = create_development_split_assignment(
            participant_id="PTC_000001",
            session_id="SES_000001",
            answer_ids=("ANS_000001", "ANS_000002"),
        )
        self.assertEqual(assignment.split, "DEVELOPMENT")
        self.assertFalse(linkage["leakage_detected"])
        self.assertEqual(
            {item["split_name"] for item in linkage["sessions"]},
            {"DEVELOPMENT"},
        )
        self.assertEqual(
            {item["split_name"] for item in linkage["answers"]},
            {"DEVELOPMENT"},
        )
        self.assertEqual(linkage["other_split_memberships"], [])

    def test_operational_split_conflict_is_rejected(self) -> None:
        existing = DatasetSplitAssignment(
            "PTC_000001", "HOLDOUT", 1,
            "PARTICIPANT_LEVEL_DETERMINISTIC",
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            create_development_split_assignment(
                participant_id="PTC_000001",
                session_id="SES_000001",
                answer_ids=("ANS_000001",),
                operational_assignments=(existing,),
            )

    def test_representative_candidates_remain_inside_answer(self) -> None:
        answer = {
            "answer_id": "ANS_000001",
            "interval_id": "INT_ANSWER_001",
            "start_timestamp_ms": 11_000,
            "end_timestamp_ms": 50_000,
        }
        selected = select_representative_candidates(
            answer=answer,
            missing_segments=({
                "start_timestamp_ms": 12_000,
                "end_timestamp_ms": 16_000,
                "duration_sec": 4.2,
            },),
            head_jump_timestamps=(11_200, 20_000, 49_800),
            posture_jump_timestamps=(25_000, 30_000),
        )
        self.assertLessEqual(len(selected), 5)
        self.assertTrue(all(
            11_500 <= item["timestamp_ms"] < 49_500
            for item in selected
        ))

    def test_strict_json_and_forbidden_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "value.json"
            write_strict_json(path, {"decision": "REVIEW_PENDING"})
            self.assertEqual(
                load_strict_json(path)["decision"], "REVIEW_PENDING"
            )
            with self.assertRaises(PilotVideoIntakeError):
                write_strict_json(path, {"value": float("nan")})
        assert_no_forbidden_semantics({"head_pose_available": False})
        with self.assertRaises(PilotVideoIntakeError):
            assert_no_forbidden_semantics({"personality": "forbidden"})


if __name__ == "__main__":
    unittest.main()
