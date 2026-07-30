from __future__ import annotations

import unittest

from app.vision.neutral_baseline_collector import (
    collect_baseline_candidates,
    evaluate_baseline_candidate,
)
from app.vision.neutral_baseline_models import (
    BaselineFailureReason,
    NeutralBaselineFrame,
)


def frame(timestamp_ms: int = 0, **changes) -> NeutralBaselineFrame:
    head = {
        "available": True,
        "yaw_deg": 20.0,
        "pitch_deg": -2.0,
        "roll_deg": 1.0,
        "confidence": 0.9,
        **changes.pop("head", {}),
    }
    posture = {
        "available": True,
        "shoulders_available": True,
        "nose_alignment_available": True,
        "face_alignment_available": True,
        "shoulder_tilt_deg": 2.0,
        "shoulder_height_difference_norm": 0.01,
        "shoulder_center_x": 0.5,
        "shoulder_center_y": 0.7,
        "shoulder_width_norm": 0.4,
        "nose_shoulder_offset_x_norm": 0.01,
        "nose_shoulder_offset_y_norm": -0.8,
        "face_shoulder_offset_x_norm": 0.02,
        "face_shoulder_offset_y_norm": -0.7,
        "confidence": 0.95,
        **changes.pop("posture", {}),
    }
    temporal = {
        "shoulder_center_velocity_norm_per_sec": 0.01,
        "shoulder_tilt_velocity_deg_per_sec": 1.0,
        "shoulder_width_change_rate_per_sec": 0.01,
        **changes.pop("temporal", {}),
    }
    return NeutralBaselineFrame(
        timestamp_ms=timestamp_ms,
        target_id=changes.pop("target_id", "TARGET_001"),
        target_status=changes.pop("target_status", "TARGET_TRACKED"),
        candidate_count=changes.pop("candidate_count", 1),
        target_confidence=changes.pop("target_confidence", 0.95),
        head_pose=head,
        head_angular_velocity_deg_per_sec=changes.pop("head_velocity", 2.0),
        head_jump_candidate=changes.pop("head_jump", False),
        posture_raw=posture,
        posture_temporal=temporal,
        posture_jump_candidate=changes.pop("posture_jump", False),
    )


class NeutralBaselineCollectorTests(unittest.TestCase):
    def test_stable_frame_is_candidate_for_every_group(self):
        decision = evaluate_baseline_candidate(frame())
        self.assertTrue(decision.common_available)
        self.assertTrue(decision.head_pose_candidate)
        self.assertTrue(decision.shoulder_candidate)
        self.assertTrue(decision.nose_alignment_candidate)
        self.assertTrue(decision.face_alignment_candidate)

    def test_head_motion_rejects_only_head_group(self):
        decision = evaluate_baseline_candidate(frame(head_velocity=60.0))
        self.assertFalse(decision.head_pose_candidate)
        self.assertIn(
            BaselineFailureReason.UNSTABLE_HEAD_MOTION.value,
            decision.head_pose_reasons,
        )
        self.assertTrue(decision.shoulder_candidate)
        self.assertTrue(decision.face_alignment_candidate)

    def test_shoulder_motion_rejects_all_posture_derived_groups(self):
        decision = evaluate_baseline_candidate(
            frame(
                temporal={
                    "shoulder_center_velocity_norm_per_sec": 0.2,
                }
            )
        )
        self.assertTrue(decision.head_pose_candidate)
        self.assertFalse(decision.shoulder_candidate)
        self.assertFalse(decision.nose_alignment_candidate)
        self.assertFalse(decision.face_alignment_candidate)

    def test_missing_face_preserves_shoulder_and_nose_candidates(self):
        decision = evaluate_baseline_candidate(
            frame(
                posture={
                    "face_alignment_available": False,
                    "face_shoulder_offset_x_norm": None,
                    "face_shoulder_offset_y_norm": None,
                }
            )
        )
        self.assertTrue(decision.shoulder_candidate)
        self.assertTrue(decision.nose_alignment_candidate)
        self.assertFalse(decision.face_alignment_candidate)

    def test_multiple_person_and_target_loss_are_common_failures(self):
        decision = evaluate_baseline_candidate(
            frame(candidate_count=2, target_id=None)
        )
        self.assertFalse(decision.common_available)
        self.assertFalse(decision.head_pose_candidate)
        self.assertFalse(decision.shoulder_candidate)
        self.assertIn(
            BaselineFailureReason.MULTIPLE_PERSON_DETECTED.value,
            decision.common_reasons,
        )
        self.assertIn(
            BaselineFailureReason.TARGET_NOT_AVAILABLE.value,
            decision.common_reasons,
        )

    def test_collection_window_and_duplicate_timestamp_are_deterministic(self):
        frames = [frame(0), frame(200), frame(200), frame(2_200)]
        collection = collect_baseline_candidates(
            frames,
            collection_start_ms=0,
            collection_end_ms=2_000,
        )
        self.assertEqual(collection.total_frame_count, 3)
        self.assertEqual(len(collection.head_pose_frames), 2)
        self.assertIn(
            BaselineFailureReason.INVALID_TIMESTAMP.value,
            collection.decisions[2].common_reasons,
        )

    def test_non_finite_and_low_confidence_are_explicit(self):
        decision = evaluate_baseline_candidate(
            frame(
                head={"yaw_deg": float("nan"), "confidence": 0.1},
                posture={"confidence": 0.1},
            )
        )
        self.assertIn(
            BaselineFailureReason.NON_FINITE_VALUE.value,
            decision.head_pose_reasons,
        )
        self.assertIn(
            BaselineFailureReason.LOW_CONFIDENCE.value,
            decision.head_pose_reasons,
        )
        self.assertFalse(decision.shoulder_candidate)


if __name__ == "__main__":
    unittest.main()
